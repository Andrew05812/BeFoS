"""Integration test fixtures.

Points the app at a dedicated ``befos_test`` database (created on the fly), builds the schema,
seeds the reference catalogues once per session, and wipes user-domain rows between tests so
each test starts from a clean state. Runs only as the single session on that database: a second
concurrent session is refused rather than allowed to corrupt results.

Refuses to start on a schema older than the models, too. ``create_all`` never alters an existing
table, so a reused ``befos_test`` keeps yesterday's columns and the run would report the stand as a
product regression; the check after ``create_all`` compares the models against the reflected schema
and exits, naming each difference by table and column.
"""

from __future__ import annotations

import asyncio
import os
import threading

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
from sqlalchemy import MetaData, UniqueConstraint, delete

_MAINT_DSN = f"postgresql://{_PG_USER}:{_PG_PASSWORD}@{_PG_HOST}:{_PG_PORT}/postgres"
_TEST_DSN = f"postgresql://{_PG_USER}:{_PG_PASSWORD}@{_PG_HOST}:{_PG_PORT}/{_TEST_DB}"


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


_TEST_DB_LOCK_KEY = 475001813


class _TestDatabaseLease:
    """Hold a Postgres advisory lock on the test database for the life of the session.

    The lock dies with the backend that holds it, so the connection has to stay open for the
    whole run. Keeping it means keeping an event loop that connection belongs to, and pytest
    gives every test its own — hence a dedicated thread with its own loop, which also lets the
    fixture stay synchronous.

    ``key`` is a parameter because the suite must be able to prove the mechanism refuses and
    releases without disturbing the lease the session itself is holding.
    """

    def __init__(self, key: int = _TEST_DB_LOCK_KEY) -> None:
        self._key = key
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._conn = None
        self._stopped = False

    def _call(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=30)

    async def _acquire(self) -> bool:
        self._conn = await asyncpg.connect(_TEST_DSN)
        return bool(await self._conn.fetchval("SELECT pg_try_advisory_lock($1)", self._key))

    def acquire(self) -> bool:
        return self._call(self._acquire())

    async def _unlock(self) -> None:
        if self._conn is None:
            return
        await self._conn.fetchval("SELECT pg_advisory_unlock($1)", self._key)
        await self._conn.close()
        self._conn = None

    def release(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        try:
            self._call(self._unlock())
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=10)


def _refuse_a_second_session(lease: "_TestDatabaseLease") -> bool:
    """Take the lease or end the run. Returns whether this session now holds it.

    Kept out of the fixture so the refusal is testable without spawning a second interpreter.
    """
    if lease.acquire():
        return True
    pytest.exit(
        f"another pytest session already holds {_TEST_DB}. Two sessions on one database wipe "
        "each other's domain rows through the `client` fixture, and the failures they report "
        "are not regressions. Wait for the first run to finish, or point this one at its own "
        "database: BEFOS_TEST_DB=befos_test_2 (its schema has to be recreated, because "
        "create_all never alters an existing table).",
        returncode=1,
    )
    return False  # not reached: pytest.exit raises


@pytest.fixture(scope="session", autouse=True)
def _single_session_on_this_database():
    """Refuse a second concurrent session instead of letting it corrupt the first.

    The ``client`` fixture deletes every domain table before each test, so two sessions pointed
    at the same database erase each other's rows mid-flight and report the result as failures
    that look exactly like regressions (measured on this tree: 13 failed / 229 passed for two
    overlapping runs against 245 passed for the same tree alone). A session-scoped advisory
    lock is scoped to one database and one backend, so whoever arrives second is turned away
    before it can wipe anything, with a message that names the cause.
    """
    lease = _TestDatabaseLease()
    _refuse_a_second_session(lease)
    try:
        yield
    finally:
        lease.release()


def _unique_keys(table) -> dict[str, frozenset[str]]:
    """Map each named unique constraint of this table to the columns it covers."""
    return {
        constraint.name: frozenset(col.name for col in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint) and constraint.name
    }


def _index_names(table) -> set[str]:
    """Names of the indexes the table asks for.

    Only the names are compared, never their columns: `ix_profiles_deck_order` is built on the
    expression `created_at DESC`, which the model side reports as no column at all and the
    database side reports as `created_at`, so a column comparison there is a false accusation.
    """
    return {index.name for index in table.indexes if index.name}


def _drift_between(models, live) -> list[str]:
    """Compare the models with a reflected schema and name every difference, table by table.

    Pure on purpose: the session can be proved honest against a real database, and the shape of
    a refusal can be proved without wrecking a database to draw it.
    """
    problems: list[str] = []
    for name in sorted(models.tables):
        model, seen = models.tables[name], live.tables.get(name)
        if seen is None:
            problems.append(f"{name}: the table is not there at all")
            continue
        for column in sorted({c.name for c in model.columns} - {c.name for c in seen.columns}):
            problems.append(f"{name}.{column}: the column is missing")
        for column in sorted({c.name for c in seen.columns} - {c.name for c in model.columns}):
            problems.append(
                f"{name}.{column}: the stand holds a column no model declares"
            )
        want, have = _unique_keys(model), _unique_keys(seen)
        for key in sorted(set(want) - set(have)):
            problems.append(f"{name}: unique key {key} over {sorted(want[key])} is missing")
        for key in sorted(set(have) - set(want)):
            problems.append(f"{name}: unique key {key} exists that no model declares")
        for key in sorted(set(want) & set(have)):
            if want[key] != have[key]:
                problems.append(
                    f"{name}: unique key {key} covers {sorted(have[key])}, the models ask for "
                    f"{sorted(want[key])}"
                )
        for index in sorted(_index_names(model) - _index_names(seen) - set(have)):
            problems.append(f"{name}: index {index} is missing")
    for name in sorted(set(live.tables) - set(models.tables)):
        if name != "alembic_version":
            problems.append(f"{name}: a table the models no longer declare")
    return problems


def _schema_drift(sync_conn) -> list[str]:
    """Reflect the stand's schema and return what it lacks compared with the models."""
    live = MetaData()
    live.reflect(bind=sync_conn)
    return _drift_between(Base.metadata, live)


def _refuse_a_stale_schema(problems: list[str]) -> bool:
    """End the run on a stand whose schema predates the models. Returns whether it may go on.

    ``create_all`` only adds tables that are absent; it never alters one that exists. So a
    database left by an earlier stage keeps its old shape, and every test that touches what a
    later stage added fails on the endpoint instead — which reads as a product regression.
    Measured on 2026-10-11 on a stand from before stage 63: 11 failed and 4 errors across an
    11-minute run, all of them in the recommendation family, the first of them
    ``UndefinedColumnError: column activity_preferences.match_id does not exist``, while the
    same seven files on a freshly built stand passed 59 in 134 s.
    """
    if not problems:
        return True
    listed = "\n  ".join(problems)
    pytest.exit(
        f"{_TEST_DB} holds a schema older than the models, and create_all never alters an "
        "existing table, so this run would report the stand as a product regression. "
        f"Build the stand again — drop the database, or run against a name of your own: "
        f"BEFOS_TEST_DB=befos_test_2. What disagrees:\n  {listed}",
        returncode=1,
    )
    return False  # not reached: pytest.exit raises


@pytest.fixture(scope="session", autouse=True)
def _prepare_database(_single_session_on_this_database):
    """Create the schema, refuse it if it was already there in an older shape, seed catalogues.

    The engine is disposed at the end so no connection is bound to this loop;
    each test then opens fresh connections on its own function-scoped loop.
    """

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            problems = await conn.run_sync(_schema_drift)
        _refuse_a_stale_schema(problems)
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
