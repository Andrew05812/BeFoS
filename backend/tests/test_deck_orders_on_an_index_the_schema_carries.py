"""The deck's newest-first page ordered a result the schema could not supply in order.

``docs/SCALE_PLAN.md`` («Парные прогоны стадии 55») has the measurement on the 50 000-profile stand.
The refill read the whole visible population — ``Seq Scan on profiles rows=25000 loops=2`` — sorted
it and then took 150, because nothing in the schema offered ``created_at DESC, user_id`` as a key to
walk: 43.5 ms for a viewer whose preferences match everybody, 5.1 ms once that index exists, and the
plan becomes ``Limit -> Index Only Scan`` with no Sort node under it.

What this test checks is the *pairing*, not the plan. At the size of the test database the planner
seq-scans whatever indexes the schema carries, so an assertion about a plan would be red for the
wrong reason; and an index the query no longer orders on is a pure write cost. So the statement the
repository actually emits is captured off the wire with ``before_cursor_execute``, and the test asks
of the catalog: is there an index whose key is that ORDER BY, column for column and direction for
direction, and is it partial over the visibility the same statement puts on every row it can show —
restricted to what an index over ``profiles`` alone is allowed to name. Change the deck's order, or
withdraw a condition the index has to carry, and this fails — which is the point.
"""

from __future__ import annotations

import uuid

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.repositories.social_repo import DiscoveryRepository

_CATALOG = """
WITH idx AS (
    SELECT ic.relname AS index_name,
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
    WHERE n.nspname = 'public' AND c.relname = 'profiles'
    GROUP BY ic.relname, i.indpred IS NOT NULL, pg_get_indexdef(i.indexrelid)
)
SELECT index_name, is_partial, index_def, key FROM idx ORDER BY index_name
"""

# Two details of that query were checked rather than assumed, on the 50 000-profile stand:
# `(i.indoption::int[])[1]` reads the *second* key because casting an int2vector gives an array with
# lower bound 0, hence the `ord - 1`; and bit 0 of indoption is the direction, not the nulls order --
# `created_at DESC` stored 3, `DESC NULLS LAST` stored 1, `ASC NULLS FIRST` stored 2. The documented
# helper `pg_index_column_has_property(..., 'descending')` returns NULL for a btree, so the bit is
# what the catalog actually offers:
#   docker exec befos_postgres psql -U befos -d befos_scale -c "CREATE INDEX ix_probe_dir_a ON
#   profiles (created_at DESC); CREATE INDEX ix_probe_dir_b ON profiles (created_at DESC NULLS LAST);
#   CREATE INDEX ix_probe_dir_c ON profiles (created_at ASC NULLS FIRST)"

# The half of the deck's visibility rule an index over `profiles` can name. The predicate of a
# partial index is an expression over the indexed table only — Postgres refuses the other half with
# `ERROR: cannot use subquery in index predicate` (`docker exec befos_postgres psql -U befos -d befos
# -c "CREATE INDEX ix_probe_users ON profiles (created_at DESC) WHERE (SELECT is_deleted FROM users
# WHERE users.id = profiles.user_id) IS FALSE"`) — so `users.is_deleted IS FALSE` and
# `users.is_active IS TRUE`, which `social_repo._candidate_conditions` states about every row the deck
# can show, stay in the join. The rest of what the deck puts on a row names one viewer — the subject
# exclusion, the preferences, the anti-joins against this viewer's passes and likes — so no index over
# `profiles` could carry that either.
_VISIBILITY = ("is_hidden", "onboarding_completed_at")


def _normalised(statement: str) -> str:
    return " ".join(statement.lower().split())


async def _refill_statement(session: AsyncSession) -> str:
    """The SELECT the deck runs when it needs a new batch, taken from the wire.

    Read from the repository rather than restated here: a test that rebuilt the query would keep
    passing after the real one changed its ORDER BY.
    """
    slot: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany) -> None:
        slot.append(_normalised(statement))

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    try:
        await DiscoveryRepository(session).new_candidate_ids(
            viewer_id=uuid.uuid4(),
            gender_pref=["female"],
            age_min=20,
            age_max=35,
            city=None,
            limit=10,
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)

    wanted = [s for s in slot if "from profiles" in s and "discovery_queue" in s]
    assert wanted, f"the refill never reached the database; saw {len(slot)} statement(s)"
    return wanted[0]


def _order_by(statement: str) -> list[str]:
    """The deck's ORDER BY as ``['created_at desc', 'user_id asc']``."""
    tail = statement.split(" order by ", 1)
    assert len(tail) == 2, "the deck's candidate read has no ORDER BY at all"
    clause = tail[1].split(" limit ", 1)[0]
    terms = []
    for raw in clause.split(","):
        term = raw.strip()
        direction = " desc" if term.endswith(" desc") else " asc"
        column = term.removesuffix(" desc").removesuffix(" asc").strip()
        table, _, name = column.rpartition(".")
        assert table == "profiles", f"the deck orders on {column}, which is not a profiles column"
        terms.append(f"{name}{direction}")
    return terms


async def _indexes(session: AsyncSession) -> list:
    return (await session.execute(text(_CATALOG))).mappings().all()


async def test_the_deck_orders_on_a_key_an_index_carries(session: AsyncSession) -> None:
    statement = await _refill_statement(session)
    order = _order_by(statement)

    rows = await _indexes(session)
    exact = [row for row in rows if list(row["key"]) == order]
    assert exact, (
        f"the deck pages by {order}, and no index on profiles carries that key: "
        f"every batch sorts the whole visible population first"
    )

    # A full index here would enter every registration shell and every hidden profile to serve a
    # read that can never ask for them. Measured on the stand and recorded in docs/SCALE_PLAN.md
    # («Индекс порядка колоды: что он берёт с записи»): 1 000 registrations leave the partial index
    # at 2 039 808 bytes, and completing their onboarding grows it by 49 152 — the entries appear
    # exactly when the deck could start showing them.
    assert all(row["is_partial"] for row in exact), (
        f"{[row['index_name'] for row in exact]} carries rows the deck excludes"
    )


async def test_the_partial_index_carries_the_visibility_an_index_can_name(
    session: AsyncSession
) -> None:
    statement = await _refill_statement(session)
    order = _order_by(statement)

    rows = [row for row in await _indexes(session) if list(row["key"]) == order and row["is_partial"]]
    assert rows, f"no partial index on profiles carries {order}"

    for row in rows:
        predicate = row["index_def"].split(" WHERE ", 1)[1]
        named = {name for name in _VISIBILITY if name in predicate}
        assert named == set(_VISIBILITY), (
            f"{row['index_name']} filters on {sorted(named)}, and both of them are conditions the "
            f"deck states about every row it can show; a row the index holds and the deck refuses is "
            f"a write for nothing"
        )
        for column in _VISIBILITY:
            assert f"profiles.{column}" in statement, (
                f"the deck stopped stating {column} about every row, so the index predicate "
                f"{predicate} no longer matches what the read asks"
            )
        assert "profiles.is_hidden is false" in statement
        assert "profiles.onboarding_completed_at is not null" in statement
