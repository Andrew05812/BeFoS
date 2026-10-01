from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.database import get_session
from app.models import User
from app.services.safety_service import SafetyService

router = APIRouter(tags=["safety"])


class ReportIn(BaseModel):
    reason: str = Field(min_length=2, max_length=40)
    details: str | None = Field(default=None, max_length=1000)


class HiddenIn(BaseModel):
    hidden: bool


@router.post("/users/{user_id}/block", status_code=200)
async def block_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = SafetyService(session)
    return await service.block(current_user.id, user_id)


@router.post("/users/{user_id}/report", status_code=200)
async def report_user(
    user_id: uuid.UUID,
    payload: ReportIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = SafetyService(session)
    return await service.report(current_user.id, user_id, payload.reason, payload.details)


@router.post("/users/me/visibility", status_code=200)
async def set_visibility(
    payload: HiddenIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = SafetyService(session)
    return await service.set_hidden(current_user.id, payload.hidden)


@router.delete("/users/me", status_code=200)
async def delete_account(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = SafetyService(session)
    return await service.delete_account(current_user.id)
