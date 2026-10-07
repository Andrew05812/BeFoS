from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.database import get_session
from app.core.exceptions import NotFoundError
from app.models import Interest, Match, User
from app.schemas.schemas import (
    CategoryScoreOut,
    CompatibilityOut,
    ExplanationItemOut,
    MatchListResponse,
    MatchSummary,
    RecommendationListResponse,
    RecommendationOut,
)
from app.services.compatibility_service import CompatibilityService
from app.services.matches_service import MatchesService
from app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("", response_model=MatchListResponse)
async def list_matches(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = MatchesService(session)
    matches = await service.list_matches(current_user.id)
    return MatchListResponse(matches=[MatchSummary(**m) for m in matches])


@router.get("/{match_id}")
async def get_match(
    match_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    match = await session.get(Match, match_id)
    if match is None or current_user.id not in (match.user_a_id, match.user_b_id):
        raise NotFoundError("Match not found.")
    other_id = match.other_user(current_user.id)
    from app.services.discovery_service import DiscoveryService

    # Membership was just proven against the `matches` row, so this is not the deck asking
    # whether it may introduce two strangers — `for_match_member` keeps the deck's visibility
    # rule for every other caller.
    profile = await DiscoveryService(session).get_public_profile(
        current_user.id, other_id, for_match_member=True
    )
    return {
        "match_id": str(match.id),
        "compatibility": int(round(match.compatibility_score * 100)),
        "created_at": match.created_at,
        "other_user": profile,
    }


@router.get("/{match_id}/compatibility", response_model=CompatibilityOut)
async def match_compatibility(
    match_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    match = await session.get(Match, match_id)
    if match is None or current_user.id not in (match.user_a_id, match.user_b_id):
        raise NotFoundError("Match not found.")
    other_id = match.other_user(current_user.id)

    service = CompatibilityService(session)
    result, explanation = await service.explain_pair(current_user.id, other_id)
    shared_titles: dict[str, str] = {}
    if explanation.shared_interests:
        rows = (
            await session.execute(select(Interest).where(Interest.slug.in_(explanation.shared_interests)))
        ).scalars().all()
        shared_titles = {i.slug: i.name for i in rows}
    return CompatibilityOut(
        overall=result.overall_percent,
        engine_version=result.version,
        categories=[
            CategoryScoreOut(category=c.key, label=c.label, score=c.percent, weight=c.weight)
            for c in result.categories
        ],
        strengths=[ExplanationItemOut(**vars(i)) for i in explanation.strengths],
        differences=[ExplanationItemOut(**vars(i)) for i in explanation.differences],
        shared_interests=[shared_titles.get(s, s) for s in explanation.shared_interests],
    )


@router.get("/{match_id}/recommendations", response_model=RecommendationListResponse)
async def match_recommendations(
    match_id: uuid.UUID,
    force: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = RecommendationService(session)
    recs = await service.for_match(match_id, current_user.id, force=force)
    return RecommendationListResponse(
        match_id=str(match_id),
        recommendations=[
            RecommendationOut(
                activity=r["activity"], score=r["score"], position=r["position"], reasons=r["reasons"]
            )
            for r in recs
        ],
    )


@router.post("/{match_id}/recommendations/{activity_id}/select", status_code=204)
async def select_recommendation(
    match_id: uuid.UUID,
    activity_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = RecommendationService(session)
    await service.mark_selected(match_id, current_user.id, activity_id)
    return None
