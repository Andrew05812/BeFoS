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
        # Not `get_profile_with_user`: that one only asks whether the account still exists,
        # and existence is not consent to be acted upon. A hidden, deactivated or never
        # onboarded profile answers 404 here for the same reason it is absent from the deck,
        # and the answer is the same "not found" the public profile uses so that neither
        # path tells the caller which of the three it is.
        target = await self.users.get_showable_profile(target_id)
        if target is None:
            raise NotFoundError("User not found.")
        if await self.social.is_blocked_either(viewer_id, target_id):
            raise NotFoundError("User not found.")

    async def like(self, viewer_id: uuid.UUID, target_id: uuid.UUID) -> dict:
        await self._ensure_target(viewer_id, target_id)
        # Taken before the first read so a simultaneous like from the other side — and a
        # simultaneous block, which SafetyService.block guards with this same pair lock —
        # waits here until that transaction commits; see SocialRepository.lock_pair.
        await self.social.lock_pair(viewer_id, target_id)
        # The block check in _ensure_target ran before the lock became ours, so a block that
        # committed while we waited is invisible to it. Reading again now, with the lock held,
        # is the difference between a like that answers 404 and one that silently re-creates
        # the match a fresh block just dissolved — leaving a blocked pair matched and chatting.
        if await self.social.is_blocked_either(viewer_id, target_id):
            raise NotFoundError("User not found.")

        result = await self.compatibility.score_pair(viewer_id, target_id)
        # Stored as the engine produced it, not snapped to four decimals. The match list
        # shows this value multiplied by 100 and rounded, and a rounded snapshot can land
        # on the other side of that boundary from the number the live screen computes.
        score = result.overall

        existing = await self.social.get_like(viewer_id, target_id)
        if existing is None:
            await self.social.add_like(viewer_id, target_id, score)
            # A pass becomes irrelevant once you like someone.
            await self.social.delete_pass(viewer_id, target_id)

        mutual = await self.social.has_liked_back(viewer_id, target_id)
        match_id: uuid.UUID | None = None
        created_match = False
        if mutual:
            match_id, created_match = await self.social.ensure_match(viewer_id, target_id, score)
            if created_match:
                tracker.track(
                    Event.MATCH, str(viewer_id), match=str(match_id), with_user=str(target_id)
                )

        await self.session.commit()
        tracker.track(Event.LIKE, str(viewer_id), target=str(target_id), matched=created_match)
        return {
            "liked": True,
            # Only the like that actually formed the pair reports a match, so a second
            # tap cannot fire the «это взаимно» moment twice.
            "match": created_match,
            "match_id": str(match_id) if match_id else None,
            "compatibility": int(round(score * 100)),
        }

    async def pass_user(self, viewer_id: uuid.UUID, target_id: uuid.UUID) -> dict:
        await self._ensure_target(viewer_id, target_id)
        await self.social.add_pass(viewer_id, target_id)
        await self.session.commit()
        tracker.track(Event.PASS, str(viewer_id), target=str(target_id))
        return {"passed": True}
