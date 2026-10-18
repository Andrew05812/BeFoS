from __future__ import annotations

import uuid

from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import Match
from app.models.base import age_years, utc_today
from app.repositories.chat_repo import ChatRepository
from app.repositories.social_repo import SocialRepository
from app.repositories.user_repo import UserRepository


class MatchesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.chat = ChatRepository(session)
        self.social = SocialRepository(session)

    async def list_matches(self, user_id: uuid.UUID) -> list[dict]:
        # Four columns of the pair, not the row: its id, the id of the other member, the percent
        # stored at the like, its date. A `Match` entity carries six, and it is only one of the four
        # reads this screen pays for — together they materialised thirty-eight columns per card to
        # answer with eleven fields (stage 49).
        other_id = case((Match.user_a_id == user_id, Match.user_b_id), else_=Match.user_a_id)
        stmt = (
            select(Match.id, other_id.label("other_id"), Match.compatibility_score, Match.created_at)
            .where(or_(Match.user_a_id == user_id, Match.user_b_id == user_id))
            .order_by(Match.created_at.desc())
        )
        pairs = list((await self.session.execute(stmt)).all())

        # Batch-load per-match data: no query inside the loop.
        match_ids = [pair.id for pair in pairs]
        peer_ids = [pair.other_id for pair in pairs]
        # The cards on this screen show a name, an age, a city and a photo, and the percent the
        # pair stored at the like. Interests appear nowhere in it, so they are not read here.
        profiles = {p.user_id: p for p in await self.users.get_profile_cards(peer_ids)}
        photos = await self.users.get_primary_photos(peer_ids)
        # The newest line and the unread counter come from one pass over `messages`.
        summaries = await self.chat.chat_summaries(match_ids, user_id)

        today = utc_today()
        result: list[dict] = []
        for pair in pairs:
            profile = profiles.get(pair.other_id)
            if profile is None:
                continue
            body, at, unread = summaries.get(pair.id, (None, None, 0))
            result.append(
                {
                    "match_id": str(pair.id),
                    "user_id": str(pair.other_id),
                    "name": profile.name,
                    "age": age_years(profile.birth_date, today),
                    "city": profile.city,
                    "photo_url": photos.get(pair.other_id),
                    "compatibility": int(round(pair.compatibility_score * 100)),
                    "last_message": body,
                    "last_message_at": at,
                    "unread": unread,
                    "created_at": pair.created_at,
                }
            )

        # Sort: matches with recent activity first, then newest matches.
        result.sort(
            key=lambda m: (m["last_message_at"] or m["created_at"]),
            reverse=True,
        )
        return result

    async def dissolve(self, match_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """End the pair for both of its members, or say there is no pair here to end.

        Two reads of the members answer different questions. The one before the lock names the pair
        whose advisory lock this transaction must take — without it the write below would race a
        concurrent block, unmatch, or account deletion the way two mutual likes raced before
        `lock_pair` existed. The delete's own `RETURNING` answers the membership question after the
        lock is held: between those two moments the row can be gone (a block ended it), and a pair
        formed later is a new row with a new id that this request will not touch.

        Both `likes` rows of the pair go with it, which is what makes the answer mean «начать заново
        можно, но только вдвоём»: left standing, one next tap on that card would find
        `has_liked_back` still true and `ensure_match` would write a fresh pair the dissolved person
        never agreed to. The conversation and the plans need no separate cleanup — every child of
        `matches` is `ON DELETE CASCADE`, the same machinery a block already leans on, so a pair
        ended by an unmatch leaves exactly the shape a pair ended by a block leaves.
        """
        before = (
            await self.session.execute(
                select(Match.user_a_id, Match.user_b_id).where(Match.id == match_id)
            )
        ).first()
        if before is None or user_id not in (before[0], before[1]):
            raise NotFoundError("Match not found.")

        await self.social.lock_pair(before[0], before[1])
        ended = await self.social.dissolve_match(match_id)
        if ended is None:
            raise NotFoundError("Match not found.")
        await self.social.delete_likes_between(*ended)
        await self.session.commit()
