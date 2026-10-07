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

        # Batch-load per-match data: no query inside the loop.
        match_ids = [m.id for m in matches]
        other_ids = [m.other_user(user_id) for m in matches]
        # The cards on this screen show a name, an age, a city and a photo, and the percent the
        # pair stored at the like. Interests appear nowhere in it, so they are not read here.
        profiles = {
            p.user_id: p for p in await self.users.get_profiles_without_interests(other_ids)
        }
        photos = await self.users.get_primary_photos(other_ids)
        last_messages = await self.chat.last_messages(match_ids)
        unread_counts = await self.chat.unread_counts(match_ids, user_id)

        result: list[dict] = []
        for match in matches:
            other_id = match.other_user(user_id)
            profile = profiles.get(other_id)
            if profile is None:
                continue
            photo = photos.get(other_id)
            last = last_messages.get(match.id)
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
                    "unread": unread_counts.get(match.id, 0),
                    "created_at": match.created_at,
                }
            )

        # Sort: matches with recent activity first, then newest matches.
        result.sort(
            key=lambda m: (m["last_message_at"] or m["created_at"]),
            reverse=True,
        )
        return result
