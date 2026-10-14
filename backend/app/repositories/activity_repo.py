from __future__ import annotations

import uuid

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity, ActivityPreference, Match, Recommendation


class ActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[Activity]:
        stmt = select(Activity).order_by(Activity.id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_by_ids(self, activity_ids: list[int]) -> dict[int, Activity]:
        """One read for a page of ids, keyed so the caller keeps its own order."""
        if not activity_ids:
            return {}
        stmt = select(Activity).where(Activity.id.in_(activity_ids))
        return {a.id: a for a in (await self.session.execute(stmt)).scalars().all()}

    async def get_by_slug(self, slug: str) -> Activity | None:
        stmt = select(Activity).where(Activity.slug == slug)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_cities(self, cities: list[str]) -> list[Activity]:
        """Activities available in any of the given cities, plus city-agnostic ones."""
        stmt = select(Activity).order_by(Activity.id)
        rows = list((await self.session.execute(stmt)).scalars().all())
        lowered = {c.lower() for c in cities}
        return [a for a in rows if not a.cities or any(c.lower() in lowered for c in a.cities)]

    async def set_preference(
        self, user_id: uuid.UUID, activity_id: int, score: float, match_id: uuid.UUID
    ) -> None:
        # Constraint-decided write: tapping the same activity twice reaches the server
        # before the first insert commits.
        await self.session.execute(
            pg_insert(ActivityPreference)
            .values(
                user_id=user_id, activity_id=activity_id, score=score, match_id=match_id
            )
            .on_conflict_do_update(
                constraint="uq_activity_pref",
                set_={"score": score, "proposed": True},
            )
        )

    async def set_declined(
        self, user_id: uuid.UUID, activity_id: int, match_id: uuid.UUID, declined: bool
    ) -> None:
        """Record that this person pushed the card away — or took that back.

        The row is the same one a proposal writes, and `proposed` is left alone by the update:
        an idea that already went into the pair's chat stays an idea that went into the chat,
        whatever the person decides about it afterwards.
        """
        await self.session.execute(
            pg_insert(ActivityPreference)
            .values(
                user_id=user_id,
                activity_id=activity_id,
                match_id=match_id,
                proposed=False,
                declined=declined,
            )
            .on_conflict_do_update(constraint="uq_activity_pref", set_={"declined": declined})
        )

    async def decisions_by_pair(
        self, match_id: uuid.UUID, activity_ids: list[int]
    ) -> tuple[dict[uuid.UUID, set[int]], dict[uuid.UUID, set[int]]]:
        """Which of these cards each half of the pair proposed, and which this person pushed away.

        One statement answers for both people: the questions are the same shape — whose decisions
        does this table record for this pair — and asking them twice, once per person, would cost
        the page a second round trip to say what one row of the answer already says. Both are
        keyed by the person who acted, because a card one half proposed is not a card the other
        half has used: the page still answers per viewer, it just also names the other half's
        proposal. A refusal is keyed too and deliberately not sent out — see the service.
        """
        if not activity_ids:
            return {}, {}
        stmt = (
            select(
                ActivityPreference.user_id,
                ActivityPreference.activity_id,
                ActivityPreference.proposed,
                ActivityPreference.declined,
            )
            .where(
                ActivityPreference.match_id == match_id,
                ActivityPreference.activity_id.in_(activity_ids),
            )
        )
        proposed: dict[uuid.UUID, set[int]] = {}
        declined: dict[uuid.UUID, set[int]] = {}
        for user_id, activity_id, was_proposed, was_declined in (
            await self.session.execute(stmt)
        ).all():
            if was_proposed:
                proposed.setdefault(user_id, set()).add(activity_id)
            if was_declined:
                declined.setdefault(user_id, set()).add(activity_id)
        return proposed, declined

    async def replace_recommendations(
        self, match_id: uuid.UUID, recs: list[dict]
    ) -> None:
        await self.session.execute(delete(Recommendation).where(Recommendation.match_id == match_id))
        if not recs:
            return
        # One statement for the page. Inserting row by row sent eight round trips for the
        # eight cards a pair is shown, and a screen that regenerates its page on a cold cache
        # paid for them on every one of those reads.
        values = [
            {
                "match_id": match_id,
                "activity_id": item["activity_id"],
                "score": item["score"],
                "explanation": item["explanation"],
                "position": position,
            }
            for position, item in enumerate(recs)
        ]
        stmt = pg_insert(Recommendation).values(values)
        await self.session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_match_activity_rec",
                set_={
                    "score": stmt.excluded.score,
                    "explanation": stmt.excluded.explanation,
                    "position": stmt.excluded.position,
                },
            )
        )

    async def list_recommendations(self, match_id: uuid.UUID) -> list[Recommendation]:
        stmt = (
            select(Recommendation)
            .where(Recommendation.match_id == match_id)
            .order_by(Recommendation.position)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def invalidate_for_user(self, user_id: uuid.UUID) -> int:
        """Drop the cached recommendations of every match this user is in.

        A page of activities is scored once and then served from the database, which is
        only honest while both profiles still say what they said then. Once one of them
        moves city, re-takes the test or edits their interests, the stored reasons
        describe somebody who no longer exists on this pair.
        """
        matches = select(Match.id).where(or_(Match.user_a_id == user_id, Match.user_b_id == user_id))
        stmt = delete(Recommendation).where(Recommendation.match_id.in_(matches))
        return (await self.session.execute(stmt)).rowcount or 0
