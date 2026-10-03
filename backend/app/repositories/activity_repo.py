from __future__ import annotations

import uuid

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity, ActivityPreference, Recommendation


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

    async def set_preference(self, user_id: uuid.UUID, activity_id: int, score: float) -> None:
        # Constraint-decided write: tapping the same activity twice reaches the server
        # before the first insert commits.
        await self.session.execute(
            pg_insert(ActivityPreference)
            .values(user_id=user_id, activity_id=activity_id, score=score)
            .on_conflict_do_update(constraint="uq_activity_pref", set_={"score": score})
        )

    async def replace_recommendations(
        self, match_id: uuid.UUID, recs: list[dict]
    ) -> None:
        await self.session.execute(delete(Recommendation).where(Recommendation.match_id == match_id))
        for position, item in enumerate(recs):
            await self.session.execute(
                pg_insert(Recommendation)
                .values(
                    match_id=match_id,
                    activity_id=item["activity_id"],
                    score=item["score"],
                    explanation=item["explanation"],
                    position=position,
                )
                .on_conflict_do_update(
                    constraint="uq_match_activity_rec",
                    set_={
                        "score": item["score"],
                        "explanation": item["explanation"],
                        "position": position,
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
