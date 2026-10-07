from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utc_today() -> date:
    """The single calendar the product dates itself by.

    Age is whole years between a stored birth date and "today", and three paths compute it:
    the 18+ gate at signup, the number on a card, the birth-date window that fills the deck.
    Reading "today" off the server's own clock put those paths in different calendars whenever
    that clock ran ahead of UTC, and the product admitted a person as an adult while showing
    them a year younger.
    """
    return datetime.now(timezone.utc).date()


def age_years(birth_date: date, today: date) -> int:
    """Whole years lived by ``today`` — a birthday not yet reached does not count."""
    return (
        today.year
        - birth_date.year
        - ((today.month, today.day) < (birth_date.month, birth_date.day))
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, nullable=False
    )
