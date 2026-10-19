from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.database import get_session
from app.models import User
from app.schemas.schemas import MessageIn, MessageOut, MessagePage
from app.services.chat_service import ChatService, message_frame
from app.websocket.manager import manager

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
    if data["marked_read"]:
        # The reader consumed the backlog by opening the chat, so the receipt has to go out
        # from here — the follow-up POST /read marks nothing new and stays silent. Same shape
        # and same exclusion as the explicit endpoint, so the reader's own socket is not told
        # to mark its own messages read.
        await manager.broadcast_to_match(
            match_id, {"type": "read", "user_id": str(current_user.id)},
            exclude_user=current_user.id,
        )
    return MessagePage(
        messages=[MessageOut(**m) for m in data["messages"]],
        has_more=data["has_more"],
    )


@router.post("/{match_id}/messages", response_model=MessageOut, status_code=201)
async def send_message(
    match_id: uuid.UUID,
    payload: MessageIn,
    response: Response,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ChatService(session)
    msg, created = await service.send(
        match_id, current_user.id, payload.body, payload.client_msg_id
    )
    if not created:
        # The retry of a send that did land: the peer already has this message, so the
        # honest answer is the stored row with 200 and no second broadcast.
        response.status_code = 200
        return MessageOut(**msg)
    # REST sends must reach open sockets too, otherwise the peer only sees
    # the message after a history reload. The frame is the one the socket sends and the
    # accepted hour sends, so a pair reading a live line cannot tell doors apart.
    await manager.broadcast_to_match(match_id, message_frame(msg))
    return MessageOut(**msg)


@router.delete("/{match_id}/messages/{message_id}", status_code=204)
async def recall_message(
    match_id: uuid.UUID,
    message_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ChatService(session)
    await service.recall(match_id, current_user.id, message_id)
    # The line has to leave the screen that is already open, not only the page the next reload
    # brings. Both ends get the frame: the pair's other socket drops the sentence, and a second
    # device of the person who tapped finds the same empty place it just made.
    await manager.broadcast_to_match(
        match_id,
        {"type": "message_recalled", "match_id": str(match_id), "message_id": str(message_id)},
    )
    return None


@router.post("/{match_id}/read", status_code=200)
async def mark_read(
    match_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ChatService(session)
    count = await service.mark_read(match_id, current_user.id)
    if count:
        await manager.broadcast_to_match(
            match_id, {"type": "read", "user_id": str(current_user.id)},
            exclude_user=current_user.id,
        )
    return {"marked_read": count}
