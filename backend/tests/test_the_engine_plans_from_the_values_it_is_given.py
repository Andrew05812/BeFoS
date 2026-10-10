"""The engine asks each connection to plan from the values it was given, and that is measurable.

Postgres plans a named prepared statement from its bound values for the first five executions and
then may keep one generic plan for the rest of the connection's life. The SQLAlchemy asyncpg dialect
names every statement it caches, so the switch is the app's, not the driver's: on the 50 000 stand
(stage 57, ``docs/SCALE_PLAN.md``) every hot read ended its 40-call window at 35 generic plans
against 5 custom, and for the deck's selection rule over a spent deck that switch is the difference
between a 106 ms page and a 230 ms one.

``plan_cache_mode = force_custom_plan`` is what keeps the values, and it lives on the engine, so a
regression here is silent — nothing breaks, the page just gets more than twice as slow again. The
setting reaching the server is asserted first; then one statement is run twelve times on one
connection of the app's engine and on one connection of an engine built without the setting, and
``pg_prepared_statements`` is read for the counters the server kept. The second half is the control:
it shows that on this server, this statement and this count the switch is real, so the guarded
engine's zero is not a statement the planner never wanted to generalise.

Both tests take the `session` fixture rather than a connection of their own, because that fixture
ends with ``engine.dispose()``: a pooled connection left over from a previous test's event loop is a
failure this suite already guards against.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings

EXECUTIONS = 12
# What the server holds is the same text with the parameter named by position (`$1`), so the lookup
# below matches the prefix rather than the string the call passes.
_STATEMENT_PREFIX = "SELECT id FROM users WHERE id ="
_QUERY = "SELECT id FROM users WHERE id = :viewer_id"


async def _plan_counters(session: AsyncSession) -> tuple[int, int]:
    """``(generic_plans, custom_plans)`` held for this test's statement on this connection."""
    rows = (
        await session.execute(
            text("SELECT statement, generic_plans, custom_plans FROM pg_prepared_statements")
        )
    ).all()
    held = [(r[1], r[2]) for r in rows if r[0].lstrip().startswith(_STATEMENT_PREFIX)]
    if not held:
        raise AssertionError("the statement was never prepared on this connection")
    return sum(g for g, _ in held), sum(c for _, c in held)


async def _run_twelve_times(session: AsyncSession) -> None:
    viewer_id = uuid4()
    for _ in range(EXECUTIONS):
        await session.execute(text(_QUERY), {"viewer_id": viewer_id})


async def test_the_product_engine_sends_the_plan_mode_it_documents(session: AsyncSession) -> None:
    """Every connection the app borrows reports custom plans, not the server default."""
    mode = (await session.execute(text("SHOW plan_cache_mode"))).scalar_one()

    assert mode == "force_custom_plan", (
        "without it a connection switches to one generic plan after five executions of a text, "
        "and the deck's page over a spent deck pays for the whole candidate set again"
    )


async def test_a_statement_of_the_app_engine_never_reaches_a_generic_plan(
    session: AsyncSession,
) -> None:
    await _run_twelve_times(session)
    guarded_generic, guarded_custom = await _plan_counters(session)

    control = create_async_engine(settings.database_url, pool_size=1, max_overflow=0)
    try:
        async with AsyncSession(bind=control, autoflush=False) as other:
            await _run_twelve_times(other)
            control_generic, _ = await _plan_counters(other)
    finally:
        await control.dispose()

    assert control_generic > 0, (
        f"the engine without the setting ran the text {EXECUTIONS} times and got {control_generic} "
        "generic plans; if this server no longer generalises the statement, the assertions below "
        "prove nothing"
    )
    assert guarded_generic == 0, (
        f"the app engine kept {guarded_generic} generic plans against {guarded_custom} custom, "
        "while the control engine reached a generic plan on the same statement"
    )
    assert guarded_custom == EXECUTIONS, (
        f"the app engine planned {guarded_custom} times, expected {EXECUTIONS}"
    )
