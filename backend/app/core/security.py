from __future__ import annotations

import asyncio
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


# A refusal to sign in should not say whether the email exists. Skipping the password check when no
# account was found made the two refusals differ by an order of magnitude in wall time (measured
# over a socket against one worker: 24.7 ms for an unknown address, 476.1 ms for a wrong password
# on a known one), so the clock alone enumerated accounts. This hash is what an unknown address is
# checked against instead: same algorithm, same cost factor, so the check costs what a stored hash
# costs. Its plaintext is published next to it because it guards no account —
# `AuthService.authenticate` refuses a missing user whatever this check returns, so knowing the
# preimage buys nothing.
TIMING_FILLER_PASSWORD = "befos-timing-filler"
TIMING_FILLER_HASH = "$2b$12$7YckIb7gRVarLlFGn0Ue.u89ES/TUakO/CJbNtZmuxfTaLk.r/owm"


async def hash_password_async(password: str) -> str:
    """`hash_password` on a worker thread, because at rounds=12 it is a synchronous CPU burn.

    Measured on one machine, a hash or a verify costs 451-468 ms. Called from an `async def`,
    that time belongs to the event loop of the only worker the app runs, so no other request on
    it can be scheduled: over a socket a bystander that normally answers in 24.1 ms waited 253.8 ms
    at one login's median and 496.6 ms at the worst in that window, and only two of them got
    answered there. On a thread the same window answers 21-22 with a 24.1 ms median and none of 107
    over 100 ms, while the login itself is unchanged (492.5 ms median on the loop, 505.1 ms on the
    thread). Both halves of that pair drop the probe's first repeat as warm-up and aggregate the
    five that follow, which is the same rule the bystander tallies above use. bcrypt releases the
    GIL, which is why the thread gets the loop back rather than trading it for a queue. The sync
    pair stays for scripts (`seed.py`) with no loop to protect.
    """
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, password_hash: str) -> bool:
    """`verify_password` on a worker thread; see `hash_password_async` for the measurement."""
    return await asyncio.to_thread(verify_password, password, password_hash)


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
