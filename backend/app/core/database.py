from __future__ import annotations

from collections.abc import AsyncGenerator

import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    # A connection an idle half hour has passed over is cheaper to throw away than to
    # discover dead on the first request after a quiet night.
    pool_recycle=1800,
    pool_size=10,
    max_overflow=20,
    # How long the 31st concurrent request of this process waits before it is refused. It is
    # SQLAlchemy's own default, and the number §7 of OPERATIONS.md tells an operator to plan
    # around, so it is written down rather than inherited: measured on the stand, 15 borrowers
    # past the ceiling were refused after 30.002 / 30.004 / 30.007 s. Shortening it would turn
    # served requests into refusals — at 45 concurrent borrowers holding 3 s each the last wave
    # waited up to 6.15 s and was still served — so the value stays and only its source changes.
    pool_timeout=30,
)

# What asyncpg raises for a socket the server closed between two statements. It is not a
# DBAPI error, so pre-ping cannot classify it as a disconnection and the checkout fails
# instead of retrying; measured after `pg_terminate_backend`, the failed borrow is the
# only one — the pool throws the poisoned connection away, so the next attempt is fine.
_DROPPED_CONNECTION = (
    asyncpg.exceptions.InterfaceError,
    asyncpg.exceptions._base.InternalClientError,
)


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class DatabaseUnavailable(RuntimeError):
    """No connection could be taken for this request.

    Raised from the dependency rather than left as whatever the driver said, so the API
    answers one thing — the database is not there — instead of a bare 500 whose text names
    the host and the user of the connection string.
    """


async def checkout_connection(session: AsyncSession) -> None:
    """Take a pooled connection, and take another one if the server dropped the first.

    Kept separate from the dependency so the recovery is testable against a pool the
    caller controls.
    """
    for attempt in (0, 1):
        try:
            await session.connection()
            return
        except _DROPPED_CONNECTION as error:
            if attempt:
                raise
            logger.warning(
                "discarded a database connection the server dropped (%s), retrying the checkout",
                type(error).__name__,
            )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session.

    The pooled connection is taken before the handler starts rather than at its first
    query, so a connection the server dropped costs a second attempt instead of a
    half-executed request. Without the eager borrow the same error surfaces from inside a
    handler, where nothing can retry it without running the request again.
    """
    session = AsyncSessionLocal()
    try:
        try:
            await checkout_connection(session)
        except Exception as error:
            logger.warning("no database connection for this request (%s)", type(error).__name__)
            raise DatabaseUnavailable from error
    except BaseException:
        await session.close()
        raise

    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
