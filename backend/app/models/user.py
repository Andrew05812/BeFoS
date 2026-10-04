from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin
from app.models.enums import DatingGoal, Gender


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped["Profile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    photos: Mapped[list["Photo"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="Photo.position"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email}>"


class Profile(TimestampMixin, Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[str] = mapped_column(String(20), default=Gender.OTHER.value, nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)
    dating_goal: Mapped[str] = mapped_column(
        String(30), default=DatingGoal.RELATIONSHIP.value, nullable=False
    )

    # Search preferences
    age_min: Mapped[int] = mapped_column(Integer, default=18, nullable=False)
    age_max: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    gender_preference: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)), default=list, nullable=False
    )
    city_preference: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Lifestyle / trait snapshot used by the compatibility engine as a fallback
    # and for display. Structured as free-form JSON so it stays extensible.
    lifestyle: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship(back_populates="profile")
    interests: Mapped[list["Interest"]] = relationship(
        secondary="user_interests", back_populates="users", lazy="selectin"
    )

    __table_args__ = (
        # Every candidate read asks for lower(city) plus a birth_date range; the plain
        # city/dating_goal indexes could serve none of them.
        Index("ix_profiles_city_lower_birth", text("lower(city)"), "birth_date"),
    )

    @property
    def age(self) -> int:
        today = datetime.utcnow().date()
        return (
            today.year
            - self.birth_date.year
            - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        )


class Photo(TimestampMixin, Base):
    __tablename__ = "photos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="photos")


# The one order a photo list is ever read in. Every screen paints `photos[0]` as the
# avatar, so the photo the owner chose leads; `position` alone sorted a column that is
# always 0, which leaves the rest to whatever the heap handed back — and a page can be
# rewritten under it by a vacuum. The two tiebreakers make the answer a fact.
PHOTO_DISPLAY_ORDER = (
    Photo.is_primary.desc(),
    Photo.position.asc(),
    Photo.created_at.asc(),
    Photo.id.asc(),
)


class Interest(Base):
    __tablename__ = "interests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    users: Mapped[list["Profile"]] = relationship(
        secondary="user_interests", back_populates="interests"
    )


class UserInterest(Base):
    __tablename__ = "user_interests"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    interest_id: Mapped[int] = mapped_column(
        ForeignKey("interests.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (
        # The pair is the row identity and the name the interest upsert conflicts on;
        # declaring it as the primary key is what the database actually holds, so
        # `alembic check` stops reporting a constraint that cannot be added twice.
        PrimaryKeyConstraint("profile_id", "interest_id", name="uq_user_interest"),
        Index("ix_user_interests_interest", "interest_id"),
    )
