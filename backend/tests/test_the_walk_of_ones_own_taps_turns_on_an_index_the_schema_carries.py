"""The walk of one's own taps turned a page by sorting the whole history first.

Stage 123 gave `GET /discover/liked` a cursor, and then priced the walk it made possible: the same
read repeated from the link the previous page handed out, at the three scales the stand keeps — 88,
893 and 4 493 of a viewer's own taps (`s123_pages.json`, скрипт `s123_pages.py`). The pages came out
27.2 / 26.2 мс at 88 taps, 37.7 мс at 893 and 61.2 мс at 4 493. A page that costs the page does not
move like that; a page that sorts the reader's whole history before it takes its fifty rows does, and
the schema is exactly the reason: `likes` carries `uq_like_pair (from_user_id, to_user_id)`, whose
leading column serves the equality and nothing else, and `ix_likes_from_user_id` was dropped by
`e6b28c4a13d0` as a left prefix of that key. So every page of the walk runs
`Sort (rows=N) -> Index Scan using uq_like_pair`, and the ninetieth page of a long history pays for
the whole history again.

What this test checks is the pairing, not the plan — the same rule the deck's order index follows in
`test_deck_orders_on_an_index_the_schema_carries.py`. At the size of the test database the planner
seq-scans whatever the schema carries, so an assertion about a plan would be red for the wrong reason.
The statement the repository really sends is captured off the wire, and the catalog is asked whether
one of `likes`' indexes is the key that statement walks: the equality it puts on the row first, then
its ORDER BY, column for column and direction for direction. Change the walk's order, or move the
page's boundary off the key, and this fails.
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
           pg_get_indexdef(i.indexrelid) AS index_def,
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
    WHERE n.nspname = 'public' AND c.relname = 'likes'
    GROUP BY ic.relname, i.indisunique, i.indpred IS NOT NULL, pg_get_indexdef(i.indexrelid)
)
SELECT index_name, is_unique, is_partial, index_def, key FROM idx ORDER BY index_name
"""

# The key the walk needs, in the order the statement puts it: whose taps, then newest first, then the
# id that decides a tie the timestamp cannot.
_WALK_KEY = ["from_user_id asc", "created_at desc", "id desc"]


def _normalised(statement: str) -> str:
    return " ".join(statement.lower().split())


async def _walk_statements(session: AsyncSession) -> list[str]:
    """Both pages of one reader's walk, taken from the wire rather than restated here.

    The first call is the screen opening, the second is the same read behind the link the first one
    handed out — and it is the second that the cursor was invented for. Read from the repository so
    that changing its ORDER BY or its boundary turns this test red instead of leaving it describing a
    query nobody sends.
    """
    slot: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany) -> None:
        slot.append(_normalised(statement))

    viewer = uuid.uuid4()
    anchor = (datetime(2026, 10, 19, 6, 0, tzinfo=UTC), uuid.uuid4())
    event.listen(engine.sync_engine, "before_cursor_execute", before)
    try:
        await DiscoveryRepository(session).liked(viewer, 51)
        await DiscoveryRepository(session).liked(viewer, 51, before=anchor)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)

    seen = [s for s in slot if "from likes" in s and "join profiles" in s]
    assert len(seen) == 2, f"the walk sent {len(seen)} read(s) over likes, expected two"
    return seen


def _order_by(statement: str) -> list[str]:
    """The walk's ORDER BY as ``['created_at desc', 'id desc']``."""
    tail = statement.split(" order by ", 1)
    assert len(tail) == 2, "the walk of own taps has no ORDER BY at all"
    clause = tail[1].split(" limit ", 1)[0]
    terms = []
    for raw in clause.split(","):
        term = raw.strip()
        direction = " desc" if term.endswith(" desc") else " asc"
        column = term.removesuffix(" desc").removesuffix(" asc").strip()
        table, _, name = column.rpartition(".")
        assert table == "likes", f"the walk orders on {column}, which is not a column of `likes`"
        terms.append(f"{name}{direction}")
    return terms


def _pinned_column(statement: str) -> str:
    """The column the walk puts on every row before it orders anything: the reader's own half.

    Read as a bind equality (`likes.from_user_id = $n`) rather than as a bare mention: the pair and the
    block exclusions name `likes` in subqueries too, and it is the outer predicate that decides which
    part of the key the scan enters first. Drop it and this fails — which is the point, since a walk
    that no longer addresses its own rows is a tenancy bug before it is a slow one.
    """
    if "likes.from_user_id = $" in statement:
        return "from_user_id asc"
    raise AssertionError(f"the walk does not pin the reader's own taps; it reads: …{statement[:320]}")


async def _indexes(session: AsyncSession) -> list:
    return (await session.execute(text(_CATALOG))).mappings().all()


async def test_the_walk_turns_on_a_key_the_schema_carries(session: AsyncSession) -> None:
    first, turned = await _walk_statements(session)
    for statement in (first, turned):
        order = _order_by(statement)
        key = [_pinned_column(statement), *order]
        assert key == _WALK_KEY, f"the walk now asks for {key}, and this test prices {_WALK_KEY}"

        rows = await _indexes(session)
        exact = [row for row in rows if list(row["key"]) == _WALK_KEY]
        assert exact, (
            f"no index on `likes` carries {_WALK_KEY}: every page of the walk sorts the reader's "
            f"whole history before it takes its fifty rows. The catalog offers "
            f"{[(row['index_name'], list(row['key'])) for row in rows]}"
        )


async def test_the_key_is_whole_because_no_part_of_the_visibility_rule_is_nameable(
    session: AsyncSession,
) -> None:
    """A partial index here could not exclude what the walk excludes, so it must not pretend to.

    The deck's order key is partial for one reason: half of its visibility rule is a pair of columns
    on `profiles` itself. This read's exclusions live in the tables it joins — a tap toward a hidden,
    deleted or deactivated account is dropped by `users.is_deleted` / `users.is_active` and by
    `profiles.is_hidden`, and the pair and the block are two other tables — and Postgres refuses a
    predicate over another table in an index (`cannot use subquery in index predicate`). A partial key
    over `likes` alone would be a full key with a lie about it, so the measured write cost is the price
    and it is named in `docs/SCALE_PLAN.md` instead of hidden in a predicate.
    """
    rows = await _indexes(session)
    exact = [row for row in rows if list(row["key"]) == _WALK_KEY]
    assert exact, "the walk's key is gone from the schema"
    assert not any(row["is_partial"] for row in exact), (
        f"{[row['index_name'] for row in exact if row['is_partial']]} claims to skip rows the walk's "
        "exclusions cannot be expressed on `likes` alone"
    )
    # The tap's own uniqueness stays where it was: this key exists to serve an order, not a rule.
    assert not any(row["is_unique"] for row in exact), (
        "the walk's order key is unique, which `uq_like_pair` already decides"
    )


async def test_turning_the_page_costs_the_page_and_not_the_history(session: AsyncSession) -> None:
    """The boundary the cursor draws has to sit on the same key the index walks.

    A page whose boundary is a tuple `(created_at, id)` compared as one value is what lets Postgres
    stop inside the index instead of reading to the end of the reader's history and cutting it. Written
    as two separate comparisons it still answers correctly — and the plan goes back to sorting, which is
    the defect this stage measured. So the shape is asserted, not the plan.
    """
    _first, turned = await _walk_statements(session)
    assert "(likes.created_at, likes.id) < (" in turned, (
        f"the second page no longer compares the pair as one value; it says: …{turned[-260:]}"
    )
    assert " offset " not in turned, "the walk moved back to OFFSET, which shifts under a withdrawal"
