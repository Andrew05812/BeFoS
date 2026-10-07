"""No index may be a left prefix of another index on the same table.

A btree over (from_user_id, to_user_id) answers `WHERE from_user_id = ?` just as a btree over
(from_user_id) does, so the narrower one is never needed for a read and is still written on every
insert. A swipe is one insert into `passes`, so the tax is paid on the most frequent write in the
product. Measured, not assumed: 100 000 rows took 4 047 ms with the extra index and 3 514 ms
without it (`messages`: 4 234 ms against 3 518 ms, and the relation 28 MB against 24 MB). The
experiment and its SQL are recorded in docs/SCALE_PLAN.md.

The property is checked over column *names*, and three shapes are deliberately excluded because
none of them is redundant: an expression index (`lower(email)` is a different key from `email`),
a partial index (a full scan cannot be served by an index that covers only part of the table),
and a unique single column (uniqueness over one column is *not* implied by uniqueness over a pair
that starts with it, so such an index is a constraint, not an accident).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_INDEXES = """
WITH idx AS (
    SELECT c.relname AS table_name,
           ic.relname AS index_name,
           i.indisunique AS is_unique,
           i.indpred IS NOT NULL AS is_partial,
           bool_or(a.attname IS NULL) AS has_expression,
           array_agg(COALESCE(a.attname, '<expression>') ORDER BY k.ord) AS columns
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indrelid
    JOIN pg_class ic ON ic.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN LATERAL unnest(i.indkey::int[]) WITH ORDINALITY AS k(attnum, ord) ON true
    LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
    WHERE n.nspname = 'public' AND c.relkind = 'r'
    GROUP BY c.relname, ic.relname, i.indisunique, i.indpred IS NOT NULL
)
"""

# Every column this repository used to give its own index. Dropping those keys is only safe while
# a wider key still starts with them — this is the half of the claim a later migration can break.
_LEADING_COLUMNS = [
    ("activity_preferences", "user_id"),
    ("blocks", "blocker_id"),
    ("likes", "from_user_id"),
    ("matches", "user_a_id"),
    ("message_reads", "message_id"),
    ("messages", "match_id"),
    ("passes", "from_user_id"),
    ("recommendations", "match_id"),
    ("refresh_tokens", "user_id"),
    ("reports", "reporter_id"),
    ("test_answers", "user_id"),
    ("test_questions", "category"),
    ("test_results", "user_id"),
]


async def test_no_index_is_a_left_prefix_of_another_index_on_the_same_table(
    session: AsyncSession,
) -> None:
    sql = _INDEXES + """
        SELECT narrow.table_name,
               narrow.index_name AS redundant_index,
               wide.index_name AS covered_by,
               narrow.columns
        FROM idx narrow
        JOIN idx wide ON wide.table_name = narrow.table_name AND wide.index_name <> narrow.index_name
        WHERE narrow.has_expression = false
          AND wide.has_expression = false
          AND wide.is_partial = false
          AND narrow.is_unique = false
          AND cardinality(narrow.columns) <= cardinality(wide.columns)
          AND narrow.columns = wide.columns[1:cardinality(narrow.columns)]
        ORDER BY 1, 2
    """
    rows = (await session.execute(text(sql))).mappings().all()

    assert rows == [], "indexes maintained on every write and never needed for a read: " + ", ".join(
        f"{row['table_name']}.{row['redundant_index']} is a prefix of {row['covered_by']}" for row in rows
    )


async def test_the_lookups_left_by_those_indexes_still_have_a_key_to_use(
    session: AsyncSession,
) -> None:
    wanted = ", ".join(f"('{table}', '{column}')" for table, column in _LEADING_COLUMNS)
    sql = _INDEXES + f"""
        SELECT pair.table_name, pair.column_name
        FROM (VALUES {wanted}) AS pair(table_name, column_name)
        WHERE NOT EXISTS (
            SELECT 1 FROM idx i
            WHERE i.table_name = pair.table_name AND i.columns[1] = pair.column_name
        )
        ORDER BY 1, 2
    """
    missing = (await session.execute(text(sql))).mappings().all()

    assert missing == [], "no index starts with these columns any more: " + ", ".join(
        f"{row['table_name']}.{row['column_name']}" for row in missing
    )
