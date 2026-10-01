from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.database import get_session
from app.models import User
from app.schemas.schemas import DiscoveryResponse, LikeResponse, PassResponse
from app.services.discovery_service import DiscoveryService
from app.services.match_service import MatchService

router = APIRouter(tags=["discovery"])


@router.get("/discover", response_model=DiscoveryResponse)
async def discover(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    city: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = DiscoveryService(session)
    data = await service.feed(current_user.id, limit=limit, offset=offset, city_override=city)
    return DiscoveryResponse(**data)


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
