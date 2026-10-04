from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from app.core.logging import get_logger

logger = get_logger("analytics")


class AnalyticsBackend(Protocol):
    def track(self, event: str, user_id: str | None, props: dict[str, Any]) -> None: ...


@dataclass
class LogAnalyticsBackend:
    """Default backend: structured logs only. No external analytics is sent,
    keeping the abstraction honest (nothing pretends to reach a 3rd party)."""

    def track(self, event: str, user_id: str | None, props: dict[str, Any]) -> None:
        logger.info("analytics event=%s user=%s props=%s", event, user_id or "anon", props)


class Event:
    ONBOARDING_COMPLETED = "onboarding_completed"
    PROFILE_COMPLETED = "profile_completed"
    TEST_STARTED = "test_started"
    TEST_COMPLETED = "test_completed"
    PROFILE_VIEWED = "profile_viewed"
    DISCOVERY_FEED = "discovery_feed"
    LIKE = "like"
    PASS = "pass"
    MATCH = "match"
    MESSAGE_SENT = "message_sent"
    RECOMMENDATION_VIEWED = "recommendation_viewed"
    RECOMMENDATION_SELECTED = "recommendation_selected"


@dataclass
class AnalyticsTracker:
    backend: AnalyticsBackend = field(default_factory=LogAnalyticsBackend)

    def track(self, event: str, user_id: str | None = None, **props: Any) -> None:
        try:
            self.backend.track(event, user_id, {**props, "ts": datetime.now(timezone.utc).isoformat()})
        except Exception:  # analytics must never break the request path
            logger.warning("analytics backend failed for event=%s", event, exc_info=True)


tracker = AnalyticsTracker()
