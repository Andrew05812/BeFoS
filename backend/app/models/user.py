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
from app.models.base import TimestampMixin, age_years, utc_today
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

    __table_args__ = (
        # Login and registration both ask `lower(email) = :value`, because the stored value is
        # normalised by the write path and the caller must be able to sign in with any casing he
        # typed. A btree over the raw column cannot answer that predicate at all — Postgres will
        # seq-scan the table for it — so the lookup that every single sign-in performs gets its own
        # expression index here, and the same index makes a mixed-case duplicate impossible.
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

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
    # Reserved rather than shipped: no endpoint writes this field, so the city half of the
    # deck filter below never binds on a request that came through the API. It is kept because
    # the column, the filter and the index already agree with each other, and deleting one of
    # the three would leave the other two pointing at nothing.
    city_preference: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Lifestyle / trait snapshot used by the compatibility engine as a fallback
    # and for display. Structured as free-form JSON so it stays extensible.
    lifestyle: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Set once by onboarding. Registration leaves a shell behind (a name taken from the
    # email, a placeholder birth date, nothing else), and a shell is not a person anybody
    # agreed to be shown, so the deck asks for this stamp instead of guessing from the
    # fields that happen to be filled.
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="profile")
    interests: Mapped[list["Interest"]] = relationship(
        secondary="user_interests", back_populates="users", lazy="selectin"
    )

    __table_args__ = (
        # The candidate read filters the city case-insensitively and the age as a range, and a
        # plain btree over `city` cannot answer a predicate on `lower(city)`. What the API
        # actually sends today is the range alone — the city comes from `city_preference`, which
        # nothing writes — so this index is reachable for the read but binds no leading column,
        # and at 264 profiles the planner seq-scans. See docs/DATABASE.md before quoting it as
        # a win.
        Index("ix_profiles_city_lower_birth", text("lower(city)"), "birth_date"),
        # The deck pages the visible population newest-first, and with no key in that order the
        # planner reads every visible row, sorts it, and keeps 150 of them. Measured on the 50 000
        # stand against this repository's own statement: the candidate read costs 5.1 ms instead of
        # 43.5 ms where preferences match everybody, and in a paired ABBA run of the whole refill
        # call — a viewer with 20 000 passes behind it — 15.0/15.1 ms against 381.2/381.7 ms, the
        # call itself 195.3/196.1 ms against 578.1/562.3 ms, with the chat read of the same run
        # standing at 2.5-2.7 ms in all four positions (docs/SCALE_PLAN.md, «Парные прогоны стадии
        # 55»). `DESC` binds to `created_at` alone — the catalog stores this key and
        # `(created_at DESC, user_id ASC)` as one and the same index, which is what lets the read
        # be a walk the Limit stops rather than a sort it waits for.
        #
        # The predicate is the half of the deck's visibility rule an index over `profiles` can name
        # — a partial index cannot reach into `users`, so `is_deleted` and `is_active` stay in the
        # join — and it is there for the reason `onboarding_completed_at` exists at all: a
        # registration shell and a hidden profile can never be shown, so entering them is a write
        # that answers no read. Measured on the same stand: 1 000 registrations leave a finished
        # index at 2 039 808 bytes, completing their onboarding adds 49 152 of them, and hiding
        # them again adds nothing — entries go dead rather than away (docs/SCALE_PLAN.md,
        # «Индекс порядка колоды: что он берёт с записи»).
        Index(
            "ix_profiles_deck_order",
            text("created_at DESC"),
            "user_id",
            postgresql_where=text(
                "is_hidden IS FALSE AND onboarding_completed_at IS NOT NULL"
            ),
        ),
    )

    @property
    def age(self) -> int:
        return age_years(self.birth_date, utc_today())


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
