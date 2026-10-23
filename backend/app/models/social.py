from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, utcnow
from app.models.enums import ReportStatus


class Like(TimestampMixin, Base):
    __tablename__ = "likes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    from_user_id: Mapped[uuid.UUID] = mapped_column(
        # uq_like_pair already covers from_user_id as its leading column.
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    to_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    compatibility_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("from_user_id", "to_user_id", name="uq_like_pair"),
        CheckConstraint("from_user_id <> to_user_id", name="ck_like_not_self"),
        # The account's own list is walked newest-first and continues after a `(created_at, id)` pair,
        # so the order belongs in the key. `uq_like_pair` starts with `from_user_id` and answers the
        # predicate, then leaves the sort to the reader: measured over the walk this stage priced, a
        # page cost 27.2 мс at 88 taps, 37.7 мс at 893 and 61.2 мс at 4 493 of the same reader's taps
        # (`s123_pages.json`) — the shape of a read that walks the whole history before it takes its
        # fifty rows. `created_at` and `id` are both NOT NULL, so the direction is the only thing the
        # key is choosing, and the whole list belongs in it: the exclusions this read puts on a row
        # (hidden, deleted, deactivated, a pair, a block) live in the tables it joins, and an index
        # predicate cannot reach into another table.
        Index(
            "ix_likes_tapper_order",
            "from_user_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
    )


class Pass(TimestampMixin, Base):
    __tablename__ = "passes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    from_user_id: Mapped[uuid.UUID] = mapped_column(
        # uq_pass_pair already covers from_user_id as its leading column.
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    to_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint("from_user_id", "to_user_id", name="uq_pass_pair"),
        CheckConstraint("from_user_id <> to_user_id", name="ck_pass_not_self"),
    )


class Match(TimestampMixin, Base):
    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # user_a_id is always the lexicographically smaller UUID to keep pairs unique.
    user_a_id: Mapped[uuid.UUID] = mapped_column(
        # uq_match_pair already covers user_a_id as its leading column.
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    user_b_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    compatibility_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="match", cascade="all, delete-orphan", order_by="Message.created_at"
    )

    __table_args__ = (
        UniqueConstraint("user_a_id", "user_b_id", name="uq_match_pair"),
        CheckConstraint("user_a_id <> user_b_id", name="ck_match_not_self"),
    )

    def other_user(self, user_id: uuid.UUID) -> uuid.UUID:
        return self.user_b_id if self.user_a_id == user_id else self.user_a_id


class Block(TimestampMixin, Base):
    __tablename__ = "blocks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    blocker_id: Mapped[uuid.UUID] = mapped_column(
        # uq_block_pair already covers blocker_id as its leading column.
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    blocked_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_block_pair"),
        CheckConstraint("blocker_id <> blocked_id", name="ck_block_not_self"),
    )


class Report(TimestampMixin, Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        # uq_report already covers reporter_id as its leading column.
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    reported_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=ReportStatus.OPEN.value, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("reporter_id", "reported_id", "reason", name="uq_report"),
        CheckConstraint("reporter_id <> reported_id", name="ck_report_not_self"),
        # The moderation queue asks for exactly this shape: one status, oldest first, and a page
        # that continues after a (created_at, id) pair. `ix_reports_status` answered the predicate
        # and then sorted the whole bucket in the reader; the ordering columns belong in the key,
        # and status alone is its left prefix, so the old index is dropped rather than kept as a
        # write cost that no read asks for.
        Index("ix_reports_status_created_at", "status", "created_at", "id"),
    )


class ReportReview(TimestampMixin, Base):
    """One status change of one complaint, written by the hand that moved it.

    `reports.status` says where a complaint stands now; this says how it got there and who said
    so. The pair (previous, new) is stored rather than only the new value because a queue read
    after the fact has to be able to tell a complaint that was dismissed straight away from one
    that was looked at twice, and a single column cannot hold both answers.
    """

    __tablename__ = "report_reviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    moderator_id: Mapped[uuid.UUID] = mapped_column(
        # RESTRICT and not CASCADE: a row that records what was decided about a person must not
        # disappear because the account that decided it stopped being one, and accounts are never
        # hard-deleted anyway, so nothing in the product has the power to take it with them.
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("from_status <> to_status", name="ck_report_review_moves_status"),
        # One history read per complaint, in the order the decisions were made, and the cursor of
        # a page of the queue is a (created_at, id) pair of this same shape.
        Index("ix_report_reviews_report_order", "report_id", "created_at", "id"),
    )
