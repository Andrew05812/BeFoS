from __future__ import annotations

import logging
import sys

from app.core.config import settings

_CONFIGURED = False


class SensitiveFilter(logging.Filter):
    """Redact secrets/tokens that must never reach the logs."""

    _KEYS = ("password", "token", "access_token", "refresh_token", "authorization", "secret")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage().lower()
        for key in self._KEYS:
            if f"{key}=" in msg or f'"{key}"' in msg:
                record.msg = "[redacted sensitive log]"
                record.args = ()
                break
        return True


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = logging.DEBUG if settings.debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(SensitiveFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
