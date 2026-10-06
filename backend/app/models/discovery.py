from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
)
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
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(8), default=READY, nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Named for the upsert that leans on it (`ON CONFLICT` needs a constraint name)
        # and declared as the primary key rather than as a second unique constraint over
        # the same columns: Postgres promotes the unique index to the primary key, and a
        # separate UniqueConstraint here would make `alembic check` report drift forever.
        PrimaryKeyConstraint("viewer_id", "candidate_id", name="uq_discovery_queue_pair"),
        CheckConstraint(
            "status in ('ready', 'seen')",
            name="ck_discovery_queue_status",
        ),
        # The paging read: ready rows of one viewer, in deck order, past a cursor.
        Index("ix_discovery_queue_viewer_status_rank", "viewer_id", "status", "rank"),
        # A rank is a position in a cursor, and the cursor advances with `rank > :after`.
        # Two refills running at once both read `max(rank) + 1` as their ceiling, and when
        # the candidate sets they picked differ by one row — somebody hid, somebody new
        # joined — the second batch lands a fresh candidate on a rank the first batch
        # already used. Both rows then sit behind the same cursor step and only one of them
        # is ever claimed: the other is a person who silently vanishes from the deck. The
        # pair constraint cannot see this, because the two rows are different pairs.
        Index("uq_discovery_queue_viewer_rank", "viewer_id", "rank", unique=True),
    )
