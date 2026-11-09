"""Turning «an address somebody typed» into «an address this account holds».

Registration writes a shell and hands a letter to the channel in `services/mail.py`; this module owns
the two doors on either side of that letter. `send_letter` mints it and gives it to the channel — at
registration, and again from the confirmation screen when the first one never arrived. `confirm`
spends it: the code is looked up by its SHA-256 digest under its own purpose, the account it names is
read back live, and only then does `is_verified` become true.

Two claims this file deliberately does not make:

* that a letter was delivered. `send_letter` answers where it was handed (a path, a peer), and nothing
  here says a mailbox received it — the same sentence `services/mail.py` writes at the top applies to
  every caller;
* that the address was confirmed because the write succeeded. The flag moves only through `confirm`,
  which only a row minted for `ChallengePurpose.EMAIL_CONFIRMATION` can satisfy, so a recovery letter
  or anything else this table learns to hold cannot raise it.

The gate that flag opens sits in the deck's predicate (`repositories/social_repo.py`), not on this
module's callers: an unverified account is simply not a candidate anybody is offered, however it
reaches the screen.
"""

from __future__ import annotations

import smtplib

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.logging import get_logger
from app.core.security import (
    generate_recovery_code,
    generate_token_hash,
    normalise_recovery_code,
)
from app.models import ChallengePurpose, User
from app.repositories.challenge_repo import ChallengeRepository
from app.services.mail import (
    CODE_REFUSED,
    MailChannelUnavailable,
    current_transport,
    email_confirmation_letter,
)

logger = get_logger(__name__)


class VerificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.challenges = ChallengeRepository(session)

    async def send_letter(self, user: User) -> str | None:
        """Mint a confirmation code, hand its letter to the channel, and say where it went.

        Returns None without writing anything when there is nothing to send: an address that is
        already confirmed, or one that still holds a live letter. The second rule is the abuse
        surface — a resend button without it is a script that makes this server mail on command —
        and it is also the honest answer to a double tap: the letter that is already in the mailbox
        is the letter that works.

        Raises when the channel raises. The caller decides whether that failure fails the request
        (the resend door: it did) or is logged and survived (registration: the account is the person's
        and the letter has the resend door behind it).
        """
        if user.is_verified:
            return None
        live = await self.challenges.live_for(user.id, ChallengePurpose.EMAIL_CONFIRMATION)
        if live is not None:
            return None

        minutes = settings.confirm_code_minutes
        code = generate_recovery_code()
        row = await self.challenges.issue(
            user.id,
            ChallengePurpose.EMAIL_CONFIRMATION,
            generate_token_hash(code),
            minutes,
        )
        try:
            where = await current_transport().send(
                email_confirmation_letter(to=user.email, code=code, minutes=minutes)
            )
        except (MailChannelUnavailable, smtplib.SMTPException, OSError):
            # The row was flushed to enforce «one live letter per account», but no letter will ever
            # carry it. Removing it here — rather than rolling the whole session back, which expires
            # every loaded object — keeps the person's account usable after a failed send and keeps
            # the resend door able to try again.
            await self.session.delete(row)
            await self.session.flush()
            raise
        await self.session.commit()
        logger.info("Confirmation letter handed to the channel destination=%s", where)
        return where

    async def confirm(self, code: str) -> None:
        """Spend a confirmation code: the account it names becomes verified.

        The refusal is one sentence for a code that never existed, one already spent, one too old
        and an account that has since been erased — the same four answers `RecoveryService` gives,
        for the same reason. A code that still works is spent by the same statement that reads it
        (`ChallengeRepository.redeem`), so two taps cannot both raise the flag.
        """
        owner = await self.challenges.redeem(
            generate_token_hash(normalise_recovery_code(code)),
            ChallengePurpose.EMAIL_CONFIRMATION,
        )
        if owner is None:
            raise UnauthorizedError(CODE_REFUSED)

        user = await self.session.get(User, owner)
        if user is None or user.is_deleted or not user.is_active:
            raise UnauthorizedError(CODE_REFUSED)

        # True is written even when it was already true: a second tap on the same code is not a
        # conflict, and the row it would otherwise have to report is the same one.
        user.is_verified = True
        await self.session.commit()
        logger.info("Confirmed the address of an account user_id=%s", user.id)
