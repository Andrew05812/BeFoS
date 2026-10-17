from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Profile, Report, ReportReview, User


class ModerationRepository:
    """The reads and the two writes the moderation surface is built on.

    Nothing here resolves a permission — `app/auth/deps.py:46` decides who may ask, and this
    module answers whoever asks. The separation is the point: a route that forgot the dependency
    would still not get a row, because the row cannot be reached without going through a
    function that the moderation service calls from behind that door.

    Two shapes are chosen rather than convenient. The queue is paged by a (created_at, id) pair
    and not by an offset, so a complaint arriving while somebody is on page one cannot shift page
    two under them; and the one row a review touches is read `FOR UPDATE`, which is what makes two
    moderators answering the same complaint a sequence instead of two overlapping verdicts.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_report(self, report_id: uuid.UUID, *, for_update: bool = False) -> Report | None:
        stmt = select(Report).where(Report.id == report_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def page(
        self,
        *,
        status: str | None,
        after: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> list[Report]:
        """One page of the queue, oldest complaint first."""
        stmt = select(Report).order_by(Report.created_at.asc(), Report.id.asc()).limit(limit)
        if status is not None:
            stmt = stmt.where(Report.status == status)
        if after is not None:
            # The pair comparison is the cursor: `id` breaks a tie between two complaints written
            # in the same second, which a bare `created_at >` would either drop or repeat.
            stmt = stmt.where(tuple_(Report.created_at, Report.id) > after)
        return list((await self.session.execute(stmt)).scalars().all())

    async def reviews_of(self, report_id: uuid.UUID) -> list[ReportReview]:
        stmt = (
            select(ReportReview)
            .where(ReportReview.report_id == report_id)
            .order_by(ReportReview.created_at.asc(), ReportReview.id.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_review(
        self,
        report_id: uuid.UUID,
        moderator_id: uuid.UUID,
        from_status: str,
        to_status: str,
        comment: str | None,
    ) -> ReportReview:
        row = ReportReview(
            report_id=report_id,
            moderator_id=moderator_id,
            from_status=from_status,
            to_status=to_status,
            comment=comment,
        )
        self.session.add(row)
        return row

    async def accounts_for(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, Any]:
        """The two accounts a complaint names, as little of them as a decision can be made on.

        A reviewer has to know who is accused and who accused them, and whether the accused still
        has an account anybody can see — the last part decides whether there is anything left to
        act on, since a deleted account has already removed itself. The questionnaire, the
        photographs, the lifestyle jsonb and the email address are not read here and are not sent
        by any moderation route.
        """
        if not user_ids:
            return {}
        stmt = (
            select(
                User.id,
                Profile.name,
                Profile.birth_date,
                Profile.city,
                Profile.is_hidden,
                User.is_deleted,
                User.is_moderator,
            )
            .join(Profile, Profile.user_id == User.id)
            .where(User.id.in_(user_ids))
        )
        return {row.id: row for row in (await self.session.execute(stmt)).all()}

    async def names_of(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Who wrote each line of a history, for the one read that shows the history."""
        if not user_ids:
            return {}
        stmt = select(Profile.user_id, Profile.name).where(Profile.user_id.in_(user_ids))
        return {row.user_id: row.name for row in (await self.session.execute(stmt)).all()}
