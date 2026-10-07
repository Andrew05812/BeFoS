from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.tracker import Event, tracker
from app.core.exceptions import NotFoundError, ValidationError
from app.models import Profile
from app.repositories.social_repo import SocialRepository
from app.repositories.user_repo import UserRepository
from app.services.compatibility_service import CompatibilityService


class MatchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.social = SocialRepository(session)
        self.users = UserRepository(session)
        self.compatibility = CompatibilityService(session)

    async def _reject_unavailable(self, viewer_id: uuid.UUID, target_id: uuid.UUID) -> None:
        """The early refusal, asked as a boolean.

        Runs before the pair lock so a like aimed at somebody who is not in the deck never
        takes it, and its answer is thrown away a moment later: the row is read again after
        the lock, which is what the race tests hold. Loading the person here would buy the
        same yes-or-no at the price of their name, their city and their whole interest list.
        """
        if viewer_id == target_id:
            raise ValidationError("You cannot act on your own profile.")
        if not await self.users.is_showable_profile(target_id):
            raise NotFoundError("User not found.")
        if await self.social.is_blocked_either(viewer_id, target_id):
            raise NotFoundError("User not found.")

    async def _available_target(self, viewer_id: uuid.UUID, target_id: uuid.UUID) -> Profile:
        """The peer's row, for the request that has to score it.

        Not `get_profile_with_user`: that one only asks whether the account still exists,
        and existence is not consent to be acted upon. A hidden, deactivated or never
        onboarded profile answers 404 here for the same reason it is absent from the deck,
        and the answer is the same "not found" the public profile uses so that neither
        path tells the caller which of the three it is.
        """
        target = await self.users.get_showable_profile(target_id)
        if target is None:
            raise NotFoundError("User not found.")
        if await self.social.is_blocked_either(viewer_id, target_id):
            raise NotFoundError("User not found.")
        return target

    async def like(self, viewer_id: uuid.UUID, target_id: uuid.UUID) -> dict:
        await self._reject_unavailable(viewer_id, target_id)
        # Taken before the first read so a simultaneous like from the other side — and a
        # simultaneous block, which SafetyService.block guards with this same pair lock, or
        # a peer's delete_account, whose purge now takes the pair lock too — waits here
        # until that transaction commits; see SocialRepository.lock_pair.
        await self.social.lock_pair(viewer_id, target_id)
        # The pre-lock `_reject_unavailable` ran at a snapshot that could already be stale by
        # the time the pair lock became ours: a block committed while we waited, or a peer's
        # account deletion, is invisible to that earlier read. Re-running the same check now
        # is what separates a like that answers 404 from one that silently re-creates the
        # match a fresh block just dissolved or that writes a Match row against a
        # soft-deleted peer with no future cascade able to clean it.
        target = await self._available_target(viewer_id, target_id)

        # Scored from the rows this request already read: `score_pair` would fetch both people
        # again for a number computed from data in hand, and the peer's row would then be read
        # a third time in a path that only checks their availability twice on purpose.
        viewer_input = await self.compatibility.build_input(viewer_id)
        target_input = await self.compatibility.input_for(target)
        result = self.compatibility.score_inputs(viewer_input, target_input)
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
        await self._reject_unavailable(viewer_id, target_id)
        await self.social.add_pass(viewer_id, target_id)
        await self.session.commit()
        tracker.track(Event.PASS, str(viewer_id), target=str(target_id))
        return {"passed": True}
