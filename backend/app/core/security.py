from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt. Never store plaintext."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _secret_for(token_type: TokenType) -> str:
    return settings.jwt_secret if token_type == "access" else settings.jwt_refresh_secret


def _expire_for(token_type: TokenType) -> datetime:
    now = datetime.now(timezone.utc)
    if token_type == "access":
        return now + timedelta(minutes=settings.access_token_expire_minutes)
    return now + timedelta(days=settings.refresh_token_expire_days)


def create_token(subject: str | int, token_type: TokenType, extra: dict[str, Any] | None = None) -> tuple[str, datetime]:
    """Create a signed JWT. Returns (token, expires_at)."""
    expires_at = _expire_for(token_type)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": datetime.now(timezone.utc),
        "exp": expires_at,
        "jti": secrets.token_urlsafe(16),
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, _secret_for(token_type), algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_token(token: str, token_type: TokenType) -> dict[str, Any]:
    """Decode and validate a JWT. Raises jwt.PyJWTError on any problem."""
    return jwt.decode(
        token,
        _secret_for(token_type),
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub", "type"]},
    )


def generate_token_hash(token: str) -> str:
    """Store refresh tokens hashed (SHA-256), never in plaintext."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
