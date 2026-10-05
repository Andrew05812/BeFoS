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


