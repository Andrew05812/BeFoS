from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request, WebSocket

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
        if not self.allow(key):
            raise RateLimitedError()

    def allow(self, key: str) -> bool:
        """Count one hit and report whether it is inside the window.

        The HTTP routes want an exception, the WebSocket gateway wants a boolean it can act on
        without unwinding a long-lived connection through the REST error handler, so both read
        the same window through this one method.
        """
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
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
        return True

    def reset(self) -> None:
        self._hits.clear()


_default_limiter = SlidingWindowRateLimiter(settings.rate_limit_per_minute)
_auth_limiter = SlidingWindowRateLimiter(limit=20, window_seconds=60)
_probe_limiter = SlidingWindowRateLimiter(limit=60, window_seconds=60)
# A socket is one handshake and then an unbounded number of frames, so it needs two windows of
# its own: one per address at the door, one per account across the life of the connection.
_ws_handshake_limiter = SlidingWindowRateLimiter(limit=30, window_seconds=60)
_ws_frame_limiter = SlidingWindowRateLimiter(limit=settings.rate_limit_per_minute, window_seconds=60)


def reset_rate_limiters() -> None:
    """Clear all in-memory limiter state (used by the test suite)."""
    _default_limiter.reset()
    _auth_limiter.reset()
    _probe_limiter.reset()
    _ws_handshake_limiter.reset()
    _ws_frame_limiter.reset()


def _client_key(client: Request | WebSocket) -> str:
    """Identify the caller by the peer address of the TCP connection.

    ``X-Forwarded-For`` is attacker-controlled: trusting it unconditionally lets anyone
    rotate the header and get a fresh bucket per request, which walks straight past the
    limit this exists to enforce. It is read only when the deployment declares that a
    proxy in front of the app overwrites it.
    """
    if settings.trust_proxy_headers:
        forwarded = client.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return client.client.host if client.client else "unknown"


async def rate_limit_dependency(request: Request) -> None:
    _default_limiter.check(_client_key(request))


async def auth_rate_limit_dependency(request: Request) -> None:
    """Stricter limit for auth endpoints to slow credential stuffing."""
    _auth_limiter.check(f"auth:{_client_key(request)}")


async def probe_rate_limit_dependency(request: Request) -> None:
    """Its own bucket for the readiness probe that opens a database connection.

    `/health` stays unthrottled because a monitor that gets a 429 reports an outage that
    is not happening. `/health/db` is a different cost — every call borrows a connection
    from the pool that authenticated traffic shares — so an anonymous loop against it can
    starve real requests. Sixty a minute is far above what any sane alerter polls (see
    `docs/OPERATIONS.md`) and far below what a flood looks like.
    """
    _probe_limiter.check(f"probe:{_client_key(request)}")


def websocket_handshake_allowed(websocket: WebSocket) -> bool:
    return _ws_handshake_limiter.allow(f"ws-handshake:{_client_key(websocket)}")


def websocket_frame_allowed(user_id: object) -> bool:
    """Keyed by the authenticated account, not the address.

    One account with several tabs, or one household behind one NAT, must not consume each
    other's budget; the frame budget belongs to whoever is writing.
    """
    return _ws_frame_limiter.allow(f"ws-frame:{user_id}")
