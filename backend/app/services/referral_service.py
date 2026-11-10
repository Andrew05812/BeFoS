"""A personal door into BeFoS: one random code, one account behind it, one use.

The empty deck is not always the absence of people; sometimes it is the absence of a way in.
This service owns the second half of that sentence — the link an existing account can hand to
somebody who has not registered — and it is deliberately smaller than a «referral programme»:

* there is no reward, no points and no level. A link buys an invitee a product, not the inviter a
  status, so the product has no reason to make people farm links;
* a code is a bearer secret, not a user id. It is minted by `secrets.token_urlsafe`, unique in the
  table, and nothing in it can be turned into a profile read. The public preview answers «does
  this door open» and never «whose door is it»;
* one code is spent by one account. `invitations.accepted_by_user_id` is UNIQUE, so the rule is the
  schema's even when two registrations pass the service's read at the same instant. The same
  column is why the inviter's own list does not name the invitee: that person is not the inviter's
  data to read, and their id would be a hop away from a public profile;
* an inviter may have one live link at a time and twenty new links a day. The first rule makes the
  endpoint idempotent (`POST` twice returns the same door, not two); the second bounds a script
  that keeps spending and minting. Neither is a reward — they are the shape of a door, not a game.

`revoke` is the inviter's own way out: the link stops opening, the row stays, and the screen can say
«вы отозвали ссылку» instead of pretending the code never existed. Expiry and revocation are kept
apart for the same reason `AuthChallenge` keeps `expires_at` from `consumed_at`: they are different
facts, and the person asking why their link failed is owed the one that happened.

This file never reads an invitee's profile, never returns an email, and never puts a code into the
analytics line — the code is a door, and a log is a place doors travel from.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.tracker import Event, tracker
from app.core.config import settings
from app.core.exceptions import NotFoundError, RateLimitedError, ValidationError
from app.core.logging import get_logger
from app.models import Invitation, User

logger = get_logger(__name__)

# Long enough that guessing is a search of 2^144, short enough to fit a URL a person can paste.
_CODE_BYTES = 18
# A month is the window in which «пригласил друга» is still a claim about a friend rather than a
# message found in an old chat. Past it the inviter can mint another link.
_INVITE_TTL_DAYS = 30
# Personal links are not a growth channel to grind: this bounds both the doors a person may mint in
# a day and (through the same constant) the accounts one inviter may be attributed in a day.
_DAILY_INVITES = 20


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ReferralService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _status(invitation: Invitation, now: datetime) -> str:
        if invitation.accepted_at is not None:
            return "accepted"
        if invitation.revoked_at is not None:
            return "revoked"
        if invitation.expires_at <= now:
            return "expired"
        return "active"

    @staticmethod
    def _url(code: str) -> str:
        return f"{settings.invite_link_base.rstrip('/')}/{code}"

    def _out(self, invitation: Invitation, now: datetime) -> dict:
        return {
            "id": str(invitation.id),
            "code": invitation.code,
            "url": self._url(invitation.code),
            "status": self._status(invitation, now),
            "expires_at": invitation.expires_at,
            "accepted_at": invitation.accepted_at,
            "created_at": invitation.created_at,
        }

    async def create_or_get(self, inviter: User) -> dict:
        """The link this account already has, or a fresh one if none is live.

        Idempotent on purpose. A button that mints a new code per tap would leave the person with
        two links, one of which they shared — and no way to tell which. The same call also bounds
        the endpoint: the second tap of a double-tap writes nothing.
        """
        now = _now()
        # Two taps of the same button are two requests, and the read below cannot see a row the
        # other transaction has not committed yet. The account row is the serializer: the second
        # request waits here on the first, then reads the door it minted instead of minting a twin.
        await self.session.execute(
            select(User.id).where(User.id == inviter.id).with_for_update()
        )
        live = (
            await self.session.execute(
                select(Invitation)
                .where(
                    Invitation.inviter_id == inviter.id,
                    Invitation.accepted_at.is_(None),
                    Invitation.revoked_at.is_(None),
                    Invitation.expires_at > now,
                )
                .order_by(Invitation.created_at.desc(), Invitation.id.desc())
                .limit(1)
            )
        ).scalars().first()
        if live is not None:
            return self._out(live, now)

        since = now - timedelta(days=1)
        minted = (
            await self.session.execute(
                select(func.count(Invitation.id)).where(
                    Invitation.inviter_id == inviter.id,
                    Invitation.created_at > since,
                )
            )
        ).scalar_one()
        if int(minted) >= _DAILY_INVITES:
            raise RateLimitedError(
                "Слишком много приглашений за сутки. Попробуйте завтра."
            )

        for _attempt in range(5):
            code = secrets.token_urlsafe(_CODE_BYTES)
            invitation = Invitation(
                inviter_id=inviter.id,
                code=code,
                expires_at=now + timedelta(days=_INVITE_TTL_DAYS),
            )
            self.session.add(invitation)
            try:
                await self.session.commit()
            except IntegrityError:
                await self.session.rollback()
                continue
            tracker.track(Event.INVITE_CREATED, str(inviter.id))
            logger.info("Invitation minted inviter_id=%s", inviter.id)
            return self._out(invitation, now)

        raise ValidationError("Не удалось создать ссылку. Попробуйте ещё раз.")

    async def list_for(self, inviter: User) -> dict:
        now = _now()
        rows = list(
            (
                await self.session.execute(
                    select(Invitation)
                    .where(Invitation.inviter_id == inviter.id)
                    .order_by(Invitation.created_at.desc(), Invitation.id.desc())
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )
        accepted_total = (
            await self.session.execute(
                select(func.count(Invitation.id)).where(
                    Invitation.inviter_id == inviter.id,
                    Invitation.accepted_at.is_not(None),
                )
            )
        ).scalar_one()
        return {
            "invites": [self._out(row, now) for row in rows],
            "accepted_total": int(accepted_total),
        }

    async def revoke(self, inviter: User, invitation_id: uuid.UUID) -> None:
        """Close one of this account's own live doors; somebody else's id is indistinguishable
        from an id that does not exist.
        """
        invitation = (
            await self.session.execute(
                select(Invitation).where(
                    Invitation.id == invitation_id,
                    Invitation.inviter_id == inviter.id,
                )
            )
        ).scalars().first()
        if invitation is None or invitation.accepted_at is not None:
            raise NotFoundError("Invitation not found.")
        if invitation.revoked_at is None:
            invitation.revoked_at = _now()
            await self.session.commit()
            tracker.track(Event.INVITE_REVOKED, str(inviter.id))

    async def preview(self, code: str) -> dict:
        """Whether a code opens a door, and when it closes. Nothing about the inviter."""
        now = _now()
        invitation = (
            await self.session.execute(
                select(Invitation)
                .join(User, User.id == Invitation.inviter_id)
                .where(
                    Invitation.code == (code or "").strip(),
                    User.is_active.is_(True),
                    User.is_deleted.is_(False),
                    User.is_verified.is_(True),
                )
            )
        ).scalars().first()
        valid = bool(
            invitation is not None
            and invitation.accepted_at is None
            and invitation.revoked_at is None
            and invitation.expires_at > now
        )
        tracker.track(Event.INVITE_OPENED, None, valid=valid, via="app")
        return {
            "valid": valid,
            "expires_at": invitation.expires_at if invitation is not None else None,
        }

    async def accept(self, code: str | None, invitee: User) -> bool:
        """Spend a code on this new account, or say why nothing was attributed.

        Called inside registration's transaction, before its commit. The row is locked
        (`FOR UPDATE`) and the spent/fresh test is part of the same statement that would write it,
        so two registrations presenting one code cannot both be attributed. Every refusal is a
        plain False: an invalid code must not turn registration into an oracle for which links
        exist, and the invitee still gets an account.
        """
        cleaned = (code or "").strip()
        if not cleaned:
            return False

        invitation = (
            await self.session.execute(
                select(Invitation).where(Invitation.code == cleaned).with_for_update()
            )
        ).scalars().first()
        now = _now()
        if invitation is None:
            return False
        if invitation.accepted_at is not None or invitation.accepted_by_user_id is not None:
            return False
        if invitation.revoked_at is not None or invitation.expires_at <= now:
            return False
        if invitation.inviter_id == invitee.id:
            return False

        inviter = await self.session.get(User, invitation.inviter_id)
        if inviter is None or inviter.is_deleted or not inviter.is_active or not inviter.is_verified:
            return False
        # The same address cannot invite itself. The comparison is on the normalised address the
        # unique index already uses, because a different case is the same mailbox.
        if inviter.email.strip().lower() == invitee.email.strip().lower():
            return False

        since = now - timedelta(days=1)
        accepted_today = (
            await self.session.execute(
                select(func.count(Invitation.id)).where(
                    Invitation.inviter_id == inviter.id,
                    Invitation.accepted_at > since,
                )
            )
        ).scalar_one()
        if int(accepted_today) >= _DAILY_INVITES:
            return False

        invitation.accepted_by_user_id = invitee.id
        invitation.accepted_at = now
        await self.session.flush()
        tracker.track(Event.INVITE_ACCEPTED, str(invitee.id))
        logger.info("Invitation accepted inviter_id=%s", inviter.id)
        return True
