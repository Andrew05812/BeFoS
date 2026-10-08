from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken


class TokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None = None,
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=(user_agent or "")[:255] or None,
        )
        self.session.add(token)
        await self.session.flush()
        return token

    async def consume(self, token_hash: str) -> bool:
        """Revoke an active token in one statement; False means it was never stored or is redeemed.

        The ``WHERE revoked = false`` predicate is what makes a single-use refresh token
        single-use under concurrency. Two redeem requests can reach this statement at the same
        instant, but the UPDATE takes the row lock, and the loser re-evaluates the predicate only
        after the winner commits — so it matches no row and is refused. The rotation therefore
        happens exactly once instead of every racing request minting its own session.
        """
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked.is_(False))
            .values(revoked=True, revoked_at=datetime.now(timezone.utc))
        )
        return result.rowcount == 1

    async def revoke_for_owner(self, token_hash: str, user_id: uuid.UUID) -> None:
        """Revoke one caller's own still-active token, in a single statement.

        The two guards this replaces used to be applied in Python after reading the row: the hash
        belongs to this caller, and the row is still live. Both fit in the ``WHERE`` clause, which
        leaves the row touched once instead of twice and settles a race with the rotation the same
        way ``consume`` does. Nothing is raised when it matches no row: logging out a token that is
        already dead is a success.
        """
        await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
            )
            .values(revoked=True, revoked_at=datetime.now(timezone.utc))
        )

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
            .values(revoked=True, revoked_at=datetime.now(timezone.utc))
        )
        await self.session.flush()
