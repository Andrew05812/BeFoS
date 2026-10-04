from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal, checkout_connection
from app.core.logging import get_logger

router = APIRouter(tags=["health"])
logger = get_logger("health")


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@router.get("/health/db")
async def health_db():
    """Ask the database whether it is there, and answer the way a probe needs.

    A probe that replies 200 while the database is down is worse than no probe at all:
    the container reads healthy, so the traffic keeps arriving and every real request
    fails. The error text stays out of the response for a second reason — it names the
    host and the user of the connection string, and this route answers unauthenticated.

    The session is taken here rather than through the request dependency so the probe
    reports one shape whether the borrow or the query fails, and still answers when the
    dependency pipeline is what is broken. It borrows through the same helper the
    requests use, so a connection the server dropped costs the probe a retry rather than
    an unhealthy reading the traffic never needed.
    """
    session = AsyncSessionLocal()
    try:
        await checkout_connection(session)
        await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("database probe failed")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "database": "unavailable"},
        )
    finally:
        await session.close()
    return {"status": "ok", "database": "connected"}
