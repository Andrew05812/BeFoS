from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class Invitation(TimestampMixin, Base):
    """One personal invitation link, and the account that used it at most once.

    A link is a bearer secret, not an object id: whoever holds the code may spend it. That is why
    the code is random (`secrets.token_urlsafe`), unique, and never derived from the inviter — the
    route that reads it can tell a stranger «this code is valid» without telling them whose it is,
    and the row has no field an invitee can turn into a profile read.

    `accepted_by_user_id` is UNIQUE and nullable. The uniqueness is the anti-inflation rule: one
    account confirms one invitation, and a second registration presenting a spent code is simply
    not attributed to it. NULL is «not spent yet»; the column is deliberately not exposed by the
    inviter's list, because the person who accepted it is not the inviter's data to read.

    `revoked_at` is the inviter's own way out of a link they regret sharing. It is not a delete:
    the row stays, the inviter's screen can say «вы отозвали ссылку», and the code remains burned.
    """

    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    inviter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # The inviter's own list is newest-first; the id breaks a same-microsecond tie.
        Index("ix_invitations_inviter_created", "inviter_id", text("created_at DESC"), "id"),
        # One account walks through one door. Named so the migration and the model say the same
        # sentence to `alembic check` instead of the database inventing a name for it.
        UniqueConstraint("accepted_by_user_id", name="uq_invitation_invited_account"),
    )


class WaitlistEntry(TimestampMixin, Base):
    """One account's voluntary «tell me when there are people in my city» mark.

    It stores no coordinates and no device data: the city is the string the person typed into
    their profile (or confirmed on the screen), and the row is keyed by the account so a second
    tap cannot become a second entry. Cancelling is a stamp, not a delete, for the same reason
    account erasure is soft: the operator can tell an active request from a withdrawn one.

    `notified_at` is deliberately present and unused. A future stage with a real delivery channel
    writes it once; until then the product does not promise that a letter will arrive.
    """

    __tablename__ = "waitlist_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_waitlist_entry_account"),
    )
