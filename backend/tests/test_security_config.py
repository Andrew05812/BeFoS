"""Security configuration guards: production must not run with weak JWT secrets."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_STRONG_A = "prod-access-secret-value-that-is-long-enough-1234567890"
_STRONG_B = "prod-refresh-secret-value-that-is-long-enough-0987654321"


def _settings(**overrides) -> Settings:
    base = {
        "ENVIRONMENT": "production",
        "JWT_SECRET": _STRONG_A,
        "JWT_REFRESH_SECRET": _STRONG_B,
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
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
    s = _settings()
    assert s.is_production is True
    assert s.jwt_secret == _STRONG_A


def test_development_allows_insecure_defaults() -> None:
    # Local dev must stay frictionless: placeholder secrets are allowed.
    s = _settings(
        ENVIRONMENT="development",
        JWT_SECRET="change-me-access-secret-key-min-32-chars",
        JWT_REFRESH_SECRET="change-me-refresh-secret-key-min-32-chars",
    )
    assert s.is_production is False
