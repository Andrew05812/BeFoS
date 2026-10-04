from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Index, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import utcnow

READY = "ready"
SEEN = "seen"


class DiscoveryQueue(Base):
    """One row per (viewer, candidate) the discovery deck has ever offered.

    The deck is what makes paging stable: ``rank`` is assigned once, when the
    candidate is appended, and never reassigned, so a cursor can be a rank and a
    page cannot shift under a viewer who likes or passes between requests.
    ``status`` keeps the two questions the feed asks apart — "may I show this
    again?" (no row, or a ready row) and "have I already seen this?" (a seen
    row, which is the deduplication memory that survives a deck rebuild).
    """

    __tablename__ = "discovery_queue"

    viewer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(8), default=READY, nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("viewer_id", "candidate_id", name="uq_discovery_queue_pair"),
        CheckConstraint(
            "status in ('ready', 'seen')",
            name="ck_discovery_queue_status",
        ),
        # The paging read: ready rows of one viewer, in deck order, past a cursor.
        Index("ix_discovery_queue_viewer_status_rank", "viewer_id", "status", "rank"),
    )
