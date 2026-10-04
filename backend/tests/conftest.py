"""Integration test fixtures.

Points the app at a dedicated ``befos_test`` database (created on the fly),
builds the schema, seeds the reference catalogues once per session, and wipes
user-domain rows between tests so each test starts from a clean state.
"""

from __future__ import annotations

import asyncio
import os

# Test database location. Defaults to the Docker Compose postgres published on
# localhost:5432 so `pytest` runs against the same runtime as the app. Override
# via BEFOS_TEST_PG_* env vars to point at another cluster (e.g. a bare-metal
# PostgreSQL on 5433).
_PG_HOST = os.environ.get("BEFOS_TEST_PG_HOST", "localhost")
_PG_PORT = os.environ.get("BEFOS_TEST_PG_PORT", "5432")
_PG_USER = os.environ.get("BEFOS_TEST_PG_USER", "befos")
_PG_PASSWORD = os.environ.get("BEFOS_TEST_PG_PASSWORD", "befos_password")
_TEST_DB = os.environ.get("BEFOS_TEST_DB", "befos_test")

# Must be set before any app module is imported so Settings picks it up.
os.environ["DATABASE_URL"] = (
    f"postgresql+asyncpg://{_PG_USER}:{_PG_PASSWORD}@{_PG_HOST}:{_PG_PORT}/{_TEST_DB}"
)
os.environ.setdefault("DEMO_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "100000")

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

_MAINT_DSN = f"postgresql://{_PG_USER}:{_PG_PASSWORD}@{_PG_HOST}:{_PG_PORT}/postgres"


def _ensure_test_database() -> None:
    async def _run() -> None:
        conn = await asyncpg.connect(_MAINT_DSN)
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", _TEST_DB
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE {_TEST_DB} OWNER {_PG_USER}')
        finally:
            await conn.close()

    asyncio.run(_run())


_ensure_test_database()

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.core.rate_limit import reset_rate_limiters  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import (  # noqa: E402
    Block,
    CompatibilityProfile,
    DiscoveryQueue,
    Like,
    Match,
    Message,
    MessageRead,
    Pass,
    Photo,
    Profile,
    Recommendation,
    RefreshToken,
    Report,
    TestAnswer,
    TestResult,
    User,
)
from app.seed import _seed_catalogs  # noqa: E402

_DOMAIN_MODELS = (
    DiscoveryQueue,
    MessageRead,
    Message,
    Recommendation,
    Match,
    Report,
    Block,
    Pass,
    Like,
    TestAnswer,
    TestResult,
    CompatibilityProfile,
    Photo,
    Profile,
    RefreshToken,
    User,
)


@pytest.fixture(scope="session", autouse=True)
def _prepare_database():
    """Create the schema and seed reference catalogues once, in a throwaway loop.

    The engine is disposed at the end so no connection is bound to this loop;
    each test then opens fresh connections on its own function-scoped loop.
    """

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with AsyncSessionLocal() as db:
            await _seed_catalogs(db)
            await db.commit()
        await engine.dispose()

    asyncio.run(_setup())
    yield


@pytest_asyncio.fixture
async def session():
    async with AsyncSessionLocal() as db:
        yield db
    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    reset_rate_limiters()
    async with AsyncSessionLocal() as db:
        for model in _DOMAIN_MODELS:
            await db.execute(delete(model))
        await db.commit()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await engine.dispose()


async def register_and_auth(client: AsyncClient, email: str, password: str = "Test12345") -> dict:
    """Register a user and return ``{"token", "refresh", "user_id", "email"}``."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "password_confirm": password},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {
        "token": data["tokens"]["access_token"],
        "refresh": data["tokens"]["refresh_token"],
        "user_id": data["user"]["id"],
        "email": data["user"]["email"],
    }


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def complete_onboarding(
    client: AsyncClient,
    token: str,
    *,
    name: str = "Тест",
    city: str = "Москва",
    gender: str = "male",
    goal: str = "relationship",
    birth_date: str = "1996-05-10",
    interests: list[str] | None = None,
) -> None:
    resp = await client.get("/api/v1/users/interests", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    catalog = resp.json()
    items = catalog if isinstance(catalog, list) else catalog.get("interests", [])
    slugs = interests or [i["slug"] for i in items][:6]
    payload = {
        "name": name,
        "birth_date": birth_date,
        "city": city,
        "gender": gender,
        "about": "Интеграционный тест",
        "dating_goal": goal,
        "interests": slugs,
        "lifestyle": {"smoking": "never", "alcohol": "rarely", "sport": "often"},
        "age_min": 20,
        "age_max": 45,
        "gender_preference": ["female", "male", "nonbinary", "other"],
    }
    resp = await client.post(
        "/api/v1/users/me/onboarding", json=payload, headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text


async def answer_all_questions(client: AsyncClient, token: str, option_index: int = 0) -> None:
    resp = await client.get("/api/v1/tests", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    questions = resp.json()["questions"]
    answers = [
        {"question_id": q["id"], "option_id": q["options"][option_index]["id"]}
        for q in questions
    ]
    resp = await client.post(
        "/api/v1/tests/answers",
        json={"answers": answers},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/v1/tests/complete", json={}, headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
