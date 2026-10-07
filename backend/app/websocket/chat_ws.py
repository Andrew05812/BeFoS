from __future__ import annotations

import json
import time
import uuid

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.context import new_request_id, request_id
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.rate_limit import (
    websocket_frame_allowed,
    websocket_handshake_allowed,
)
from app.core.security import decode_token
from app.core.exceptions import NotFoundError
from app.models import Match, User
from app.services.chat_service import ChatService
from app.websocket.manager import manager

logger = get_logger(__name__)

router = APIRouter()

MAX_BODY_CHARS = 4000
MAX_CLIENT_MSG_ID_CHARS = 64


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


async def _refusal_reason(match_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
    """Why this pair may not hold a socket right now, or None if it may.

    An access token outlives the state behind it: a block or a deletion removes the match
    and disables the account, while the JWT still decodes. The rows are the truth, so the
    handshake and every write ask them rather than trusting the token.
    """
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None or user.is_deleted:
            return "user no longer exists"
        if not user.is_active:
            return "account is disabled"
        match = await session.get(Match, match_id)
        if match is None or user_id not in (match.user_a_id, match.user_b_id):
            return "caller is not part of the pair"
    return None


def client_msg_id_from(data: dict) -> tuple[str | None, str | None]:
    """Return the send's own name for the client plus an error, one of the two empty.

    The id is opaque text the client invented; the column is 64 wide, so an over-long one
    is refused instead of being stored truncated or blowing up the write.
    """
    raw = data.get("client_msg_id")
    if raw is None:
        return None, None
    if not isinstance(raw, str):
        return None, "client_msg_id must be text."
    cleaned = raw.strip()
    if not cleaned:
        return None, None
    if len(cleaned) > MAX_CLIENT_MSG_ID_CHARS:
        return None, f"client_msg_id is longer than {MAX_CLIENT_MSG_ID_CHARS} characters."
    return cleaned, None


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
    # A socket is one long request, and every line it produces — the handshake, the
    # writes, the close — has to be findable as belonging to the same connection.
    correlation = request_id.set(f"ws-{new_request_id()}")
    try:
        await _handle_socket(websocket, match_id, token)
    finally:
        request_id.reset(correlation)


async def _handle_socket(
    websocket: WebSocket, match_id: uuid.UUID, token: str | None
) -> None:
    # Before the token is even decoded: a handshake costs this route a socket, a JWT parse and
    # two row reads, and none of that should be free for whoever holds an address.
    if not websocket_handshake_allowed(websocket):
        logger.warning("socket refused, handshake limit reached (match=%s)", match_id)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = await _authenticate(token)
    if user_id is None:
        logger.warning("socket refused, no usable access token (match=%s)", match_id)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    reason = await _refusal_reason(match_id, user_id)
    if reason is not None:
        logger.warning(
            "socket refused, %s (match=%s user=%s)", reason, match_id, user_id
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    opened = time.perf_counter()
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
            if not websocket_frame_allowed(user_id):
                # A REST send is one request out of a bucketed minute; a socket can write
                # forever without ever passing the place a REST limiter would sit. The budget
                # is the same size as the default REST one and it counts malformed frames too,
                # because a junk frame is not cheaper than a text frame.
                await manager.send_personal(
                    websocket,
                    {"type": "error", "message": "Too many messages, slow down."},
                )
                continue
            data = parse_client_frame(raw)
            if data is None:
                # One malformed frame is a bad message, not a dead connection.
                await manager.send_personal(
                    websocket, {"type": "error", "message": "Invalid frame."}
                )
                continue

            msg_type = data.get("type")

            if msg_type == "typing":
                # The typing indicator is a signal that reaches the peer, so it is not allowed
                # to be the one frame that never asks the rows — the socket's authorisation has
                # to be as fresh for a dot in someone's header as it is for a stored message.
                if await _refusal_reason(match_id, user_id) is not None:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                await manager.broadcast_to_match(
                    match_id,
                    {"type": "typing", "user_id": str(user_id), "typing": bool(data.get("typing", True))},
                    # exclude_user, not exclude: a person on two devices is not their own peer.
                    # Dropping only this socket lets the other device show «печатает…» for text
                    # its own owner is typing, so the indicator must skip every socket of the actor.
                    exclude_user=user_id,
                )

            elif msg_type == "read":
                if await _refusal_reason(match_id, user_id) is not None:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                async with AsyncSessionLocal() as session:
                    # The receipt goes through ChatService.mark_read, the same door the REST route
                    # uses: it takes the pair lock before inserting, so a block dissolving this match
                    # either cascades the receipt away behind us or makes the mark find the match gone.
                    # Writing repo.mark_read directly here raced that window and the child insert threw
                    # a foreign-key violation, which killed the socket instead of refusing it.
                    service = ChatService(session)
                    try:
                        count = await service.mark_read(match_id, user_id)
                    except NotFoundError:
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                        return
                if count:
                    # Same contract as the REST `/matches/{id}/read`: the receipt fires only for
                    # messages this call actually marked, and exclude_user keeps it off every
                    # socket of the reader — a second device must not mark the reader's own sent
                    # messages «прочитано» when the peer has not read them.
                    await manager.broadcast_to_match(
                        match_id, {"type": "read", "user_id": str(user_id)}, exclude_user=user_id
                    )

            elif msg_type == "message":
                raw_body = data.get("body")
                body = raw_body.strip() if isinstance(raw_body, str) else ""
                if not body or len(body) > MAX_BODY_CHARS:
                    await manager.send_personal(
                        websocket, {"type": "error", "message": "Invalid message body."}
                    )
                    continue
                client_msg_id, id_error = client_msg_id_from(data)
                if id_error is not None:
                    await manager.send_personal(
                        websocket, {"type": "error", "message": id_error}
                    )
                    continue
                if await _refusal_reason(match_id, user_id) is not None:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                async with AsyncSessionLocal() as session:
                    # The write goes through ChatService.send, the same door the REST route uses:
                    # it takes the pair lock before inserting, so a block dissolving this match
                    # either cascades the message away behind us or makes the send find the match
                    # gone. Writing add_message directly here raced that window and the child insert
                    # threw a foreign-key violation, which killed the socket instead of refusing it.
                    service = ChatService(session)
                    try:
                        dto, created = await service.send(
                            match_id, user_id, body, client_msg_id
                        )
                    except NotFoundError:
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                        return
                    payload = {
                        "type": "message",
                        "id": dto["id"],
                        "client_msg_id": dto["client_msg_id"],
                        "match_id": str(match_id),
                        "sender_id": str(user_id),
                        "body": dto["body"],
                        "created_at": dto["created_at"].isoformat(),
                        "is_read": False,
                    }
                if created:
                    await manager.broadcast_to_match(match_id, payload)
                else:
                    # A retry of a send that already landed: the peer has the message, and
                    # the sender is the one still waiting for the answer.
                    await manager.send_personal(websocket, payload)

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
        logger.info(
            "socket closed match=%s user=%s after %d ms",
            match_id,
            user_id,
            round((time.perf_counter() - opened) * 1000),
        )
        await manager.broadcast_to_match(
            match_id, {"type": "presence", "user_id": str(user_id), "online": False}
        )
