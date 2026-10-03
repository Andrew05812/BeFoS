from __future__ import annotations

import json
import uuid

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.security import decode_token
from app.models import Match
from app.repositories.chat_repo import ChatRepository
from app.websocket.manager import manager

logger = get_logger(__name__)

router = APIRouter()

MAX_BODY_CHARS = 4000


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


async def _still_belongs_to_match(match_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """The pair can stop existing while a socket for it is open (a block, a deletion)."""
    async with AsyncSessionLocal() as session:
        match = await session.get(Match, match_id)
        return bool(match and user_id in (match.user_a_id, match.user_b_id))


def parse_client_frame(raw: object) -> dict | None:
    """A frame is a JSON object or nothing at all; a malformed one must not end the socket."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


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
    # A client that joins a room nobody is watching would otherwise show the peer as
    # offline until the peer's next state change, so the room's truth is stated once on
    # entry as well as on every change.
    for peer in manager.presence(match_id) - {user_id}:
        await manager.send_personal(
            websocket, {"type": "presence", "user_id": str(peer), "online": True}
        )
    await manager.broadcast_to_match(
        match_id,
        {"type": "presence", "user_id": str(user_id), "online": True},
        exclude=websocket,
    )

    try:
        while True:
            try:
                raw: object = await websocket.receive_text()
            except WebSocketDisconnect:
                raise
            except Exception:
                # A binary frame cannot be read as text; the socket itself is still usable.
                raw = None
            data = parse_client_frame(raw)
            if data is None:
                # One malformed frame is a bad message, not a dead connection.
                await manager.send_personal(
                    websocket, {"type": "error", "message": "Invalid frame."}
                )
                continue

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
                raw_body = data.get("body")
                body = raw_body.strip() if isinstance(raw_body, str) else ""
                if not body or len(body) > MAX_BODY_CHARS:
                    await manager.send_personal(
                        websocket, {"type": "error", "message": "Invalid message body."}
                    )
                    continue
                if not await _still_belongs_to_match(match_id, user_id):
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                client_msg_id = data.get("client_msg_id")
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
        pass
    except Exception:  # pragma: no cover
        logger.exception("WS error match=%s user=%s", match_id, user_id)
    finally:
        manager.disconnect(match_id, websocket)
        await manager.broadcast_to_match(
            match_id, {"type": "presence", "user_id": str(user_id), "online": False}
        )
