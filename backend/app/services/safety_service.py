from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import User
from app.repositories.social_repo import SocialRepository
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.websocket.manager import manager

VALID_REASONS = {"spam", "harassment", "inappropriate", "fake", "minor", "other"}


class SafetyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.social = SocialRepository(session)
        self.users = UserRepository(session)
        self.tokens = TokenRepository(session)

    async def block(self, blocker_id: uuid.UUID, blocked_id: uuid.UUID) -> dict:
        if blocker_id == blocked_id:
            raise ValidationError("You cannot block yourself.")
        target = await self.users.get_by_id(blocked_id)
        if target is None or target.is_deleted:
            raise NotFoundError("User not found.")
        dissolved = await self.social.add_block(blocker_id, blocked_id)
        await self.session.commit()
        if dissolved is not None:
            await manager.close_room(dissolved)
        return {"blocked": True, "user_id": str(blocked_id)}

    async def report(self, reporter_id: uuid.UUID, reported_id: uuid.UUID, reason: str, details: str | None) -> dict:
        if reporter_id == reported_id:
            raise ValidationError("You cannot report yourself.")
        reason = (reason or "").strip().lower()
        if reason not in VALID_REASONS:
            raise ValidationError(f"Invalid report reason. Allowed: {sorted(VALID_REASONS)}.")
        target = await self.users.get_by_id(reported_id)
        if target is None or target.is_deleted:
            raise NotFoundError("User not found.")
        # The unique (reporter, reported, reason) constraint decides duplicates: a second
        # tap of «Пожаловаться» arrives before the first has committed, so a prior read
        # cannot be the gate.
        if not await self.social.add_report(reporter_id, reported_id, reason, (details or None)):
            raise ConflictError("You have already reported this user for the same reason.")
        await self.session.commit()
        return {"reported": True, "reason": reason}

    async def delete_account(self, user_id: uuid.UUID) -> dict:
        """Soft-delete + anonymise a user account.

        The profile is anonymised, the account is marked deleted and disabled,
        and all refresh tokens are revoked so sessions cannot be restored.
        """
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        profile = await self.users.get_profile(user_id)
        if profile is not None:
            profile.name = "Deleted User"
            profile.about = None
            profile.city = ""
            profile.is_hidden = True
            profile.lifestyle = {}
            await self.users.set_profile_interests(profile.id, [])
        user.is_deleted = True
        user.is_active = False
        user.deleted_at = datetime.now(timezone.utc)
        user.email = f"deleted_{user.id}@deleted.befos.local"
        user.password_hash = "!deleted"
        await self.tokens.revoke_all_for_user(user_id)
        dissolved = await self.social.purge_social_graph(user_id)
        await self.session.commit()
        for match_id in dissolved:
            await manager.close_room(match_id)
        return {"deleted": True}

    async def set_hidden(self, user_id: uuid.UUID, hidden: bool) -> dict:
        profile = await self.users.get_profile(user_id)
        if profile is None:
            raise NotFoundError("Profile not found.")
        profile.is_hidden = hidden
        await self.session.commit()
        return {"hidden": hidden}
