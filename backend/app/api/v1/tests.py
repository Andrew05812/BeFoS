from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.database import get_session
from app.models import User
from app.schemas.schemas import (
    AnswersIn,
    CategoryScoreOut,
    ProgressOut,
    QuestionOut,
    TestListResponse,
    TestResultOut,
)
from app.services.test_service import TestService

router = APIRouter(prefix="/tests", tags=["tests"])


@router.get("", response_model=TestListResponse)
async def list_tests(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = TestService(session)
    questions = await service.list_questions()
    progress = await service.progress(current_user.id)
    return TestListResponse(
        questions=[QuestionOut.model_validate(q) for q in questions],
        total=progress["total"],
        answered=progress["answered"],
    )


@router.get("/progress", response_model=ProgressOut)
async def get_progress(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = TestService(session)
    return ProgressOut(**await service.progress(current_user.id))


@router.post("/answers", response_model=ProgressOut)
async def submit_answers(
    payload: AnswersIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = TestService(session)
    progress = await service.save_answers(
        current_user.id, [a.model_dump() for a in payload.answers]
    )
    return ProgressOut(**progress)


@router.post("/complete", response_model=TestResultOut)
async def complete_tests(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = TestService(session)
    result = await service.complete(current_user.id)
    from app.compatibility.traits import CATEGORY_BY_KEY

    categories = [
        CategoryScoreOut(
            category=key,
            label=CATEGORY_BY_KEY.get(key).label if key in CATEGORY_BY_KEY else key,
            score=int(round(value * 100)),
            weight=0.0,
        )
        for key, value in sorted(result["categories"].items())
    ]
    return TestResultOut(categories=categories, completed_at=None)
