from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin
from app.models.enums import ChallengePurpose


class RefreshToken(TimestampMixin, Base):
    """Persisted refresh tokens (stored hashed) to allow revocation & rotation."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        # ix_refresh_user_revoked already covers user_id as its leading column.
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (Index("ix_refresh_user_revoked", "user_id", "revoked"),)


class AuthChallenge(TimestampMixin, Base):
    """A one-time code that proves somebody read a letter sent to this account's address.

    The shape is copied from `RefreshToken` on purpose, because the two rows answer the same question
    — «does the caller hold the secret we handed out?» — and the answers must be equally hard to
    imitate. So the code is stored as a SHA-256 hex digest and never as itself
    (`core/security.py:generate_token_hash`): a backup, a replica or a slow-query log that leaks this
    table must not be a set of live doors into other people's accounts.

    `expires_at` and `consumed_at` are separate columns, not one, because they answer separate
    questions. A spent code and an old code are refused with the same sentence at the door, but an
    operator clearing a stuck account or a support conversation about «why did my letter not work»
    needs the difference, and a single column cannot hold both without a rule about which one wins.

    There is deliberately no check constraint on `expires_at > created_at`. The row is a promise about
    the future made at write time, and the only way to test an expired code in a suite is to move that
    promise into the past; a constraint would have made the refusal path untestable, which is the worse
    trade. See `repositories/challenge_repo.py:redeem`, where the deadline is part of the predicate
    that decides whether the code still works.
    """

    __tablename__ = "auth_challenges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        # ix_auth_challenges_owner_purpose already carries user_id as its leading column, and a
        # second narrow index over it would be a prefix the redundancy guard exists to refuse.
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # In the redemption predicate as well as in the row: a code minted to return a lost word must not
    # be spendable as proof of anything else, whatever else this table learns to hold.
    purpose: Mapped[str] = mapped_column(
        String(20), default=ChallengePurpose.PASSWORD_RESET.value, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_auth_challenges_owner_purpose", "user_id", "purpose"),)
