from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.database import get_session
from app.models import User
from app.schemas.schemas import MessageIn, MessageOut, MessagePage
from app.services.chat_service import ChatService

router = APIRouter(prefix="/matches", tags=["chat"])


@router.get("/{match_id}/messages", response_model=MessagePage)
async def get_messages(
    match_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    before_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ChatService(session)
    data = await service.history(match_id, current_user.id, limit=limit, before_id=before_id)
    return MessagePage(
        messages=[MessageOut(**m) for m in data["messages"]],
        has_more=data["has_more"],
    )


@router.post("/{match_id}/messages", response_model=MessageOut, status_code=201)
async def send_message(
    match_id: uuid.UUID,
    payload: MessageIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ChatService(session)
    msg = await service.send(match_id, current_user.id, payload.body)
    return MessageOut(**msg)


@router.post("/{match_id}/read", status_code=200)
async def mark_read(
    match_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ChatService(session)
    count = await service.mark_read(match_id, current_user.id)
    return {"marked_read": count}
