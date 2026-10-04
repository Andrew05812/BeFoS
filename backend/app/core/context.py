"""The correlation id that every log line of one request shares."""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

request_id: ContextVar[str] = ContextVar("befos_request_id", default="")

# An inbound id is adopted only if it is printable on a single line. A caller that sends
# CR/LF, an ANSI escape, or a few kilobytes would otherwise write a forged record — or a
# megabyte of noise — straight into the log stream.
_INBOUND = re.compile(r"\A[A-Za-z0-9_.-]{1,64}\Z")


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def adopt_inbound(value: str | None) -> str:
    return value if value is not None and _INBOUND.match(value) else new_request_id()
