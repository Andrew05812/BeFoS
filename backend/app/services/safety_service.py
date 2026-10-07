from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import (
    ActivityPreference,
    CompatibilityProfile,
    DiscoveryQueue,
    Photo,
    TestAnswer,
    TestResult,
    User,
)
from app.repositories.social_repo import SocialRepository
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.services import photo_service
from app.websocket.manager import manager

VALID_REASONS = {"spam", "harassment", "inappropriate", "fake", "minor", "other"}

# What a column that no longer describes anyone holds. `birth_date`, `gender` and
# `dating_goal` are NOT NULL, so erasure writes a value that is nobody's real answer and
# could not have come from the form.
ERASED_BIRTH_DATE = date(1900, 1, 1)
ERASED_GENDER = "erased"
ERASED_DATING_GOAL = "erased"


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
        # The same pair lock MatchService.like takes. A like already in flight either commits
        # before us, so the delete below dissolves its match, or waits on this lock and its
        # post-lock block check turns it into a 404. Without the lock the two can both commit
        # and leave the pair blocked and matched at once — which chat would then keep serving.
        await self.social.lock_pair(blocker_id, blocked_id)
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
            profile.birth_date = ERASED_BIRTH_DATE
            profile.gender = ERASED_GENDER
            profile.dating_goal = ERASED_DATING_GOAL
            profile.age_min = 18
            profile.age_max = 18
            profile.gender_preference = []
            profile.city_preference = None
            await self.users.set_profile_interests(profile.id, [])
        # Hiding the profile stops every route from serving it, which is not the same
        # statement as "the photographs are gone": `/uploads` is a public static mount, so
        # a url somebody already loaded keeps answering for as long as the file sits there.
        # The rows go with the account and the files go with the rows.
        photo_urls = list(
            (await self.session.execute(select(Photo.url).where(Photo.user_id == user_id))).scalars().all()
        )
        if photo_urls:
            await self.session.execute(delete(Photo).where(Photo.user_id == user_id))
        # The questionnaire is the most personal thing this app holds, and it is the part a
        # person did not type with their hands but revealed by answering. Accounts are never
        # hard-deleted, so the schema's ON DELETE CASCADE never fires and these rows stay
        # unless the erasure says so: nothing reads them for a deleted account, because
        # every route that could asks for a live user first. The deck rows are the record of
        # who this person was shown, and the activity preferences are part of the same
        # portrait; both go with the account.
        for row in (TestAnswer, TestResult, CompatibilityProfile, ActivityPreference):
            await self.session.execute(delete(row).where(row.user_id == user_id))
        await self.session.execute(delete(DiscoveryQueue).where(DiscoveryQueue.viewer_id == user_id))
        user.is_deleted = True
        user.is_active = False
        user.deleted_at = datetime.now(timezone.utc)
        user.email = f"deleted_{user.id}@deleted.befos.local"
        user.password_hash = "!deleted"
        await self.tokens.revoke_all_for_user(user_id)
        dissolved = await self.social.purge_social_graph(user_id)
        await self.session.commit()
        # After the commit: a transaction that failed must not have already destroyed the
        # files the database still points at.
        for url in photo_urls:
            photo_service.delete_stored_photo(url)
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
