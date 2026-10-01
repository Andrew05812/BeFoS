from __future__ import annotations

import uuid

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity, ActivityPreference, Recommendation


class ActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[Activity]:
        stmt = select(Activity).order_by(Activity.id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get(self, activity_id: int) -> Activity | None:
        return await self.session.get(Activity, activity_id)

    async def get_by_slug(self, slug: str) -> Activity | None:
        stmt = select(Activity).where(Activity.slug == slug)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_cities(self, cities: list[str]) -> list[Activity]:
        """Activities available in any of the given cities, plus city-agnostic ones."""
        stmt = select(Activity).order_by(Activity.id)
        rows = list((await self.session.execute(stmt)).scalars().all())
        lowered = {c.lower() for c in cities}
        return [a for a in rows if not a.cities or any(c.lower() in lowered for c in a.cities)]

    async def get_preference(self, user_id: uuid.UUID, activity_id: int) -> ActivityPreference | None:
        stmt = select(ActivityPreference).where(
            ActivityPreference.user_id == user_id, ActivityPreference.activity_id == activity_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def set_preference(self, user_id: uuid.UUID, activity_id: int, score: float) -> None:
        pref = await self.get_preference(user_id, activity_id)
        if pref is None:
            self.session.add(
                ActivityPreference(user_id=user_id, activity_id=activity_id, score=score)
            )
        else:
            pref.score = score
        await self.session.flush()

    async def replace_recommendations(
        self, match_id: uuid.UUID, recs: list[dict]
    ) -> list[Recommendation]:
        await self.session.execute(delete(Recommendation).where(Recommendation.match_id == match_id))
        created: list[Recommendation] = []
        for position, item in enumerate(recs):
            rec = Recommendation(
                match_id=match_id,
                activity_id=item["activity_id"],
                score=item["score"],
                explanation=item["explanation"],
                position=position,
            )
            self.session.add(rec)
            created.append(rec)
        await self.session.flush()
        return created

    async def list_recommendations(self, match_id: uuid.UUID) -> list[Recommendation]:
        stmt = (
            select(Recommendation)
            .where(Recommendation.match_id == match_id)
            .order_by(Recommendation.position)
        )
        return list((await self.session.execute(stmt)).scalars().all())
