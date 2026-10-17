from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_moderator
from app.core.database import get_session
from app.models import User
from app.schemas.schemas import (
    ReportCard,
    ReportDetail,
    ReportsPage,
    ReviewIn,
    ReviewResult,
)
from app.services.moderation_service import MAX_PAGE, ModerationService

# `/reports` is the moderation surface, and it is a router of its own rather than more lines on
# `/users/{user_id}/report`: the complaint is written by an ordinary account and read by a
# moderator, and those two halves answer to different doors. Every route here takes
# `get_moderator` — the role is read from the account row per request, so an ordinary caller
# reaches none of them with a token that works everywhere else in the app.
router = APIRouter(prefix="/reports", tags=["moderation"])


@router.get("", response_model=ReportsPage)
async def list_reports(
    status: str | None = Query(default=None, max_length=20),
    after_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE),
    moderator: User = Depends(get_moderator),
    session: AsyncSession = Depends(get_session),
):
    """The queue, oldest complaint first, narrowed to one status when one is named."""
    service = ModerationService(session)
    data = await service.list_reports(status=status, after_id=after_id, limit=limit)
    return ReportsPage(
        reports=[ReportCard(**card) for card in data["reports"]],
        next_cursor=data["next_cursor"],
        has_more=data["has_more"],
    )


@router.get("/{report_id}", response_model=ReportDetail)
async def get_report(
    report_id: uuid.UUID,
    moderator: User = Depends(get_moderator),
    session: AsyncSession = Depends(get_session),
):
    """One complaint with the whole history of how it was decided."""
    service = ModerationService(session)
    return ReportDetail(**await service.detail(report_id))


@router.post("/{report_id}/review", response_model=ReviewResult)
async def review_report(
    report_id: uuid.UUID,
    payload: ReviewIn,
    moderator: User = Depends(get_moderator),
    session: AsyncSession = Depends(get_session),
):
    """Move the complaint and write the history row that says who moved it.

    One call, one transaction: the answer is the status the row holds now, which is the status the
    caller asked for only because the transition was legal at the moment the lock was taken.
    """
    service = ModerationService(session)
    data = await service.review(
        moderator.id, report_id, payload.status, payload.comment
    )
    return ReviewResult(**data)
