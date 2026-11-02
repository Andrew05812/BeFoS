"""The two lists that learned to turn a page in stage 126 turn on a key the schema carries.

Stage 123 proved this rule once, for `GET /discover/liked`: a walk that resumes below a `(created_at,
id)` pair needs the order in the index, or every page gathers the reader's whole history first. The
proof then was a shoot — 27.2 / 37.7 / 61.2 мс for one page of 88 / 893 / 4 493 taps, and `ix_likes_tapper_order`
brought it down to the page (`s123_pages.json`).

Stage 126 opened two more doors of the same shape and shot the same pair of pages on the 50 000 stand
(`s126_scale_a.json`, база `befos_s126scale_a`, дерево `e648054`):

    liked_me       56.8 мс плана / 59.5 мс   liked_me_tail  90.6 мс / 67.1 мс
    passed         93.8 мс / 96.9 мс         passed_tail   195.6 мс / 264.8 мс

with the worst node of the inbox a sequential scan of 25 000 анкет done twice, and the worst node of
the pass list an index scan of one profile repeated 15 456 times — once per row of a reader who holds
15 506 passes. The door that had the key, on the very same table and the same projection, cost 4.8 мс.

Like the stage-123 guard, this checks the pairing rather than a plan: at the size of a test database
the planner seq-scans whatever the schema carries, so an assertion about a plan would be red for the
wrong reason. What is asserted is that the statement the repository really sends — taken off the wire,
both its pages — asks for a key, and that exactly one index on the table carries that key, column for
column and direction for direction. Move the ORDER BY, change the half of the row the reader is
addressed by, or drop the migration, and this fails.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.repositories.social_repo import DiscoveryRepository

_CATALOG = """
WITH idx AS (
    SELECT ic.relname AS index_name,
           i.indisunique AS is_unique,
           i.indpred IS NOT NULL AS is_partial,
           array_agg(
               a.attname || CASE
                   WHEN ((i.indoption::int[])[k.ord - 1] & 1) = 1 THEN ' desc'
                   ELSE ' asc'
               END
               ORDER BY k.ord
           ) AS key
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indrelid
    JOIN pg_class ic ON ic.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN LATERAL unnest(i.indkey::int[]) WITH ORDINALITY AS k(attnum, ord) ON true
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
    WHERE n.nspname = 'public' AND c.relname = :table
    GROUP BY ic.relname, i.indisunique, i.indpred IS NOT NULL
)
SELECT index_name, is_unique, is_partial, key FROM idx ORDER BY index_name
"""

# The key each walk needs: the reader's own half of the row, then newest first, then the id that
# decides the tie the timestamp cannot.
_INBOX_KEY = ["to_user_id asc", "created_at desc", "id desc"]
_PASS_KEY = ["from_user_id asc", "created_at desc", "id desc"]

# One entry per door: the table it reads, the column that names the reader in that table, the key the
# scan has to enter by, and the repository call that sends both pages.
_DOORS = [
    ("likes", "to_user_id", _INBOX_KEY, DiscoveryRepository.liked_me),
    ("passes", "from_user_id", _PASS_KEY, DiscoveryRepository.passed),
]


def _normalised(statement: str) -> str:
    return " ".join(statement.lower().split())


async def _pages(session: AsyncSession, table: str, read) -> tuple[str, str]:
    """The screen's first page and the same read behind its own link, taken from the wire."""
    slot: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany) -> None:
        slot.append(_normalised(statement))

    viewer = uuid.uuid4()
    anchor = (datetime(2026, 11, 2, 6, 0, tzinfo=UTC), uuid.uuid4())
    event.listen(engine.sync_engine, "before_cursor_execute", before)
    try:
        await read(DiscoveryRepository(session), viewer, 51)
        await read(DiscoveryRepository(session), viewer, 51, before=anchor)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)

    seen = [s for s in slot if f"from {table}" in s and "join profiles" in s]
    assert len(seen) == 2, f"`{table}` read sent {len(seen)} statement(s) over the door, expected two"
    return seen[0], seen[1]


def _order_by(statement: str, table: str) -> list[str]:
    tail = statement.split(" order by ", 1)
    assert len(tail) == 2, f"the walk of `{table}` has no ORDER BY at all"
    terms = []
    for raw in tail[1].split(" limit ", 1)[0].split(","):
        term = raw.strip()
        direction = " desc" if term.endswith(" desc") else " asc"
        column = term.removesuffix(" desc").removesuffix(" asc").strip()
        owner, _, name = column.rpartition(".")
        assert owner == table, f"the walk orders on {column}, which is not a column of `{table}`"
        terms.append(f"{name}{direction}")
    return terms


def _pinned(statement: str, table: str, column: str) -> str:
    """The equality that addresses the reader's own half of the table, read off the outer predicate.

    A bare mention would not do: the pair and the block exclusions name the same columns inside
    subqueries, and it is the outer predicate that decides which part of a key the scan enters first.
    A walk that stopped addressing its own rows would be a tenancy bug before it was a slow one, so the
    absence of this clause is a failure rather than a different key.
    """
    if f"{table}.{column} = $" in statement:
        return f"{column} asc"
    raise AssertionError(f"the walk of `{table}` does not pin the reader's rows: …{statement[:320]}")


async def _indexes(session: AsyncSession, table: str) -> list:
    return (await session.execute(text(_CATALOG), {"table": table})).mappings().all()


async def test_each_turning_list_walks_a_key_the_schema_carries(session: AsyncSession) -> None:
    for table, column, key, read in _DOORS:
        first, turned = await _pages(session, table, read)
        for name, statement in (("first page", first), ("turned page", turned)):
            asked = [_pinned(statement, table, column), *_order_by(statement, table)]
            assert asked == key, f"the {name} of `{table}` asks for {asked}, this guard prices {key}"

            rows = await _indexes(session, table)
            exact = [row for row in rows if list(row["key"]) == key]
            assert exact, (
                f"no index on `{table}` carries {key}: every page of that walk sorts the reader's "
                f"whole history before it takes its fifty rows. The catalog offers "
                f"{[(row['index_name'], list(row['key'])) for row in rows]}"
            )


async def test_the_two_new_keys_are_whole_because_no_part_of_the_rule_is_nameable(
    session: AsyncSession,
) -> None:
    """Neither key is partial and neither is unique — the same two facts stage 123 wrote for the first.

    What these reads exclude lives in the tables they join (`users.is_deleted`, `users.is_active`,
    `profiles.is_hidden`, the pair, the block), and Postgres refuses a predicate over another table in
    an index, so a partial key would be a full one with a lie about it. Uniqueness over the reader's
    half is already decided by `uq_like_pair` and `uq_pass_pair`; a second unique key would refuse rows
    the first permits and serve no order the first does not.
    """
    for table, _column, key, _read in _DOORS:
        rows = await _indexes(session, table)
        exact = [row for row in rows if list(row["key"]) == key]
        assert exact, f"the key over `{table}` is gone from the schema"
        assert not any(row["is_partial"] for row in exact), (
            f"{[row['index_name'] for row in exact if row['is_partial']]} claims to skip rows "
            f"whose exclusion cannot be expressed on `{table}` alone"
        )
        assert not any(row["is_unique"] for row in exact), (
            f"the order key over `{table}` is unique, which the pair constraint already decides"
        )


async def test_turning_either_page_costs_the_page_and_not_the_history(session: AsyncSession) -> None:
    """The boundary sits on the same key the index walks, as one value over two columns.

    Written as two separate comparisons the page still answers correctly — and the plan goes back to
    sorting, which is the defect this stage measured. So the shape is asserted, not the plan.
    """
    for table, _column, _key, read in _DOORS:
        _first, turned = await _pages(session, table, read)
        assert f"({table}.created_at, {table}.id) < (" in turned, (
            f"the second page over `{table}` no longer compares the pair as one value: "
            f"…{turned[-260:]}"
        )
        assert " offset " not in turned, f"the walk over `{table}` moved back to OFFSET"
