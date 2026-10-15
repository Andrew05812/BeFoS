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
    TestProfileOut,
    TestResultOut,
    TraitAxisOut,
)
from app.services.test_service import TestService

router = APIRouter(prefix="/tests", tags=["tests"])


def _bands_and_axes(
    scores: dict[str, float], vector: dict[str, dict[str, float]]
) -> tuple[list[CategoryScoreOut], list[TraitAxisOut]]:
    """The two lists a finished profile answers with, built from one band per score and one vector.

    Both routes that hand a person their own profile come through here — the one that scores the
    answers and the one that reads that scoring back weeks later — so a band and the positions it is
    the average of cannot agree on the results screen and disagree on the profile screen.
    """
    from app.compatibility.traits import CATEGORY_BY_KEY, TRAIT_CATEGORIES, describe_side

    categories = [
        CategoryScoreOut(
            category=key,
            label=CATEGORY_BY_KEY.get(key).label if key in CATEGORY_BY_KEY else key,
            score=int(round(value * 100)),
            weight=0.0,
            # A band this response lists is a band the person answered: ``build_vector`` leaves a
            # category out of ``categories`` entirely when none of its traits carry an answer, so
            # there is no filler half to name here.
            has_data=True,
        )
        for key, value in sorted(scores.items())
    ]
    axes = [
        TraitAxisOut(
            category=category.key,
            trait=trait.key,
            label=trait.label,
            value=value,
            side=describe_side(value, trait.low_label, trait.high_label),
        )
        for category in TRAIT_CATEGORIES
        for trait in category.traits
        # Only positions the answers actually produced. An axis walked straight out of the
        # taxonomy would print a measured place for a question nobody answered, and the write
        # path keeps the vector and the taxonomy in step, so nothing here has to be named twice.
        if (value := vector.get(category.key, {}).get(trait.key)) is not None
    ]
    return categories, axes


@router.get("", response_model=TestListResponse)
async def list_tests(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = TestService(session)
    questions = await service.list_questions()
    # One read of the person's own answers carries everything this response needs beyond the
    # catalogue itself: how many answers there are, which option of each question to mark, and
    # how far each category has come. Counting them was a separate query and still left the
    # screen unable to say what the person had already answered.
    choices = await service.answer_choices(current_user.id)
    return TestListResponse(
        questions=[
            QuestionOut.model_validate(q).model_copy(
                update={"selected_option_id": choices.get(q.id)}
            )
            for q in questions
        ],
        # The response carries the whole catalog, so its size is counted from the rows it sends
        # rather than asked of the database next to the read that just listed them.
        total=len(questions),
        # Every stored row counts — the same set ``GET /tests/progress`` counts, because the two
        # places a person can compare their own progress have to agree about its size.
        answered=len(choices),
        categories=service.category_summary(questions, choices),
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
    categories, axes = _bands_and_axes(result["categories"], result["vector"])
    return TestResultOut(categories=categories, axes=axes, completed_at=None)


@router.get("/profile", response_model=TestProfileOut)
async def get_profile(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = TestService(session)
    stored = await service.stored_profile(current_user.id)
    if stored is None:
        # Nothing has ever scored this person's answers. An empty profile is the honest answer: a
        # band invented here would be a percent the questionnaire never produced, and the screen
        # reads what is still missing from ``GET /tests/progress`` rather than from a zero.
        return TestProfileOut(categories=[], axes=[], updated_at=None)
    categories, axes = _bands_and_axes(stored["scores"], stored["vector"])
    return TestProfileOut(categories=categories, axes=axes, updated_at=stored["updated_at"])
