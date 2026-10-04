"""The database half of reliability: a probe that tells the truth, and a pool that
notices a connection the server already closed.

Both are cheap to lose and expensive to discover in production, so each is pinned here
rather than left to the settings file.
"""

from __future__ import annotations

import asyncpg
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1 import health as health_module
from app.core.config import settings
from app.core.database import checkout_connection, engine, get_session
from app.main import create_app

# A database nobody answers, named the way a real one is named: host, user and password.
_UNREACHABLE = "postgresql+asyncpg://befos:befos_password@127.0.0.1:1/befos?timeout=2"


def _sessions_bound_to(url: str):
    dead = create_async_engine(url, pool_size=1, max_overflow=0)
    return dead, async_sessionmaker(bind=dead, class_=AsyncSession, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def broken_db(monkeypatch):
    """The probe's own session factory, pointed at a database that is not there.

    Nothing is stubbed inside the route: the borrow fails the way it fails in production,
    and the route is on its own to answer honestly about it.
    """
    dead, sessions = _sessions_bound_to(_UNREACHABLE)
    monkeypatch.setattr(health_module, "AsyncSessionLocal", sessions)
    try:
        yield
    finally:
        await dead.dispose()


async def test_a_probe_that_says_ok_while_the_database_is_down_is_worse_than_none(
    broken_db,
) -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health/db")

    assert response.status_code == 503, "a degraded database must not read as healthy"
    assert response.json() == {"status": "degraded", "database": "unavailable"}


async def test_the_degraded_probe_does_not_repeat_the_connection_string(broken_db) -> None:
    """The route answers without a login, and a driver error names the host, the user and
    the password of the database."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = (await client.get("/api/v1/health/db")).text

    assert "befos_password" not in body
    assert "127.0.0.1:1" not in body
    assert _UNREACHABLE not in body


async def test_a_request_that_cannot_reach_the_database_says_service_unavailable(
    monkeypatch,
) -> None:
    """The same failure on an ordinary endpoint must not read as a bug in the request.

    Before the borrow moved into the dependency, a database that is down produced a bare
    500 with the driver's text in the log and nothing a client could act on.
    """
    from app.core import database as database_module
    from app.core.exceptions import register_exception_handlers

    dead, sessions = _sessions_bound_to(_UNREACHABLE)
    monkeypatch.setattr(database_module, "AsyncSessionLocal", sessions)

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/needs-the-database")
    async def _route(session: AsyncSession = Depends(get_session)) -> dict:
        return {"rows": (await session.execute(text("SELECT 1"))).scalar()}

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/needs-the-database")
    finally:
        await dead.dispose()

    assert response.status_code == 503, "503 with a retry, not a 500 blaming the request"
    assert response.json()["error"]["code"] == "database_unavailable"
    assert response.headers["retry-after"] == "5"
    assert "befos_password" not in response.text


async def test_the_probe_reports_connected_when_the_database_answers(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_the_pool_is_configured_to_drop_dead_connections() -> None:
    assert engine.pool._pre_ping is True, (
        "without a ping before use, a connection the server closed surfaces as a failed "
        "request instead of a reconnect"
    )
    assert engine.pool._recycle and engine.pool._recycle > 0, (
        "a connection older than the recycle window is replaced before an idle network "
        "has had a chance to forget it"
    )


async def test_a_connection_the_server_dropped_still_serves_the_next_request() -> None:
    """The guarantee, proved against a real kill rather than a fake error.

    A single-connection pool is used so the connection under test is the one handed out
    again, and the kill comes from a second engine — asking a connection to terminate
    itself only proves Postgres can oblige. Repeated without any pause, because the
    failure only appears when the next borrow races the loss notification.
    """
    for _ in range(5):
        probe = create_async_engine(
            settings.database_url,
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        terminator = create_async_engine(settings.database_url, pool_size=1, max_overflow=0)
        sessions = async_sessionmaker(
            bind=probe, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        try:
            async with probe.connect() as conn:
                pid = (await conn.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            async with terminator.connect() as other:
                await other.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})

            for _ in range(3):
                session = sessions()
                try:
                    await checkout_connection(session)
                    assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
                finally:
                    await session.close()
        finally:
            await probe.dispose()
            await terminator.dispose()


async def test_the_dependency_borrows_its_connection_before_the_handler_runs(
    monkeypatch, caplog
) -> None:
    """Deterministic version of the same recovery: asyncpg's own ping is made to fail the
    way it fails after a server-side kill, once.

    Patching the driver's ping rather than the code under test keeps the test honest — if
    the retry disappears, the raised error reaches the dependency and the test fails
    instead of quietly passing on a connection that happened to stay alive. The dependency
    runs over a pool of its own: the app's engine is shared by every test in the session
    and a connection left behind here belongs to an event loop that is about to close.
    """
    from sqlalchemy.dialects.postgresql import asyncpg as asyncpg_dialect

    import app.core.database as database

    pool = create_async_engine(
        settings.database_url, pool_size=1, max_overflow=0, pool_pre_ping=True, pool_recycle=1800
    )
    monkeypatch.setattr(
        database,
        "AsyncSessionLocal",
        async_sessionmaker(bind=pool, class_=AsyncSession, expire_on_commit=False, autoflush=False),
    )

    real_ping = asyncpg_dialect.AsyncAdapt_asyncpg_connection.ping
    state = {"failed": False}

    def ping_once(self) -> None:
        if not state["failed"]:
            state["failed"] = True
            raise asyncpg.exceptions._base.InternalClientError(
                "cannot switch to state 15; another operation (2) is in progress"
            )
        real_ping(self)

    monkeypatch.setattr(asyncpg_dialect.AsyncAdapt_asyncpg_connection, "ping", ping_once)
    caplog.set_level("WARNING")

    async def borrowed_query() -> int:
        dependency = get_session()
        session = await dependency.__anext__()
        try:
            return (await session.execute(text("SELECT 1"))).scalar_one()
        finally:
            await dependency.aclose()

    try:
        # A connection the pool has just created is not pinged, so the first borrow is the
        # one that stays clean; the break proves the patched ping was reached.
        for _ in range(4):
            assert await borrowed_query() == 1
            if state["failed"]:
                break
    finally:
        await pool.dispose()

    assert state["failed"], "the ping was never reached, so nothing was proved"
    retried = [m for _, level, m in _rows(caplog) if "connection the server dropped" in m]
    assert retried, "a silent retry is indistinguishable from a connection that never broke"


def _rows(caplog) -> list[tuple[str, str, str]]:
    return [(r.name, r.levelname, r.getMessage()) for r in caplog.records]
