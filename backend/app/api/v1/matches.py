from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.compatibility.universe import build_universe
from app.core.database import get_session
from app.core.exceptions import NotFoundError
from app.models import Interest, Match, User
from app.schemas.schemas import (
    CategoryScoreOut,
    CompatibilityOut,
    ExplanationItemOut,
    MatchListResponse,
    MatchSummary,
    MeetingTimeIn,
    RecommendationListResponse,
    RecommendationOut,
    UniverseLayerOut,
    UniverseNodeOut,
    UniverseOut,
)
from app.services.compatibility_service import CompatibilityService
from app.services.matches_service import MatchesService
from app.services.chat_service import message_frame
from app.services.recommendation_service import RecommendationService
from app.websocket.manager import manager

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
            CategoryScoreOut(
                category=c.key,
                label=c.label,
                score=c.percent,
                weight=c.weight,
                has_data=c.has_data,
            )
            for c in result.categories
        ],
        strengths=[ExplanationItemOut(**vars(i)) for i in explanation.strengths],
        differences=[ExplanationItemOut(**vars(i)) for i in explanation.differences],
        shared_interests=[shared_titles.get(s, s) for s in explanation.shared_interests],
    )


@router.get("/{match_id}/universe", response_model=UniverseOut)
async def match_universe(
    match_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    match = await session.get(Match, match_id)
    if match is None or current_user.id not in (match.user_a_id, match.user_b_id):
        raise NotFoundError("Match not found.")

    # The pair's own order, not requester-first: both partners open one map of two worlds.
    service = CompatibilityService(session)
    a, b = await service.pair_inputs(match.user_a_id, match.user_b_id)

    # Titles are resolved before the map is built, so an interest carries its catalogue name into
    # its own label and into its suggestion sentence instead of leaving the slug inside the text.
    slugs = a.interests | b.interests
    titles: dict[str, str] = {}
    if slugs:
        rows = (await session.execute(select(Interest).where(Interest.slug.in_(slugs)))).scalars().all()
        titles = {i.slug: i.name for i in rows}

    result = service.score_inputs(a, b)
    universe = build_universe(a, b, result, titles)

    return UniverseOut(
        overall=universe.overall_percent,
        engine_version=universe.version,
        a_user_id=str(match.user_a_id),
        b_user_id=str(match.user_b_id),
        layers=[
            UniverseLayerOut(
                category=layer.key,
                label=layer.label,
                score=layer.score,
                weight=layer.weight,
                has_data=layer.has_data,
                coverage=layer.coverage,
                confidence=layer.confidence,
                nodes=[
                    UniverseNodeOut(**{**vars(node), "questions": list(node.questions)})
                    for node in layer.nodes
                ],
            )
            for layer in universe.layers
        ],
        story=list(universe.story),
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
                activity=r["activity"],
                score=r["score"],
                position=r["position"],
                reasons=r["reasons"],
                selected=r["selected"],
                partner_selected=r["partner_selected"],
                declined=r["declined"],
                my_meeting_time=r["my_meeting_time"],
                partner_meeting_time=r["partner_meeting_time"],
                i_accepted_time=r["i_accepted_time"],
                agreed_time=r["agreed_time"],
            )
            for r in recs
        ],
    )


@router.post("/{match_id}/recommendations/{activity_id}/select", status_code=204)
async def select_recommendation(
    match_id: uuid.UUID,
    # `activities.id` is a PostgreSQL `integer`, so a larger number names no activity and
    # cannot be looked up. Passed along, it reached the catalogue read, the driver refused
    # the value, and the client got a 500 for a url that is simply not a valid one.
    activity_id: int = Path(le=2**31 - 1),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Put an idea to the pair. The card's tap and the plan's confirmation are one verb, so the
    pair's chat gets the same proposal card from either door.

    The line arrives as a frame rather than as a sentence the app types into the message field: a
    typed bubble carries no plan id, so the other half could not tap it to open the arrangement it
    records.
    """
    service = RecommendationService(session)
    events = await service.mark_selected(match_id, current_user.id, activity_id)
    for event in events:
        await manager.broadcast_to_match(match_id, message_frame(event))
    return None


@router.post("/{match_id}/recommendations/{activity_id}/decline", status_code=204)
async def decline_recommendation(
    match_id: uuid.UUID,
    activity_id: int = Path(le=2**31 - 1),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Push one idea out of the page of the person asking.

    Named by two routes rather than by a flag on the select route because the two taps mean
    opposite things to the pair. What the push says out loud depends on whose idea it was: a card
    this person never took up is an edit of their own list and stays private, while pushing away
    an idea the other half put to the pair is an answer to them, and the answer goes into their
    chat as a line about that plan.
    """
    service = RecommendationService(session)
    events = await service.set_declined(match_id, current_user.id, activity_id, True)
    for event in events:
        await manager.broadcast_to_match(match_id, message_frame(event))
    return None


@router.delete("/{match_id}/recommendations/{activity_id}/decline", status_code=204)
async def restore_recommendation(
    match_id: uuid.UUID,
    activity_id: int = Path(le=2**31 - 1),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Take a refusal back, which puts the card where this person's page shows it again.

    The pair's chat hears about it when the refusal it undid was an answer they had received: an
    idea they were told about and then told no comes back with a line of its own.
    """
    service = RecommendationService(session)
    events = await service.set_declined(match_id, current_user.id, activity_id, False)
    for event in events:
        await manager.broadcast_to_match(match_id, message_frame(event))
    return None


@router.put("/{match_id}/recommendations/{activity_id}/time", status_code=204)
async def propose_meeting_time(
    match_id: uuid.UUID,
    payload: MeetingTimeIn,
    activity_id: int = Path(le=2**31 - 1),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Name the moment this person would meet for this idea, or move the one they named.

    A PUT rather than a POST: the pair has one row per person per card, so a second tap on a
    different hour replaces the offer instead of adding a second one for the other half to choose
    between.

    204 stays: the tap answers the card, and the card reloads its own page. What the pair's chat
    gets is the socket frame below, sent only after the transaction that wrote the line committed —
    a broadcast of a row that was rolled back would put a plan in front of a pair whose database
    holds none, and the line would arrive again on the next history read anyway.
    """
    service = RecommendationService(session)
    events = await service.propose_time(match_id, current_user.id, activity_id, payload.when)
    for event in events:
        await manager.broadcast_to_match(match_id, message_frame(event))
    return None


@router.post("/{match_id}/recommendations/{activity_id}/time/accept", status_code=204)
async def accept_meeting_time(
    match_id: uuid.UUID,
    payload: MeetingTimeIn,
    activity_id: int = Path(le=2**31 - 1),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Agree to the moment the other half named. The instant is sent back rather than read off the
    row here, because the value the person saw is the value they answered; if it moved since, this
    answers 409 and the page reloads the offer instead of agreeing to an unseen one.

    The agreement belongs to the conversation as much as to the card: an hour the pair landed on is
    said in their chat, on both screens, without either of them reopening anything.
    """
    service = RecommendationService(session)
    events = await service.accept_time(match_id, current_user.id, activity_id, payload.when)
    for event in events:
        await manager.broadcast_to_match(match_id, message_frame(event))
    return None
