from __future__ import annotations

import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Interest, Photo, Profile, User, UserInterest


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

    async def get_primary_photos(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, Photo]:
        if not user_ids:
            return {}
        stmt = (
            select(Photo)
            .where(Photo.user_id.in_(user_ids))
            .order_by(Photo.user_id, Photo.is_primary.desc(), Photo.position.asc())
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
            .order_by(Photo.is_primary.desc(), Photo.position.asc())
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
            self.session.add(UserInterest(profile_id=profile_id, interest_id=interest.id))
        await self.session.flush()

    async def list_all_interests(self) -> list[Interest]:
        stmt = select(Interest).order_by(Interest.name)
        return list((await self.session.execute(stmt)).scalars().all())
