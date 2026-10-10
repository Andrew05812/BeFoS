"""The plan decision has to hold on every connection the pool hands out, not on the one it happens to reuse.

Stages 57 and 58 measured `plan_cache_mode = force_custom_plan` by borrowing a connection and
running a statement on it, so what they proved was about a connection. The pool is where the claim
could quietly stop being true: `pool_size=10, max_overflow=20` means a busy process holds a dozen
connections, each with its own plan cache, and the setting is sent once per connection at connect
time. A regression that reached only the connections created after some change — a `connect_args`
that stopped applying to pooled connections, a second engine introduced for a route — would leave
the existing test green, because that test borrows one connection and the server default is what the
first five executions of a text look like anyway.

Stage 59 measured the shape this test guards on a 50 000 stand (`docs/SCALE_PLAN.md`, «Парные прогоны
стадии 59»): twelve concurrent borrowers, eight executions of one text each, and the
`pg_prepared_statements` counters read by each borrower about its own backend, because that view is
per session. On the control pool every one of those connections had switched; on the app's pool none
had.

The control half is what makes the zero mean something: on this server this text does generalise
after five executions, so an engine that keeps the values has to be read as holding them, not as
running a statement the planner never wanted to widen.

Both tests take the `session` fixture rather than a connection of their own, because that fixture
ends with ``engine.dispose()``: twelve pooled connections left over from this loop is a failure the
suite already guards against.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.database import engine

BORROWERS = 12
# One more than the five executions Postgres plans from the values before it may generalise, so a
# connection that switched has switched by the time its borrower reads the counters.
EXECUTIONS = 8
# What the server holds is the same text with the parameter named by position (`$1`), so the lookup
# below matches the prefix rather than the string the call passes.
_STATEMENT_PREFIX = "SELECT id FROM users WHERE id ="
_QUERY = "SELECT id FROM users WHERE id = :viewer_id"


async def _borrow_run_and_read(borrower_engine, viewer_id) -> tuple[int, int, int]:
    """One borrower: its own pooled connection, `EXECUTIONS` calls, its own counters."""
    async with AsyncSession(bind=borrower_engine, expire_on_commit=False) as session:
        for _ in range(EXECUTIONS):
            await session.execute(text(_QUERY), {"viewer_id": viewer_id})
        rows = (
            await session.execute(
                text("SELECT generic_plans, custom_plans, statement FROM pg_prepared_statements")
            )
        ).all()
        pid = (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
    held = [r for r in rows if r[2].lstrip().startswith(_STATEMENT_PREFIX)]
    if len(held) != 1:
        raise AssertionError(f"this connection holds {len(held)} copies of the text, expected 1")
    return pid, held[0][0], held[0][1]


async def _run_window(borrower_engine) -> list[tuple[int, int, int]]:
    viewer_id = uuid4()
    return list(
        await asyncio.gather(
            *(_borrow_run_and_read(borrower_engine, viewer_id) for _ in range(BORROWERS))
        )
    )


async def test_the_pool_holds_the_setting_on_every_connection_it_opens(session: AsyncSession) -> None:
    windows = await _run_window(engine)
    assert len({pid for pid, _, _ in windows}) == BORROWERS, (
        f"{BORROWERS} simultaneous borrowers came back on {len({w[0] for w in windows})} backend "
        "processes; the window did not spread over the pool, so it proves nothing about the pool"
    )
    switched = [pid for pid, generic, _ in windows if generic > 0]
    assert not switched, (
        f"connections {switched} reached a generic plan after {EXECUTIONS} executions; the plan "
        "decision is no longer reaching every connection the pool opens"
    )
    assert all(custom == EXECUTIONS for _, _, custom in windows), (
        "a connection planned "
        f"{[custom for _, _, custom in windows]} times instead of {EXECUTIONS} on {BORROWERS} "
        "borrowers; the statement text the window runs is no longer the one the server caches"
    )


async def test_the_same_window_on_a_pool_without_the_setting_does_switch(session: AsyncSession) -> None:
    control = create_async_engine(
        settings.database_url, pool_size=BORROWERS, max_overflow=0
    )
    try:
        windows = await _run_window(control)
    finally:
        await control.dispose()

    assert len({pid for pid, _, _ in windows}) == BORROWERS
    switched = sum(1 for _, generic, _ in windows if generic > 0)
    assert switched > 0, (
        f"twelve connections ran the same text {EXECUTIONS} times each and none of them reached a "
        "generic plan; this server no longer generalises the statement, so the guarded engine's "
        "zero above proves nothing"
    )
