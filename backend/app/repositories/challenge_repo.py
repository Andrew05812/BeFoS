"""Rows that prove a caller holds a letter, written and redeemed one statement at a time.

A challenge is not a session and not a like: it is a claim about a mailbox, it is worth something
only for a few minutes, and it can be spent exactly once. All three of those are properties of the
row, so all three live in the predicate of the statement that spends it — the same shape
`token_repo.py:33-47` settled on for refresh-token rotation, where reading and then writing let two
concurrent requests both believe they had rotated the token.

Nothing here commits: the service owns the transaction, as everywhere else in `app/repositories`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthChallenge


class ChallengeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def issue(
        self, user_id: uuid.UUID, purpose: str, token_hash: str, minutes: int
    ) -> AuthChallenge:
        """Write one live challenge whose deadline is `minutes` from now."""
        row = AuthChallenge(
            user_id=user_id,
            purpose=purpose,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=minutes),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def live_for(self, user_id: uuid.UUID, purpose: str) -> AuthChallenge | None:
        """The newest challenge this account can still redeem for this purpose, if one exists.

        `consumed_at IS NULL` and `expires_at > now` are both in the filter because the question being
        asked is «would a letter still work» — a spent code and an old one are not answers to it, and a
        resend throttle built on rows nobody can redeem would silently stop every letter after the
        first one.
        """
        result = await self.session.execute(
            select(AuthChallenge)
            .where(
                AuthChallenge.user_id == user_id,
                AuthChallenge.purpose == purpose,
                AuthChallenge.consumed_at.is_(None),
                AuthChallenge.expires_at > datetime.now(timezone.utc),
            )
            .order_by(AuthChallenge.created_at.desc(), AuthChallenge.id.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def redeem(self, token_hash: str, purpose: str) -> uuid.UUID | None:
        """Spend a live code and say whose account it belonged to; None means it does not work.

        One statement, because this is the whole security argument of the door: two requests holding
        the same code must not both be allowed to set a word. The ``UPDATE`` takes the row lock, the
        loser re-evaluates ``consumed_at IS NULL`` only after the winner commits and matches nothing,
        and ``RETURNING`` carries the owner out of the same round trip — so there is no window where
        this file has read a row that another statement has already spent.
        """
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            update(AuthChallenge)
            .where(
                AuthChallenge.token_hash == token_hash,
                AuthChallenge.purpose == purpose,
                AuthChallenge.consumed_at.is_(None),
                AuthChallenge.expires_at > now,
            )
            .values(consumed_at=now)
            .returning(AuthChallenge.user_id)
        )
        row = result.first()
        return row[0] if row is not None else None

    async def expire_live_for(self, user_id: uuid.UUID, purpose: str) -> int:
        """Mark every still-live challenge of this account as spent; returns how many died.

        Called when a word has just been changed: a letter that was never opened must not stay a door
        into an account whose owner has just said, by asking for a new word, that something about the
        old one was wrong.
        """
        result = await self.session.execute(
            update(AuthChallenge)
            .where(
                AuthChallenge.user_id == user_id,
                AuthChallenge.purpose == purpose,
                AuthChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=datetime.now(timezone.utc))
        )
        return result.rowcount
