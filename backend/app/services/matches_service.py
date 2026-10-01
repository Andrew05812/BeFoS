from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Match, Photo
from app.repositories.chat_repo import ChatRepository
from app.repositories.user_repo import UserRepository


class MatchesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.chat = ChatRepository(session)

    async def list_matches(self, user_id: uuid.UUID) -> list[dict]:
        stmt = (
            select(Match)
            .where(or_(Match.user_a_id == user_id, Match.user_b_id == user_id))
            .order_by(Match.created_at.desc())
        )
        matches = list((await self.session.execute(stmt)).scalars().all())

        result: list[dict] = []
        for match in matches:
            other_id = match.other_user(user_id)
            profile = await self.users.get_profile_with_user(other_id)
            if profile is None:
                continue
            photo = await self.users.get_primary_photo(other_id)
            last = await self.chat.last_message(match.id)
            unread = await self.chat.unread_count(match.id, user_id)
            result.append(
                {
                    "match_id": str(match.id),
                    "user_id": str(other_id),
                    "name": profile.name,
                    "age": profile.age,
                    "city": profile.city,
                    "photo_url": photo.url if photo else None,
                    "compatibility": int(round(match.compatibility_score * 100)),
                    "last_message": last.body if last else None,
                    "last_message_at": last.created_at if last else None,
                    "unread": unread,
                    "created_at": match.created_at,
                }
            )

        # Sort: matches with recent activity first, then newest matches.
        result.sort(
            key=lambda m: (m["last_message_at"] or m["created_at"]),
            reverse=True,
        )
        return result
