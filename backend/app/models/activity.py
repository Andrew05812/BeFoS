from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Activity(TimestampMixin, Base):
    """Catalogue of things two people can do together."""

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # Interest slugs this activity appeals to.
    interests: Mapped[list[str]] = mapped_column(ARRAY(String(80)), default=list, nullable=False)
    # Cities where it is available; empty means "anywhere".
    cities: Mapped[list[str]] = mapped_column(ARRAY(String(120)), default=list, nullable=False)
    # 0..1 how energetic / social / costly the activity is, used by the engine.
    energy: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    social: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    cost: Mapped[float] = mapped_column(Float, default=0.3, nullable=False)
    tags: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class ActivityPreference(TimestampMixin, Base):
    """Explicit user affinity toward an activity (saved / liked)."""

    __tablename__ = "activity_preferences"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        # uq_activity_pref already covers user_id as its leading column.
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "activity_id", name="uq_activity_pref"),)


class Recommendation(TimestampMixin, Base):
    """A persisted, explainable activity recommendation for a matched pair."""

    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(
        # uq_match_activity_rec already covers match_id as its leading column.
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Structured reasons: {"positive": [...], "context": [...]}
    explanation: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("match_id", "activity_id", name="uq_match_activity_rec"),
        Index("ix_rec_match_position", "match_id", "position"),
    )
