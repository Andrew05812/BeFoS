from __future__ import annotations

import uuid
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.security import decode_token
from app.models import Match, User
from app.repositories.chat_repo import ChatRepository
from app.websocket.manager import manager

logger = get_logger(__name__)

router = APIRouter()


async def _authenticate(token: str | None) -> uuid.UUID | None:
    if not token:
        return None
    try:
        payload = decode_token(token, "access")
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    try:
        return uuid.UUID(payload["sub"])
    except (ValueError, KeyError):
        return None


@router.websocket("/ws/chat/{match_id}")
async def chat_socket(
    websocket: WebSocket,
    match_id: uuid.UUID,
    token: str | None = Query(default=None),
) -> None:
    user_id = await _authenticate(token)
    if user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with AsyncSessionLocal() as session:
        match = await session.get(Match, match_id)
        if match is None or user_id not in (match.user_a_id, match.user_b_id):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await manager.connect(match_id, websocket, user_id)
    other_id = match.user_b_id if match.user_a_id == user_id else match.user_a_id
    await manager.broadcast_to_match(
        match_id,
        {"type": "presence", "user_id": str(user_id), "online": True},
        exclude=websocket,
    )

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "typing":
                await manager.broadcast_to_match(
                    match_id,
                    {"type": "typing", "user_id": str(user_id), "typing": bool(data.get("typing", True))},
                    exclude=websocket,
                )

            elif msg_type == "read":
                async with AsyncSessionLocal() as session:
                    repo = ChatRepository(session)
                    await repo.mark_read(match_id, user_id)
                    await session.commit()
                await manager.broadcast_to_match(
                    match_id, {"type": "read", "user_id": str(user_id)}, exclude=websocket
                )

            elif msg_type == "message":
                body = (data.get("body") or "").strip()
                client_msg_id = data.get("client_msg_id")
                if not body or len(body) > 4000:
                    await manager.send_personal(
                        websocket, {"type": "error", "message": "Invalid message body."}
                    )
                    continue
                async with AsyncSessionLocal() as session:
                    repo = ChatRepository(session)
                    msg = await repo.add_message(match_id, user_id, body)
                    await session.commit()
                    payload = {
                        "type": "message",
                        "id": str(msg.id),
                        "client_msg_id": client_msg_id,
                        "match_id": str(match_id),
                        "sender_id": str(user_id),
                        "body": msg.body,
                        "created_at": msg.created_at.isoformat(),
                        "is_read": False,
                    }
                await manager.broadcast_to_match(match_id, payload)

            else:
                await manager.send_personal(
                    websocket, {"type": "error", "message": f"Unknown message type: {msg_type}"}
                )

    except WebSocketDisconnect:
        manager.disconnect(match_id, websocket)
        await manager.broadcast_to_match(
            match_id, {"type": "presence", "user_id": str(user_id), "online": False}
        )
    except Exception:  # pragma: no cover
        logger.exception("WS error match=%s user=%s", match_id, user_id)
        manager.disconnect(match_id, websocket)
