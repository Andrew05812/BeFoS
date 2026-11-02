from __future__ import annotations

import uuid

from sqlalchemy import and_, case, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.compatibility.engine import to_percent
from app.core.exceptions import NotFoundError
from app.core.page_cursor import PAIRS, open_moment, seal_moment
from app.models import Match, Message, MessageRead
from app.models.base import age_years, utc_today
from app.repositories.chat_repo import ChatRepository
from app.repositories.social_repo import SocialRepository
from app.repositories.user_repo import UserRepository

# How many pairs one answer of the list carries. The same bargain the inbox, the tap list and the pass
# list each hold at fifty: four doors of one screen family that stop at different numbers is how a
# person learns that one of them is wrong about the size of their own history.
MATCHES_SHOWN = 50


class MatchesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.chat = ChatRepository(session)
        self.social = SocialRepository(session)

    async def page(
        self, user_id: uuid.UUID, *, cursor: str | None = None, limit: int = MATCHES_SHOWN
    ) -> dict:
        """One page of the account's pairs, and the link to the page behind it.

        The order the screen paints by — newest line first, a pair's own moment when it never spoke —
        is the key the page resumes below, and that is the whole reason the order had to leave Python:
        a boundary drawn under a value the query never computed is a boundary nobody can state. The
        row's id decides a tie the timestamp cannot, the way the pair's history learned to do in stage
        54 and the tap list in stage 123.
        """
        before = open_moment(PAIRS, user_id, cursor)
        rows = (
            await self.session.execute(self._pairs_read(user_id, limit=limit + 1, before=before))
        ).all()
        shown = rows[:limit]
        cards = await self._cards(shown)
        next_cursor = None
        if len(rows) > limit and shown:
            next_cursor = seal_moment(PAIRS, user_id, shown[-1].sort_key, shown[-1].id)
        return {"matches": cards, "has_more": len(rows) > limit, "next_cursor": next_cursor}

    async def list_matches(self, user_id: uuid.UUID) -> list[dict]:
        """Every pair this account holds, for the one caller that has to name them all.

        The account export is that caller. A person's own document cannot carry a page of their life
        and say it carried their life, and the section already holds its own ceiling —
        `export_service.ROWS_PER_SECTION` — so it reads the whole list whatever the screen's page is.
        """
        rows = (await self.session.execute(self._pairs_read(user_id, limit=None, before=None))).all()
        return await self._cards(rows)

    def _pairs_read(self, user_id: uuid.UUID, *, limit: int | None, before):
        """The pairs of one account, in the order the screen paints them, as far as the page reaches.

        Four statements used to answer this list, and every one of them grew with the account rather
        than with the page. Now the pairs, their newest line and their waiting counter arrive in one
        read — the pass over `messages` stage 33 paid for and `test_matches_list_messages_read.py`
        guards is unchanged, only joined instead of run afterwards — and the two reads that dress the
        cards ask for the page's partners.

        `before` is the pair `(sort_key, match id)` the previous link carried and is compared as one
        value, which is what lets the scan stop inside the key instead of reading the whole list to
        cut it; `limit + 1` is how the door learns a page ended short without asking again.
        """
        waiting = and_(Message.sender_id != user_id, MessageRead.id.is_(None))
        reader_pairs = select(Match.id).where(
            or_(Match.user_a_id == user_id, Match.user_b_id == user_id)
        )
        newest = (
            select(
                Message.match_id.label("pair_id"),
                Message.body.label("body"),
                Message.created_at.label("line_at"),
                func.count()
                .filter(waiting)
                .over(partition_by=Message.match_id)
                .label("unread"),
            )
            .outerjoin(
                MessageRead,
                and_(MessageRead.message_id == Message.id, MessageRead.reader_id == user_id),
            )
            .where(Message.match_id.in_(reader_pairs), Message.is_deleted.is_(False))
            # DISTINCT ON keeps the newest row of each pair, and the id settles two lines written in
            # the same microsecond so that the card and the screen name the same one (stage 33).
            .distinct(Message.match_id)
            .order_by(Message.match_id, Message.created_at.desc(), Message.id.desc())
            .subquery()
        )
        other_id = case((Match.user_a_id == user_id, Match.user_b_id), else_=Match.user_a_id)
        sort_key = func.coalesce(newest.c.line_at, Match.created_at)
        stmt = (
            select(
                Match.id,
                other_id.label("other_id"),
                Match.compatibility_score,
                Match.created_at,
                newest.c.body,
                newest.c.line_at,
                func.coalesce(newest.c.unread, 0).label("unread"),
                sort_key.label("sort_key"),
            )
            .outerjoin(newest, newest.c.pair_id == Match.id)
            .where(or_(Match.user_a_id == user_id, Match.user_b_id == user_id))
        )
        if before is not None:
            stmt = stmt.where(tuple_(sort_key, Match.id) < before)
        stmt = stmt.order_by(sort_key.desc(), Match.id.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        return stmt

    async def _cards(self, rows) -> list[dict]:
        """The cards a page of pairs is painted from: two batch reads, none of them inside a loop.

        A partner whose account is gone leaves the list rather than raising for it — the name, the age
        and the city a card shows live on a row that no longer exists, and the list has answered this
        way since stage 33. The row is not hidden from the page's boundary: it was read, so the link
        still points past it, and the reader never sees a pair the server cannot name.
        """
        if not rows:
            return []
        peer_ids = [row.other_id for row in rows]
        profiles = {p.user_id: p for p in await self.users.get_profile_cards(peer_ids)}
        photos = await self.users.get_primary_photos(peer_ids)
        today = utc_today()
        cards: list[dict] = []
        for row in rows:
            profile = profiles.get(row.other_id)
            if profile is None:
                continue
            cards.append(
                {
                    "match_id": str(row.id),
                    "user_id": str(row.other_id),
                    "name": profile.name,
                    "age": age_years(profile.birth_date, today),
                    "city": profile.city,
                    "photo_url": photos.get(row.other_id),
                    "compatibility": to_percent(row.compatibility_score),
                    "last_message": row.body,
                    "last_message_at": row.line_at,
                    "unread": int(row.unread),
                    "created_at": row.created_at,
                }
            )
        return cards

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
