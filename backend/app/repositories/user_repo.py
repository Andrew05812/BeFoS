from __future__ import annotations

import uuid

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload, selectinload

from app.models import PHOTO_DISPLAY_ORDER, Interest, Photo, Profile, User, UserInterest


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email.lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def email_exists(self, email: str) -> bool:
        stmt = select(User.id).where(func.lower(User.email) == email.lower())
        return (await self.session.execute(stmt)).first() is not None

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_profile(self, user_id: uuid.UUID) -> Profile | None:
        stmt = (
            select(Profile)
            .options(selectinload(Profile.interests))
            .where(Profile.user_id == user_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_profile_with_user(self, user_id: uuid.UUID) -> Profile | None:
        stmt = (
            select(Profile)
            .join(User, User.id == Profile.user_id)
            .options(selectinload(Profile.interests))
            .where(Profile.user_id == user_id, User.is_deleted.is_(False))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    def _showable_conditions(user_id: uuid.UUID) -> list:
        """The deck's rule as one list of conditions, shared by the two reads below.

        Kept in one place because the answer a caller gets about a person must not depend on
        which of the two reads it came through: a rule written twice drifts, and the drift
        shows up as a profile that still appears in the deck but 404s on a like, or the other
        way round.
        """
        return [
            Profile.user_id == user_id,
            User.is_deleted.is_(False),
            User.is_active.is_(True),
            Profile.is_hidden.is_(False),
            Profile.onboarding_completed_at.is_not(None),
        ]

    async def get_showable_profile(self, user_id: uuid.UUID) -> Profile | None:
        """The profile as the deck sees it: alive, active, visible, onboarded.

        ``DiscoveryRepository._candidate_conditions`` is the rule that decides who may be
        shown; this is the same rule asked about a single id, for the paths that never go
        through the deck. It exists because hiding is a request to disappear: if the deck
        honours it but ``POST /users/{id}/like`` still resolves the id, the person is only
        hidden from the one screen they were looking at.
        """
        stmt = (
            select(Profile)
            .join(User, User.id == Profile.user_id)
            .options(selectinload(Profile.interests))
            .where(*self._showable_conditions(user_id))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def is_showable_profile(self, user_id: uuid.UUID) -> bool:
        """``get_showable_profile`` where only the yes-or-no is used: no row, no interest loader.

        A caller that is about to reject a gesture, or that reads the person properly a moment
        later, does not need the name or the interest list — the two extra statements the full
        read costs it are what made a check that answers "no" as expensive as the page that
        answers "yes".
        """
        stmt = (
            select(Profile.user_id)
            .join(User, User.id == Profile.user_id)
            .where(*self._showable_conditions(user_id))
            .limit(1)
        )
        return (await self.session.execute(stmt)).first() is not None

    async def get_match_peer_profile(self, user_id: uuid.UUID) -> Profile | None:
        """The peer as an established match sees them: ``get_showable_profile`` without the
        ``is_hidden`` condition.

        The switch is a deck preference — its label reads «Скрыть из подбора» — so it withdraws
        introductions that have not happened yet, not a pair that already said yes to each other.
        The rest stays: a deleted, deactivated or never-onboarded account is unavailable to the
        person who matched with it too.
        """
        stmt = (
            select(Profile)
            .join(User, User.id == Profile.user_id)
            .options(selectinload(Profile.interests))
            .where(
                Profile.user_id == user_id,
                User.is_deleted.is_(False),
                User.is_active.is_(True),
                Profile.onboarding_completed_at.is_not(None),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_profiles_by_ids(self, user_ids: list[uuid.UUID]) -> list[Profile]:
        if not user_ids:
            return []
        stmt = (
            select(Profile)
            .join(User, User.id == Profile.user_id)
            .options(selectinload(Profile.interests))
            .where(Profile.user_id.in_(user_ids), User.is_deleted.is_(False))
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_profiles_without_interests(self, user_ids: list[uuid.UUID]) -> list[Profile]:
        """The same batch for a page that shows who people are, not what they like.

        ``Profile.interests`` loads with every profile by default, and that loader is the widest
        read in the match list on volume — one `Seq Scan user_interests` over 30 004 строки at
        10 000 анкет (`docs/SCALE_PLAN.md` §2). The list answers with a name, a city, a photo and
        a stored percent, so it was paying for its most expensive query and throwing the rows away.

        Reading `.interests` off one of these objects raises instead of returning an empty list:
        a page that starts showing interests has to come and ask for the loader here, rather than
        silently serve nobody's.
        """
        if not user_ids:
            return []
        stmt = (
            select(Profile)
            .join(User, User.id == Profile.user_id)
            .options(raiseload(Profile.interests))
            .where(Profile.user_id.in_(user_ids), User.is_deleted.is_(False))
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_primary_photos(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, Photo]:
        if not user_ids:
            return {}
        stmt = (
            select(Photo)
            .where(Photo.user_id.in_(user_ids))
            .order_by(Photo.user_id, *PHOTO_DISPLAY_ORDER)
        )
        first: dict[uuid.UUID, Photo] = {}
        for photo in (await self.session.execute(stmt)).scalars():
            first.setdefault(photo.user_id, photo)
        return first

    async def upsert_profile(self, profile: Profile) -> Profile:
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def get_primary_photo(self, user_id: uuid.UUID) -> Photo | None:
        stmt = (
            select(Photo)
            .where(Photo.user_id == user_id)
            .order_by(*PHOTO_DISPLAY_ORDER)
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_interests_by_slugs(self, slugs: list[str]) -> list[Interest]:
        if not slugs:
            return []
        stmt = select(Interest).where(Interest.slug.in_(slugs))
        return list((await self.session.execute(stmt)).scalars().all())

    async def set_profile_interests(self, profile_id: uuid.UUID, interests: list[Interest]) -> None:
        await self.session.execute(
            UserInterest.__table__.delete().where(UserInterest.profile_id == profile_id)
        )
        for interest in interests:
            # A second onboarding submit can land while the first is still in flight;
            # both delete and both insert the same pairs, so the constraint decides.
            await self.session.execute(
                pg_insert(UserInterest)
                .values(profile_id=profile_id, interest_id=interest.id)
                .on_conflict_do_nothing(constraint="uq_user_interest")
            )

    async def list_all_interests(self) -> list[Interest]:
        stmt = select(Interest).order_by(Interest.name)
        return list((await self.session.execute(stmt)).scalars().all())
