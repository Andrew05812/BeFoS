from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import settings
from app.core.exceptions import RateLimitedError

# Bucket keys come straight off the network, so the store must stay bounded even when a
# caller invents a new client identity per request.
_MAX_KEYS = 4096


class SlidingWindowRateLimiter:
    """In-memory sliding-window limiter keyed by client identity.

    Suitable for a single-instance MVP deployment. For multi-instance
    deployments swap the backing store for Redis behind the same interface.
    """

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._swept_at = 0.0

    def check(self, key: str) -> None:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            raise RateLimitedError()
        bucket.append(now)
        if len(self._hits) > _MAX_KEYS:
            # A limiter whose state grows with every identity it has ever seen is a memory
            # leak whose size the caller controls. Idle buckets are dead weight; when the
            # store is still over budget the oldest identities make room for the newest.
            if now - self._swept_at > self.window:
                self._swept_at = now
                for stale in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    self._hits.pop(stale, None)
            while len(self._hits) > _MAX_KEYS:
                self._hits.pop(next(iter(self._hits)), None)

    def reset(self) -> None:
        self._hits.clear()


_default_limiter = SlidingWindowRateLimiter(settings.rate_limit_per_minute)
_auth_limiter = SlidingWindowRateLimiter(limit=20, window_seconds=60)


def reset_rate_limiters() -> None:
    """Clear all in-memory limiter state (used by the test suite)."""
    _default_limiter.reset()
    _auth_limiter.reset()


def _client_key(request: Request) -> str:
    """Identify the caller by the peer address of the TCP connection.

    ``X-Forwarded-For`` is attacker-controlled: trusting it unconditionally lets anyone
    rotate the header and get a fresh bucket per request, which walks straight past the
    limit this exists to enforce. It is read only when the deployment declares that a
    proxy in front of the app overwrites it.
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"



async def rate_limit_dependency(request: Request) -> None:
    _default_limiter.check(_client_key(request))


async def auth_rate_limit_dependency(request: Request) -> None:
    """Stricter limit for auth endpoints to slow credential stuffing."""
    _auth_limiter.check(f"auth:{_client_key(request)}")
