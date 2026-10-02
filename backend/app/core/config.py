from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Known-insecure placeholder secrets shipped for local development only.
_INSECURE_DEFAULTS = {
    "change-me-access-secret-key-min-32-chars",
    "change-me-refresh-secret-key-min-32-chars",
}
_MIN_SECRET_LEN = 32


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

    database_url: str = Field(
        default="postgresql+asyncpg://befos:befos_password@localhost:5432/befos",
        alias="DATABASE_URL",
    )

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

    demo_enabled: bool = Field(default=True, alias="DEMO_ENABLED")
    demo_email: str = Field(default="demo@befos.app", alias="DEMO_EMAIL")
    demo_password: str = Field(default="Demo12345", alias="DEMO_PASSWORD")

    @field_validator("cors_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

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
