from __future__ import annotations

from functools import lru_cache
from urllib.parse import unquote, urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Known-insecure placeholder secrets shipped for local development only.
_INSECURE_DEFAULTS = {
    "change-me-access-secret-key-min-32-chars",
    "change-me-refresh-secret-key-min-32-chars",
}
# The password the development database of this repository is created with. It is printed
# in .env.example, in docker-compose.yml as a default, and in the README's local-run steps,
# so a deployment that kept it has a database password anybody with the repository knows.
_INSECURE_DB_PASSWORDS = {"befos_password"}
_MIN_SECRET_LEN = 32
# The deployment reads as production only when it says so in one of these two words. A
# typo here silently turns every guard below off, so an unknown value is a startup error.
_KNOWN_ENVIRONMENTS = {"development", "dev", "test", "staging", "production", "prod"}
_DEFAULT_DATABASE_URL = "postgresql+asyncpg://befos:befos_password@localhost:5432/befos"


def _database_password(database_url: str) -> str | None:
    """The password component of a DSN, or None when there is nothing to compare.

    A DSN this function cannot read is not a security question: asyncpg fails on it when
    the app first tries to connect, and refusing startup here would turn a typo in a
    password containing '@' into a mystery.
    """
    try:
        password = urlsplit(database_url).password
    except ValueError:
        return None
    if password is None:
        return None
    return unquote(password)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = Field(default="BeFoS", alias="APP_NAME")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=True, alias="DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    backend_host: str = Field(default="0.0.0.0", alias="BACKEND_HOST")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")

    database_url: str = Field(default=_DEFAULT_DATABASE_URL, alias="DATABASE_URL")

    jwt_secret: str = Field(default="change-me-access-secret-key-min-32-chars", alias="JWT_SECRET")
    jwt_refresh_secret: str = Field(
        default="change-me-refresh-secret-key-min-32-chars", alias="JWT_REFRESH_SECRET"
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=30, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    cors_origins: str = Field(default="http://localhost:8000", alias="CORS_ORIGINS")

    upload_dir: str = Field(default="./uploads", alias="UPLOAD_DIR")
    max_upload_size_mb: int = Field(default=5, alias="MAX_UPLOAD_SIZE_MB")

    rate_limit_per_minute: int = Field(default=120, alias="RATE_LIMIT_PER_MINUTE")
    # Only enable when a reverse proxy in front of the app sets X-Forwarded-For.
    trust_proxy_headers: bool = Field(default=False, alias="TRUST_PROXY_HEADERS")

    demo_enabled: bool = Field(default=True, alias="DEMO_ENABLED")
    demo_email: str = Field(default="demo@befos.app", alias="DEMO_EMAIL")
    demo_password: str = Field(default="Demo12345", alias="DEMO_PASSWORD")

    @field_validator("cors_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("environment")
    @classmethod
    def _known_environment(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if cleaned not in _KNOWN_ENVIRONMENTS:
            raise ValueError(
                f"ENVIRONMENT={v!r} is not one of {sorted(_KNOWN_ENVIRONMENTS)}. A value that "
                "is not understood reads as 'not production', which is how every production "
                "guard below gets skipped by a typo."
            )
        return cleaned

    @model_validator(mode="after")
    def _reject_insecure_production_secrets(self) -> "Settings":
        """Fail fast if production runs with placeholder/short JWT secrets.

        Forgery of access/refresh tokens is trivial with the shipped defaults, so
        a production deployment must override them with strong values.
        """
        if not self.is_production:
            return self
        for name, value in (
            ("JWT_SECRET", self.jwt_secret),
            ("JWT_REFRESH_SECRET", self.jwt_refresh_secret),
        ):
            if value in _INSECURE_DEFAULTS or len(value) < _MIN_SECRET_LEN:
                raise ValueError(
                    f"{name} must be a strong secret (>= {_MIN_SECRET_LEN} chars, not the "
                    "development placeholder) when ENVIRONMENT=production."
                )
        if self.jwt_secret == self.jwt_refresh_secret:
            raise ValueError("JWT_SECRET and JWT_REFRESH_SECRET must differ in production.")
        if "*" in self.cors_origin_list:
            raise ValueError("CORS_ORIGINS must not contain '*' in production.")
        if any(o.startswith("http://") for o in self.cors_origin_list):
            raise ValueError("CORS_ORIGINS must use https:// in production.")
        if self.database_url == _DEFAULT_DATABASE_URL:
            raise ValueError(
                "DATABASE_URL still points at the development database shipped in this "
                "repository; production must name its own."
            )
        db_password = _database_password(self.database_url)
        if db_password in _INSECURE_DB_PASSWORDS:
            # Comparing the whole URL, as the check above does, is not enough: the URL
            # docker-compose.yml assembles is `...@postgres:5432/befos`, which differs from
            # the literal in this file while carrying the same shipped password.
            raise ValueError(
                "DATABASE_URL still carries the development database password this "
                "repository ships ('befos_password'). docker-compose.yml builds the URL from "
                "${POSTGRES_PASSWORD:-befos_password}, so a stand started from that file as "
                "is gives a production app a database password anybody who read the "
                "repository can use."
            )
        if self.debug:
            raise ValueError(
                "DEBUG must be false in production. It drops the root log level to DEBUG, "
                "and third-party loggers then write their own internals into the same "
                "stream (asyncio's transport setup, httpx's per-request lines — both visible "
                "in the development stand's logs)."
            )
        if self.demo_enabled:
            raise ValueError(
                "DEMO_ENABLED must be false in production. The demo account's password is "
                "printed in README.md and DEMO.md, so a seeded demo login is a shared "
                "credential anybody with the repository can use."
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
