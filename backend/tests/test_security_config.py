"""Security configuration guards: production must not run with weak JWT secrets."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_STRONG_A = "prod-access-secret-value-that-is-long-enough-1234567890"
_STRONG_B = "prod-refresh-secret-value-that-is-long-enough-0987654321"


def _settings(**overrides) -> Settings:
    base = {
        # A correctly configured production stand, so that each test below can be about
        # exactly one mistake.
        "ENVIRONMENT": "production",
        "JWT_SECRET": _STRONG_A,
        "JWT_REFRESH_SECRET": _STRONG_B,
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
        "CORS_ORIGINS": "https://befos.example.com",
        "DEBUG": "false",
        "DEMO_ENABLED": "false",
    }
    base.update(overrides)
    return Settings(**base)


def test_production_rejects_default_access_secret() -> None:
    with pytest.raises(ValidationError):
        _settings(JWT_SECRET="change-me-access-secret-key-min-32-chars")


def test_production_rejects_default_refresh_secret() -> None:
    with pytest.raises(ValidationError):
        _settings(JWT_REFRESH_SECRET="change-me-refresh-secret-key-min-32-chars")


def test_production_rejects_short_secret() -> None:
    with pytest.raises(ValidationError):
        _settings(JWT_SECRET="tooshort")


def test_production_rejects_identical_secrets() -> None:
    with pytest.raises(ValidationError):
        _settings(JWT_SECRET=_STRONG_A, JWT_REFRESH_SECRET=_STRONG_A)


def test_production_accepts_strong_distinct_secrets() -> None:
    s = _settings(CORS_ORIGINS="https://befos.example.com")
    assert s.is_production is True
    assert s.jwt_secret == _STRONG_A


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError):
        _settings(CORS_ORIGINS="*")


def test_production_rejects_plain_http_cors() -> None:
    with pytest.raises(ValidationError):
        _settings(CORS_ORIGINS="http://befos.example.com")


def test_development_allows_http_and_wildcard_cors() -> None:
    s = _settings(ENVIRONMENT="development", CORS_ORIGINS="http://localhost:8000,*")
    assert s.cors_origin_list == ["http://localhost:8000", "*"]


def test_development_allows_insecure_defaults() -> None:
    # Local dev must stay frictionless: placeholder secrets are allowed.
    s = _settings(
        ENVIRONMENT="development",
        JWT_SECRET="change-me-access-secret-key-min-32-chars",
        JWT_REFRESH_SECRET="change-me-refresh-secret-key-min-32-chars",
    )
    assert s.is_production is False


def test_production_rejects_the_demo_account() -> None:
    # README.md and DEMO.md print demo@befos.app / Demo12345. A deployment that keeps the
    # demo half of the seed switched on is publishing a shared login, so the switch being
    # off is not advice but a condition for starting.
    with pytest.raises(ValidationError, match="DEMO_ENABLED"):
        _settings(DEMO_ENABLED="true")


def test_production_rejects_debug() -> None:
    with pytest.raises(ValidationError, match="DEBUG"):
        _settings(DEBUG="true")


def test_production_rejects_the_database_this_repository_ships() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        _settings(DATABASE_URL="postgresql+asyncpg://befos:befos_password@localhost:5432/befos")


def test_production_rejects_the_shipped_password_even_on_another_host() -> None:
    # The check above compares whole URLs, and docker-compose.yml assembles a different one:
    # same password, host `postgres`. So the guard that matters is the password component,
    # not the string, otherwise a stand started from the shipped compose file passes.
    for url in (
        "postgresql+asyncpg://befos:befos_password@postgres:5432/befos",
        "postgresql+asyncpg://befos:befos%5Fpassword@db.internal:5432/befos",
        "postgresql://app:befos_password@10.0.0.5:5432/app",
    ):
        with pytest.raises(ValidationError, match="befos_password|development database password"):
            _settings(DATABASE_URL=url)


def test_production_accepts_a_database_with_its_own_password() -> None:
    s = _settings(
        DATABASE_URL="postgresql+asyncpg://befos_prod:S8tr0ngPassw0rdValue@db.internal:5432/befos"
    )
    assert s.is_production is True


def test_an_environment_nobody_spelled_right_is_refused() -> None:
    # Every guard above is behind `if not is_production`. A deployment that says PRODUCTION
    # with a trailing space still has to be production, and one that says anything else has
    # to fail out loud instead of quietly running the development rules.
    assert _settings(ENVIRONMENT=" PRODUCTION ").is_production is True
    for misspelled in ("prodction", "Productio", "live", "Продакшен"):
        with pytest.raises(ValidationError, match="ENVIRONMENT"):
            _settings(ENVIRONMENT=misspelled)


def test_staging_is_a_known_environment_and_keeps_development_rules() -> None:
    s = _settings(ENVIRONMENT="staging", JWT_SECRET="change-me-access-secret-key-min-32-chars")
    assert s.is_production is False


async def test_a_public_deployment_does_not_hand_out_the_route_map(monkeypatch) -> None:
    """``/docs`` and ``/openapi.json`` answer on the stand and are gone in production.

    The document lists every route that takes an object identifier with its parameter names,
    and `/docs` is a form that fires a request at any of them from the browser. That is the
    fastest way to read the contract while the app is being built and a gift to whoever is
    probing it once it is public, so all three surfaces are switched off together — and the
    root response stops pointing at a route that no longer exists.
    """
    import httpx

    import app.main as main

    async def _ask(app, path):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://stand.test"
        ) as ac:
            return await ac.get(path)

    monkeypatch.setattr(main, "settings", _settings())
    production_app = main.create_app()
    assert (await _ask(production_app, "/docs")).status_code == 404
    assert (await _ask(production_app, "/redoc")).status_code == 404
    assert (await _ask(production_app, "/openapi.json")).status_code == 404
    assert "docs" not in (await _ask(production_app, "/")).json(), "root advertises a closed route"

    monkeypatch.setattr(main, "settings", _settings(ENVIRONMENT="development"))
    dev_app = main.create_app()
    assert (await _ask(dev_app, "/docs")).status_code == 200
    assert (await _ask(dev_app, "/openapi.json")).status_code == 200
    assert "docs" in (await _ask(dev_app, "/")).json()


async def test_the_demo_switch_decides_whether_people_get_seeded(session) -> None:
    # The guard above refuses to start a production app with DEMO_ENABLED on, which only
    # means anything if the switch changes what the seed writes. It used to be read by
    # nothing: README told the operator to turn it off, and turning it off seeded the demo
    # account anyway. Catalogues still have to arrive — the app cannot run without the
    # interests, questions and activities — so the switch is about invented people only.
    from sqlalchemy import func, select

    from app.models import TestQuestion, User
    from app.seed import run_seed

    await run_seed(session, force=True)
    users = (await session.execute(select(func.count(User.id)))).scalar()
    questions = (await session.execute(select(func.count(TestQuestion.id)))).scalar()
    assert users == 0, f"DEMO_ENABLED=false still seeded {users} accounts"
    assert questions > 0, "the reference catalogue did not arrive with the switch off"


