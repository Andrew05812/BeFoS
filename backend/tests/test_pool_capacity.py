"""What one backend process can hold against the database, and what a client is told when
it cannot get in.

Measured 2026-10-09 against the running stand with nothing else driving it:

* 45 simultaneous borrowers of an engine built with the shipped numbers (`pool_size=10`,
  `max_overflow=20`) produced 30 distinct `pg_backend_pid()` values and 15 refusals. Every
  refusal was `sqlalchemy.exc.TimeoutError` after 30.002 / 30.004 / 30.007 s, and the pool
  reported `timeout: 30.0` — a number `database.py` never sets, so it is SQLAlchemy's default.
* The server itself accepts 100 client backends: 96 opened by the probe, plus its own watcher,
  plus the three the backend container already held, and the 101st attempt raised
  `asyncpg.exceptions.TooManyConnectionsError` («sorry, too many clients already», SQLSTATE 53300).
  Batches of one and batches of ten reached the same boundary.
* With the stand full an ordinary route over the shipped dependency answered `503
  database_unavailable` with `Retry-After: 5` and no credential text, and `/health/db` answered
  `503 degraded`. The refusal shows up in the log
  (`no database connection for this request (TooManyConnectionsError)`), not in the answer.

The checks below reproduce those shapes without filling the stand: a small pool of the same class
queues and refuses the same way, and the driver's refusal is raised at the driver boundary using
the class and message the probe measured.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import asyncpg
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import database as database_module
from app.core.config import settings
from app.core.database import _DROPPED_CONNECTION, checkout_connection, engine, get_session
from app.core.exceptions import register_exception_handlers

_OPERATIONS = Path(__file__).resolve().parents[2] / "docs" / "OPERATIONS.md"

# The two ways to be told no, in the words each one uses.
_QUEUE_REFUSAL = "QueuePool limit"
_SERVER_REFUSAL = "sorry, too many clients already"


def _sessions(bind):
    return async_sessionmaker(
        bind=bind, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


async def _take(sessions) -> tuple[int, AsyncSession]:
    """Borrow a connection, prove it is a real backend, and keep it borrowed."""
    session = sessions()
    await checkout_connection(session)
    pid = (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
    return int(pid), session


async def _route_app():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/needs-the-database")
    async def _route(session: AsyncSession = Depends(get_session)) -> dict:
        return {"rows": (await session.execute(text("SELECT 1"))).scalar()}

    return app


async def _ask(app) -> tuple[int, float, str, str | None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        started = time.perf_counter()
        response = await client.get("/needs-the-database")
        waited = time.perf_counter() - started
    return (
        response.status_code,
        waited,
        response.text,
        response.headers.get("retry-after"),
    )


@pytest.fixture
async def small_pool(monkeypatch):
    """A pool of the same class the app runs, shrunk so its queue is reachable in a test.

    The dependency is repointed at it, so a request and the blockers of this test borrow from
    one pool rather than from two — the shipped engine has 30 slots and would answer anything
    a test asks of it.
    """
    bind = create_async_engine(
        settings.database_url,
        pool_size=2,
        max_overflow=1,
        pool_timeout=1,
        pool_pre_ping=True,
        pool_recycle=1800,
    )
    sessions = _sessions(bind)
    monkeypatch.setattr(database_module, "AsyncSessionLocal", sessions)
    try:
        yield bind, sessions
    finally:
        await bind.dispose()


async def test_the_ceiling_of_a_pool_is_its_size_plus_its_overflow(small_pool) -> None:
    """The per-process ceiling published in §7 is a property of the pool, proved at a scale
    a test can reach.

    Three borrowers of a 2+1 pool get three different backends; the fourth is not queued
    forever — the pool refuses it after its own timeout. And when a connection is handed back,
    the next borrower gets in: the refusal is the queue, not a pool that stopped working.
    """
    _, sessions = small_pool
    held: list[AsyncSession] = []
    try:
        pids = set()
        for _ in range(3):
            pid, session = await _take(sessions)
            held.append(session)
            pids.add(pid)
        assert len(pids) == 3, f"the ceiling is not size+overflow: {pids}"

        started = time.perf_counter()
        queued = sessions()
        try:
            with pytest.raises(Exception) as refused:
                await checkout_connection(queued)
        finally:
            await queued.close()
        waited = time.perf_counter() - started
        assert type(refused.value).__name__ == "TimeoutError"
        assert _QUEUE_REFUSAL in str(refused.value)
        assert 0.8 <= waited < 3.0, f"the queue did not wait out its timeout: {waited}"

        await held.pop().close()
        served = sessions()
        try:
            await checkout_connection(served)
            assert (await served.execute(text("SELECT 1"))).scalar_one() == 1
        finally:
            await served.close()
    finally:
        for session in held:
            await session.close()


async def test_a_request_that_had_to_queue_is_answered_when_the_wait_ends(small_pool) -> None:
    """A client that got no connection must not read it as a bug in its own request.

    The existing coverage points the engine at a host that answers nothing; this is the other
    failure — the database is fine and the pool is full. Same dependency, same 503, and the
    answer arrives when the wait ends rather than whenever the driver feels like it.
    """
    _, sessions = small_pool
    blockers = [await _take(sessions) for _ in range(3)]
    try:
        status_code, waited, body, retry_after = await _ask(await _route_app())
    finally:
        for _, session in blockers:
            await session.close()

    assert status_code == 503, body
    assert '"database_unavailable"' in body
    assert retry_after == "5"
    assert "befos_password" not in body
    assert 0.8 <= waited < 3.0, f"the request was not answered at the end of the wait: {waited}"


async def test_the_overflow_connection_is_closed_and_the_kept_ones_are_not(
    small_pool,
) -> None:
    """What a replica holds between spikes, measured rather than assumed.

    `pool_size` is a floor for the idle set, not only a ceiling: after three simultaneous
    borrowers of a 2+1 pool the server still has two of their backends and the overflow one is
    gone. Scaled to the shipped numbers, a process that has seen one peak of 30 keeps 10 open
    from then on, so N replicas cost 10N idle connections at rest rather than nothing.
    """
    _, sessions = small_pool
    held = [await _take(sessions) for _ in range(3)]
    pids = [pid for pid, _ in held]
    for _, session in held:
        await session.close()

    watcher = sessions()
    try:
        await checkout_connection(watcher)
        rows = (
            await watcher.execute(
                text("select pid from pg_stat_activity where pid = any(cast(:pids as integer[]))"),
                {"pids": pids},
            )
        ).scalars()
        still_open = {int(pid) for pid in rows}
    finally:
        await watcher.close()

    assert len(still_open) == 2, (
        f"the pool kept {sorted(still_open)} of {pids}, expected pool_size of them"
    )


async def test_a_refusal_by_the_database_itself_is_answered_the_same_way(
    monkeypatch,
) -> None:
    """The second way to be told no: the server has no slot left for this process.

    The class and the message are the ones measured at the 101st connection; they are raised at
    the driver boundary because filling 100 slots for a test would take the stand away from
    everything else. What is under test is the mapping. A server-side refusal is not a dropped
    connection, so the once-retry in `checkout_connection` must not treat it as one, and the
    request still ends as 503 with the driver's text kept out of the answer.
    """
    from sqlalchemy.dialects.postgresql import asyncpg as asyncpg_dialect

    assert not issubclass(
        asyncpg.exceptions.TooManyConnectionsError, _DROPPED_CONNECTION
    ), "a slotless server would be retried as though the connection had simply died"

    def refuse(*args, **kwargs):
        raise asyncpg.exceptions.TooManyConnectionsError(_SERVER_REFUSAL)

    monkeypatch.setattr(asyncpg_dialect.AsyncAdapt_asyncpg_dbapi, "connect", refuse)

    bind = create_async_engine(settings.database_url, pool_size=1, max_overflow=0)
    monkeypatch.setattr(database_module, "AsyncSessionLocal", _sessions(bind))
    try:
        status_code, _, body, retry_after = await _ask(await _route_app())
    finally:
        await bind.dispose()

    assert status_code == 503, body
    assert '"database_unavailable"' in body
    assert retry_after == "5"
    assert _SERVER_REFUSAL not in body
    assert "befos_password" not in body


def test_the_operations_page_publishes_the_wait_and_the_settings_of_the_pool() -> None:
    """§7 tells an operator how many replicas fit, so its numbers are the engine's numbers.

    The section used to derive the ceiling by arithmetic, to name a superuser reserve the stand
    does not have (~10 against a measured 3), and to promise that a saturated fourth replica
    answers with a refused connection rather than «database unavailable» — measured, the client
    gets 503 `database_unavailable`. The capacity advice is only true while it tracks the pool it
    describes, so the settings the engine reports have to be the settings the page states: a
    silent SQLAlchemy default for the queue wait, or a retuned pool, now breaks the page's own
    guard instead of quietly invalidating it.
    """
    section = _operations_section()
    documented = {
        key: value
        for key, value in re.findall(
            r"(pool_size|max_overflow|pool_timeout|pool_pre_ping|pool_recycle)\s*=\s*`?([^`,\s]+)",
            section,
        )
    }
    actual = {
        "pool_size": str(engine.pool.size()),
        "max_overflow": str(engine.pool._max_overflow),
        "pool_timeout": _seconds(engine.pool.timeout()),
        "pool_pre_ping": str(engine.pool._pre_ping),
        "pool_recycle": str(engine.pool._recycle),
    }

    for key, value in actual.items():
        assert documented.get(key) == value, (
            f"§7 says {documented.get(key)!r} about {key}, the engine says {value!r}"
        )

    assert "pool_timeout" in Path(database_module.__file__).read_text(encoding="utf-8"), (
        "the queue wait an operator is told to plan around is a library default again"
    )


def _operations_section() -> str:
    body = _OPERATIONS.read_text(encoding="utf-8")
    start = body.index("## 7. ")
    end = body.find("\n## ", start + 1)
    return body[start : len(body) if end == -1 else end]


def _seconds(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)
