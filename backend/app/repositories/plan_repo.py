from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Match, Message, SharedPlan, SharedPlanMember


class PlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _with_members(self):
        # Both halves are asked about every plan, so a plan without its two answer rows is not a
        # readable object — and loading them lazily would cost one statement per plan on the list
        # that shows a dozen of them.
        return select(SharedPlan).options(selectinload(SharedPlan.members))

    async def get(self, plan_id: uuid.UUID) -> SharedPlan | None:
        stmt = self._with_members().where(SharedPlan.id == plan_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def for_pair(self, match_id: uuid.UUID, activity_id: int) -> SharedPlan | None:
        stmt = self._with_members().where(
            SharedPlan.match_id == match_id, SharedPlan.activity_id == activity_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_match(self, match_id: uuid.UUID) -> list[SharedPlan]:
        stmt = (
            self._with_members()
            .where(SharedPlan.match_id == match_id)
            .order_by(SharedPlan.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_for_user(self, user_id: uuid.UUID) -> list[SharedPlan]:
        """Every plan of every pair this person is in.

        Through the `matches` row rather than through `shared_plan_members`: membership of a pair is
        what authorises the read, and a member row is one person's answer about a plan, not the proof
        they are allowed to see it. A plan whose members were rewritten by a bug would otherwise
        become visible to somebody outside the pair.
        """
        stmt = (
            self._with_members()
            .join(Match, Match.id == SharedPlan.match_id)
            .where(or_(Match.user_a_id == user_id, Match.user_b_id == user_id))
            .order_by(SharedPlan.starts_at.asc().nulls_last(), SharedPlan.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def matches_for(self, plans: list[SharedPlan]) -> dict[uuid.UUID, Match]:
        """The pairs behind a page of plans, in one read, keyed by the pair."""
        ids = sorted({plan.match_id for plan in plans})
        if not ids:
            return {}
        stmt = select(Match).where(Match.id.in_(ids))
        return {match.id: match for match in (await self.session.execute(stmt)).scalars().all()}

    async def events(self, plan_id: uuid.UUID, *, limit: int = 30) -> list[Message]:
        """What the pair's plan said, oldest first — the history the detail screen shows.

        Read off the conversation rather than from a second journal table on purpose: the lines in
        `messages` are the same ones the pair's chat already carries, so the plan's history and the
        chat's record of it cannot tell two different stories about one tap.
        """
        stmt = (
            select(Message)
            .where(Message.plan_id == plan_id, Message.is_deleted.is_(False))
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        rows.reverse()
        return rows

    async def add_member(self, plan_id: uuid.UUID, user_id: uuid.UUID) -> SharedPlanMember:
        member = SharedPlanMember(plan_id=plan_id, user_id=user_id)
        self.session.add(member)
        await self.session.flush()
        return member
