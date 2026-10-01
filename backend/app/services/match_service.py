from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.tracker import Event, tracker
from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.social_repo import SocialRepository
from app.repositories.user_repo import UserRepository
from app.services.compatibility_service import CompatibilityService


class MatchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.social = SocialRepository(session)
        self.users = UserRepository(session)
        self.compatibility = CompatibilityService(session)

    async def _ensure_target(self, viewer_id: uuid.UUID, target_id: uuid.UUID) -> None:
        if viewer_id == target_id:
            raise ValidationError("You cannot act on your own profile.")
        target = await self.users.get_profile_with_user(target_id)
        if target is None:
            raise NotFoundError("User not found.")
        if await self.social.is_blocked_either(viewer_id, target_id):
            raise NotFoundError("User not found.")

    async def like(self, viewer_id: uuid.UUID, target_id: uuid.UUID) -> dict:
        await self._ensure_target(viewer_id, target_id)

        result = await self.compatibility.score_pair(viewer_id, target_id)
        score = round(result.overall, 4)

        existing = await self.social.get_like(viewer_id, target_id)
        if existing is None:
            await self.social.add_like(viewer_id, target_id, score)
            # A pass becomes irrelevant once you like someone.
            await self.social.delete_pass(viewer_id, target_id)

        mutual = await self.social.has_liked_back(viewer_id, target_id)
        match_id: uuid.UUID | None = None
        if mutual:
            match = await self.social.get_match_between(viewer_id, target_id)
            if match is None:
                match = await self.social.add_match(viewer_id, target_id, score)
            match_id = match.id
            tracker.track(Event.MATCH, str(viewer_id), match=str(match_id), with_user=str(target_id))

        await self.session.commit()
        tracker.track(Event.LIKE, str(viewer_id), target=str(target_id), matched=mutual)
        return {
            "liked": True,
            "match": mutual,
            "match_id": str(match_id) if match_id else None,
            "compatibility": int(round(score * 100)),
        }

    async def pass_user(self, viewer_id: uuid.UUID, target_id: uuid.UUID) -> dict:
        await self._ensure_target(viewer_id, target_id)
        if await self.social.get_pass(viewer_id, target_id) is None:
            await self.social.add_pass(viewer_id, target_id)
        await self.session.commit()
        tracker.track(Event.PASS, str(viewer_id), target=str(target_id))
        return {"passed": True}
