"""The pair's own reading surface: who, since when, how the two fit, what is agreed.

Every section of this answer already exists in the app — the match row, the compatibility
explanation, the pair's plans — and the phone could reach each of them on its own. It did not have
to: the deck and the pair pages have already taught this codebase that reading the same concern
twice for two people is a bug wearing a performance story, so the pair's profile is assembled from
one batch per concern instead of one request per section.

What this read deliberately does *not* do is call `PlanService.sync_pair`. Syncing the pair is what
lets an arrangement the preferences imply become a row — a write, and stage 124 decided the plans
screen owns it. A profile that synced would create rows just because someone looked, which is the
kind of surprise a reading surface must not carry. So the profile reports what the pair has already
agreed, and the hour that could still be born stays behind the door that can birth it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compatibility.explanation import CompatibilityExplanation
from app.compatibility.engine import CompatibilityResult
from app.core.exceptions import NotFoundError
from app.models import Match, Profile
from app.repositories.plan_repo import PlanRepository
from app.services.compatibility_service import CompatibilityService


@dataclass(frozen=True)
class PairPerson:
    user_id: uuid.UUID
    name: str


@dataclass(frozen=True)
class PairProfile:
    match_id: uuid.UUID
    since: datetime
    people: tuple[PairPerson, PairPerson]
    result: CompatibilityResult
    explanation: CompatibilityExplanation
    plans_total: int
    next_plan: object | None

    @property
    def next_plan_id(self) -> uuid.UUID | None:
        return self.next_plan.plan_id if self.next_plan is not None else None


@dataclass(frozen=True)
class UpcomingPlan:
    plan_id: uuid.UUID
    status: str
    starts_at: datetime


class PairProfileService:
    """One read of a pair, for either half of it, in the pair's own order."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.plans = PlanRepository(session)

    async def read(self, match_id: uuid.UUID, viewer_id: uuid.UUID) -> PairProfile:
        match = await self.session.get(Match, match_id)
        if match is None or viewer_id not in (match.user_a_id, match.user_b_id):
            # A pair that is not yours does not exist for you: the same answer the pair pages give,
            # so this route cannot be used to learn which pairing is real.
            raise NotFoundError("Match not found.")

        result, explanation = await CompatibilityService(self.session).explain_pair(
            match.user_a_id, match.user_b_id
        )
        rows = (
            await self.session.execute(
                select(Profile.user_id, Profile.name).where(
                    Profile.user_id.in_([match.user_a_id, match.user_b_id])
                )
            )
        ).all()
        by_id = {row.user_id: row.name for row in rows}
        missing = [uid for uid in (match.user_a_id, match.user_b_id) if uid not in by_id]
        if missing:
            raise NotFoundError("Profile not found.")
        people = (
            PairPerson(match.user_a_id, by_id[match.user_a_id]),
            PairPerson(match.user_b_id, by_id[match.user_b_id]),
        )

        rows_of_plan = await self.plans.list_for_match(match_id)
        upcoming = sorted(
            (
                UpcomingPlan(plan.id, plan.status, plan.starts_at)
                for plan in rows_of_plan
                if plan.starts_at is not None
            ),
            key=lambda item: (item.starts_at, item.plan_id),
        )
        return PairProfile(
            match_id=match.id,
            since=match.created_at,
            people=people,
            result=result,
            explanation=explanation,
            plans_total=len(rows_of_plan),
            next_plan=upcoming[0] if upcoming else None,
        )
