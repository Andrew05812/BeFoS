from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.tracker import Event, tracker
from app.core.exceptions import NotFoundError
from app.models import Match
from app.recommendations.engine import ActivitySignal, UserSignal, recommend
from app.repositories.activity_repo import ActivityRepository
from app.repositories.social_repo import SocialRepository
from app.repositories.user_repo import UserRepository


class RecommendationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.activities = ActivityRepository(session)
        self.users = UserRepository(session)
        self.social = SocialRepository(session)

    async def _require_match(self, match_id: uuid.UUID, user_id: uuid.UUID) -> Match:
        match = await self.session.get(Match, match_id)
        # The same row answered through the same route family has to give the same refusal as
        # `ChatService._require_membership` and `GET /matches/{id}`; a 403 here would say "this
        # pair exists, you are just not in it".
        if match is None or not (match.user_a_id == user_id or match.user_b_id == user_id):
            raise NotFoundError("Match not found.")
        return match

    async def _signal(self, user_id: uuid.UUID) -> UserSignal:
        profile = await self.users.get_profile_with_user(user_id)
        from app.repositories.test_repo import TestRepository

        cp = await TestRepository(self.session).get_compatibility_profile(user_id)
        return UserSignal(
            interests={i.slug for i in profile.interests} if profile else set(),
            vector=cp.vector if cp and isinstance(cp.vector, dict) else {},
            city=profile.city if profile else "",
            dating_goal=profile.dating_goal if profile else "",
            interest_titles={i.slug: i.name for i in profile.interests} if profile else {},
        )

    async def for_match(self, match_id: uuid.UUID, user_id: uuid.UUID, *, force: bool = False) -> list[dict]:
        match = await self._require_match(match_id, user_id)

        existing = await self.activities.list_recommendations(match_id)
        if existing and not force:
            tracker.track(Event.RECOMMENDATION_VIEWED, str(user_id), match=str(match_id))
            return await self._hydrate(existing)

        other_id = match.other_user(user_id)
        a = await self._signal(match.user_a_id)
        b = await self._signal(match.user_b_id)

        cities = list({c for c in (a.city, b.city) if c})
        catalogue = await self.activities.list_for_cities(cities)
        signals = [
            ActivitySignal(
                activity_id=act.id,
                slug=act.slug,
                title=act.title,
                category=act.category,
                interests=list(act.interests),
                cities=list(act.cities),
                energy=act.energy,
                social=act.social,
            )
            for act in catalogue
        ]
        scored = recommend(signals, a, b, top_n=8)

        recs = [
            {
                "activity_id": s.activity_id,
                "score": round(s.score, 4),
                "explanation": {"reasons": s.reasons},
            }
            for s in scored
        ]
        # The pair advisory lock is the same one `block` (stage 9), `delete_account`'s purge
        # (stage 13) and every chat write (stages 11–12) already serialise on. Without it the
        # wide window between the initial membership read and the INSERT below is a
        # read-then-write race on `recommendations.match_id`, which FKs `matches.id ON DELETE
        # CASCADE`: a concurrent dissolve commits its `DELETE FROM matches` here, the child
        # INSERT references an absent parent, and asyncpg raises `ForeignKeyViolationError`
        # — HTTP 500 on `GET /matches/{id}/recommendations?force=true`. Taking the lock makes
        # the two writers take turns: whoever commits last either writes under the lock (and
        # the later dissolve cascades the row away, 200 then a follow-up 404) or lands first
        # and the post-lock re-check via `select(Match.id)` — fresh snapshot, not the
        # identity map — answers the same 404 that a write into an absent match already gives.
        await self.social.lock_pair(match.user_a_id, match.user_b_id)
        if not await self.social.match_still_present(match_id):
            raise NotFoundError("Match not found.")

        await self.activities.replace_recommendations(match_id, recs)
        await self.session.commit()
        tracker.track(Event.RECOMMENDATION_VIEWED, str(user_id), match=str(match_id), count=len(recs))
        stored = await self.activities.list_recommendations(match_id)
        return await self._hydrate(stored)

    async def _hydrate(self, stored: list) -> list[dict]:
        # The catalogue rows are read once for the whole page: one round trip per card
        # made opening the tab cost eight queries to fetch eight rows of the same table.
        by_id = await self.activities.get_by_ids([rec.activity_id for rec in stored])
        out: list[dict] = []
        for rec in stored:
            act = by_id.get(rec.activity_id)
            if act is None:
                continue
            reasons = rec.explanation.get("reasons", []) if isinstance(rec.explanation, dict) else []
            out.append(
                {
                    "activity": {
                        "id": act.id,
                        "slug": act.slug,
                        "title": act.title,
                        "description": act.description,
                        "category": act.category,
                        "energy": act.energy,
                        "social": act.social,
                        "cost": act.cost,
                    },
                    "score": int(round(rec.score * 100)),
                    "position": rec.position,
                    "reasons": reasons,
                }
            )
        out.sort(key=lambda r: r["position"])
        return out

    async def mark_selected(self, match_id: uuid.UUID, user_id: uuid.UUID, activity_id: int) -> None:
        await self._require_match(match_id, user_id)
        # The id arrives from the request url, so it is a claim about the catalogue rather
        # than a fact from it. Left unchecked it reached a foreign key and the database
        # answered with an integrity error, which the client saw as a 500.
        known = await self.activities.get_by_ids([activity_id])
        if activity_id not in known:
            raise NotFoundError("Activity not found.")
        await self.activities.set_preference(user_id, activity_id, 1.0)
        await self.session.commit()
        tracker.track(Event.RECOMMENDATION_SELECTED, str(user_id), match=str(match_id), activity=activity_id)
