from __future__ import annotations

import logging
import re
import sys

from app.core.config import settings
from app.core.context import request_id

_CONFIGURED = False

# The socket handshake authorises with ?token=<jwt>, so uvicorn's own connection line
# echoes a live access token. A record of the request is useful; the credential is not.
_REDACT = re.compile(
    r"""(?i)
    (?P<q>\b(?:access_token|refresh_token|token|password|secret|authorization)=)(?P<qv>[^\s&"']+)
    | "(?P<k>access_token|refresh_token|token|password|secret|authorization)"\s*:\s*"(?P<kv>[^"]*)"
    """,
    re.VERBOSE,
)


def redact(text: str) -> str:
    def swap(match: re.Match[str]) -> str:
        if match.group("q"):
            return match.group("q") + "[redacted]"
        return '"%s": "[redacted]"' % match.group("k")

    return _REDACT.sub(swap, text)


class SensitiveFilter(logging.Filter):
    """Redacts secrets/tokens that must never reach the logs, keeping the rest of the line."""

    def filter(self, record: logging.LogRecord) -> bool:
        text = record.getMessage()
        scrubbed = redact(text)
        if scrubbed != text:
            record.msg = scrubbed
            record.args = ()
        return True


class RequestIdFilter(logging.Filter):
    """Puts the current correlation id on every record, so lines of one request sort together."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get() or "-"
        return True


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = logging.DEBUG if settings.debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(request_id)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(SensitiveFilter())
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn installs handlers on its own loggers and does not propagate, which is how
    # its lines escaped the filter above.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
