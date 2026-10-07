from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class TestQuestion(TimestampMixin, Base):
    __tablename__ = "test_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    trait: Mapped[str] = mapped_column(String(60), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    options: Mapped[list["TestOption"]] = relationship(
        back_populates="question", cascade="all, delete-orphan", order_by="TestOption.position"
    )

    __table_args__ = (Index("ix_question_category_position", "category", "position"),)


class TestOption(Base):
    __tablename__ = "test_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("test_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(String(255), nullable=False)
    # Position of this option on the question's trait axis, normalised to 0..1.
    value: Mapped[float] = mapped_column(Float, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    question: Mapped["TestQuestion"] = relationship(back_populates="options")


class TestAnswer(TimestampMixin, Base):
    __tablename__ = "test_answers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        # uq_user_question_answer already covers user_id as its leading column.
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("test_questions.id", ondelete="CASCADE"), nullable=False
    )
    option_id: Mapped[int] = mapped_column(
        ForeignKey("test_options.id", ondelete="CASCADE"), nullable=False
    )

    question: Mapped["TestQuestion"] = relationship(lazy="selectin")
    option: Mapped["TestOption"] = relationship(lazy="selectin")

    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_user_question_answer"),
    )


class TestResult(TimestampMixin, Base):
    """Per-category aggregated self-assessment score in 0..1, for display."""

    __tablename__ = "test_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        # uq_user_category_result already covers user_id as its leading column.
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    __table_args__ = (UniqueConstraint("user_id", "category", name="uq_user_category_result"),)


class CompatibilityProfile(TimestampMixin, Base):
    """Normalised trait vector consumed by the Compatibility Engine.

    `vector` shape: {category: {trait: value(0..1)}}. Versioned so the engine
    can be re-run when the trait model or weights change.
    """

    __tablename__ = "compatibility_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    vector: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
