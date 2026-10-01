from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, Index, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, utcnow
from app.models.enums import ReportStatus


class Like(TimestampMixin, Base):
    __tablename__ = "likes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    from_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    to_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    compatibility_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("from_user_id", "to_user_id", name="uq_like_pair"),
        CheckConstraint("from_user_id <> to_user_id", name="ck_like_not_self"),
    )


class Pass(TimestampMixin, Base):
    __tablename__ = "passes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    from_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
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
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
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
        Index("ix_match_users", "user_a_id", "user_b_id"),
    )

    def other_user(self, user_id: uuid.UUID) -> uuid.UUID:
        return self.user_b_id if self.user_a_id == user_id else self.user_a_id


class Block(TimestampMixin, Base):
    __tablename__ = "blocks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    blocker_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
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
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reported_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=ReportStatus.OPEN.value, nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint("reporter_id", "reported_id", "reason", name="uq_report"),
        CheckConstraint("reporter_id <> reported_id", name="ck_report_not_self"),
    )
