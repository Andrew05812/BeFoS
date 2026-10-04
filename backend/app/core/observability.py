"""One line per request: what was asked, what it cost, and the id the rest of the work shares."""

from __future__ import annotations

import time

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import adopt_inbound, request_id
from app.core.logging import get_logger

logger = get_logger("befos.access")

HEADER = "X-Request-Id"
SLOW_MS = 1000.0
# A liveness probe is asked thousands of times a day; keeping it out of the info stream
# is what makes the rest of it readable.
_QUIET_PATHS = ("/api/v1/health",)


class RequestContextMiddleware:
    """Assigns a correlation id, puts it on the response, and times the request.

    Pure ASGI instead of ``BaseHTTPMiddleware``: the request must reach the endpoint
    without a task group in between, and the WebSocket route has to pass through this
    layer untouched — a streaming middleware that reads the body breaks the socket
    handshake it is standing in front of.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        rid = adopt_inbound(Headers(scope=scope).get(HEADER))
        # The query string is deliberately absent: the socket handshake carries its
        # credential there, and a path plus an id is enough to find the rest.
        target = f"{scope['method']} {scope['path']}"
        started = time.perf_counter()
        status = 500

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                nonlocal status
                status = message["status"]
                MutableHeaders(raw=message["headers"])[HEADER] = rid
            await send(message)

        token = request_id.set(rid)
        try:
            try:
                await self.app(scope, receive, send_with_id)
            finally:
                elapsed_ms = (time.perf_counter() - started) * 1000
                line = f"{target} -> {status} in {elapsed_ms:.1f} ms"
                quiet = scope["path"].startswith(_QUIET_PATHS)
                # Logged while the id is still current: this line is the one an operator
                # searches by, and an access log stamped "-" ties nothing to anything.
                if elapsed_ms >= SLOW_MS and not quiet:
                    logger.warning("slow request %s", line)
                elif not quiet:
                    logger.info("request %s", line)
                else:
                    logger.debug("request %s", line)
        finally:
            request_id.reset(token)
