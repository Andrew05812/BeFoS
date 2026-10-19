from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.database import get_session
from app.models import User
from app.schemas.schemas import DiscoveryResponse, LikedMeResponse, LikeResponse, PassResponse
from app.services.discovery_service import DiscoveryService
from app.services.match_service import MatchService

router = APIRouter(tags=["discovery"])


@router.get("/discover", response_model=DiscoveryResponse)
async def discover(
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """One page of the viewer's deck, and the cursor for the next one.

    No offset: the deck is ranked once and paging moves by rank, so liking or passing
    between requests cannot shift a card into or out of the page being asked for.
    """
    service = DiscoveryService(session)
    data = await service.feed(current_user.id, limit=limit, cursor=cursor)
    return DiscoveryResponse(**data)


@router.get("/discover/liked-me", response_model=LikedMeResponse)
async def liked_me(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Who tapped the account, newest tap first, at most fifty of them.

    The tap is written by the route below and, until this one existed, could be read back only as
    a yes-or-no about one named stranger. This answers the account's own question — «кто меня
    выбрал» — and says with it whether more taps stand behind the page.
    """
    service = DiscoveryService(session)
    data = await service.liked_me(current_user.id)
    return LikedMeResponse(**data)


@router.post("/users/{user_id}/like", response_model=LikeResponse)
async def like_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = MatchService(session)
    result = await service.like(current_user.id, user_id)
    return LikeResponse(**result)


@router.post("/users/{user_id}/pass", response_model=PassResponse)
async def pass_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = MatchService(session)
    result = await service.pass_user(current_user.id, user_id)
    return PassResponse(**result)
