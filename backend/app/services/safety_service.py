from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import (
    ActivityPreference,
    Block,
    CompatibilityProfile,
    DiscoveryQueue,
    Photo,
    TestAnswer,
    TestResult,
    User,
)
from app.models.base import age_years, utc_today
from app.repositories.social_repo import SocialRepository
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.services import photo_service
from app.websocket.manager import manager

# The categories a complaint may name. `reason` is a plain column and not an enum, so a value
# already stored by an older build keeps reading exactly as it did: adding the last two entries
# changed nothing about the rows that exist, only about what a new one may be written with. The
# two that were missing are the two a person reaches for when the account itself is the problem —
# somebody pretending to be someone else, and somebody whose message they do not want to read
# twice — and a complaint about either had to be filed as «other», which is the row a reviewer
# learns least from.
VALID_REASONS = {
    "spam",
    "harassment",
    "inappropriate",
    "fake",
    "minor",
    "impersonation",
    "threats",
    "other",
}

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

    async def unblock(self, blocker_id: uuid.UUID, blocked_id: uuid.UUID) -> list[dict]:
        """Undo a block the caller placed, and answer with the list that is left.

        The row goes under the same pair lock a block and a like take, so the three orders a
        person can cause — blocking, unblocking, liking — serialise instead of leaving a pair
        liked and blocked at once or a like reading a row the unblock is deleting.

        What comes back is the owner's list, not a boolean: the screen that asked has to paint
        the row the server actually holds after the removal, the same way the photograph row is
        painted from the answer rather than from what the tap expected. Undoing a block returns
        the person to the deck — the deck's anti-join stops excluding them — and does not
        resurrect the match the block dissolved: that pair's chat was deleted, and a route that
        quietly re-created it would be writing a relationship nobody agreed to.
        """
        if blocker_id == blocked_id:
            raise ValidationError("You cannot unblock yourself.")
        await self.social.lock_pair(blocker_id, blocked_id)
        if not await self.social.remove_block(blocker_id, blocked_id):
            # A number this account never blocked and a number nobody holds answer alike: the
            # route cannot be used to ask whether some other pair is blocked.
            raise NotFoundError("You have not blocked this user.")
        await self.session.commit()
        return await self.list_blocked(blocker_id)

    async def list_blocked(self, user_id: uuid.UUID) -> list[dict]:
        """The rows this account wrote into `blocks`, newest first, as cards it can recognise.

        The read is one-way on purpose: a row where this account is the blocked side belongs to
        the other person's list and is not this account's to see.
        """
        stmt = (
            select(Block.blocked_id, Block.created_at)
            .where(Block.blocker_id == user_id)
            # `created_at` alone is not an order: two taps in the same second give two rows with
            # one timestamp, and the list would then shuffle between two reads of the same state.
            .order_by(Block.created_at.desc(), Block.id.desc())
        )
        rows = list((await self.session.execute(stmt)).all())
        if not rows:
            return []
        ids = [row.blocked_id for row in rows]
        profiles = {p.user_id: p for p in await self.users.get_profile_cards(ids)}
        photos = await self.users.get_primary_photos(ids)
        today = utc_today()
        result: list[dict] = []
        for row in rows:
            profile = profiles.get(row.blocked_id)
            if profile is None:
                continue
            result.append(
                {
                    "user_id": str(row.blocked_id),
                    "name": profile.name,
                    "age": age_years(profile.birth_date, today),
                    "city": profile.city,
                    "photo_url": photos.get(row.blocked_id),
                    "blocked_at": row.created_at,
                }
            )
        return result

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
        profile = await self.users.get_profile_for_write(user_id)
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
        profile = await self.users.get_profile_for_write(user_id)
        if profile is None:
            raise NotFoundError("Profile not found.")
        profile.is_hidden = hidden
        await self.session.commit()
        return {"hidden": hidden}
