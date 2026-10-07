from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
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

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def revoke(self, token: RefreshToken) -> None:
        token.revoked = True
        token.revoked_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def consume(self, token_hash: str) -> bool:
        """Revoke an active token in one statement; False means it was already redeemed or revoked.

        The ``WHERE revoked = false`` predicate is what makes a single-use refresh token
        single-use under concurrency. Two redeem requests can both read the row as active, but
        this UPDATE takes the row lock, and the loser re-evaluates the predicate only after the
        winner commits — so it matches no row and is refused. The rotation therefore happens
        exactly once instead of every racing request minting its own session.
        """
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked.is_(False))
            .values(revoked=True, revoked_at=datetime.now(timezone.utc))
        )
        return result.rowcount == 1

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
            .values(revoked=True, revoked_at=datetime.now(timezone.utc))
        )
        await self.session.flush()
