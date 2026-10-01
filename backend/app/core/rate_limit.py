from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import settings
from app.core.exceptions import RateLimitedError


class SlidingWindowRateLimiter:
    """In-memory sliding-window limiter keyed by client identity.

    Suitable for a single-instance MVP deployment. For multi-instance
    deployments swap the backing store for Redis behind the same interface.
    """

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            raise RateLimitedError()
        bucket.append(now)

    def reset(self) -> None:
        self._hits.clear()


_default_limiter = SlidingWindowRateLimiter(settings.rate_limit_per_minute)
_auth_limiter = SlidingWindowRateLimiter(limit=20, window_seconds=60)


def reset_rate_limiters() -> None:
    """Clear all in-memory limiter state (used by the test suite)."""
    _default_limiter.reset()
    _auth_limiter.reset()


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return ip


async def rate_limit_dependency(request: Request) -> None:
    _default_limiter.check(_client_key(request))


async def auth_rate_limit_dependency(request: Request) -> None:
    """Stricter limit for auth endpoints to slow credential stuffing."""
    _auth_limiter.check(f"auth:{_client_key(request)}")
