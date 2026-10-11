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
            .on_conflict_do_update(constraint="uq_activity_pref", set_={"score": score})
        )

    async def chosen_activity_ids(
        self, user_id: uuid.UUID, match_id: uuid.UUID, activity_ids: list[int]
    ) -> set[int]:
        """Which of these cards this person already chose for this pair.

        One read for the page, keyed on the three columns the tap is written under. It answers per
        viewer rather than per pair: the stored `recommendations` rows are shared by both halves, and
        a card one half proposed is not a card the other half has used.
        """
        if not activity_ids:
            return set()
        stmt = (
            select(ActivityPreference.activity_id)
            .where(
                ActivityPreference.user_id == user_id,
                ActivityPreference.match_id == match_id,
                ActivityPreference.activity_id.in_(activity_ids),
            )
        )
        return {row[0] for row in (await self.session.execute(stmt)).all()}

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
