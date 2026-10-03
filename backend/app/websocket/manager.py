from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from fastapi import WebSocket, status

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Connection:
    websocket: WebSocket
    user_id: uuid.UUID


class ConnectionManager:
    """Tracks active WebSocket connections grouped by match id."""

    def __init__(self) -> None:
        self._rooms: dict[uuid.UUID, list[Connection]] = {}

    async def connect(self, match_id: uuid.UUID, websocket: WebSocket, user_id: uuid.UUID) -> None:
        await websocket.accept()
        self._rooms.setdefault(match_id, []).append(Connection(websocket, user_id))
        logger.info("WS connected match=%s user=%s", match_id, user_id)

    def disconnect(self, match_id: uuid.UUID, websocket: WebSocket) -> None:
        room = self._rooms.get(match_id)
        if not room:
            return
        self._rooms[match_id] = [c for c in room if c.websocket is not websocket]
        if not self._rooms[match_id]:
            self._rooms.pop(match_id, None)
        logger.info("WS disconnected match=%s", match_id)

    async def close_room(self, match_id: uuid.UUID) -> None:
        """End every socket for a pair that no longer exists.

        A block or a deletion removes the match row; the open sockets would otherwise
        keep reporting a live connection into a conversation that can no longer hold a
        message, and the client has no way to find that out.
        """
        for conn in self._rooms.pop(match_id, []):
            try:
                await conn.websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            except Exception:  # pragma: no cover - the socket is already going away
                logger.debug("WS close failed match=%s", match_id, exc_info=True)
        logger.info("WS room closed match=%s", match_id)

    async def broadcast_to_match(
        self,
        match_id: uuid.UUID,
        payload: dict,
        *,
        exclude: WebSocket | None = None,
        exclude_user: uuid.UUID | None = None,
    ) -> None:
        """Fan out to a match room.

        `exclude` drops one socket (the actor's own WS connection); `exclude_user`
        drops every socket of a user, which is what a REST-triggered receipt needs —
        the actor's REST call has no socket identity, but their own client must not
        be told "read" about a read they just performed.
        """
        room = list(self._rooms.get(match_id, []))
        for conn in room:
            if exclude is not None and conn.websocket is exclude:
                continue
            if exclude_user is not None and conn.user_id == exclude_user:
                continue
            try:
                await conn.websocket.send_json(payload)
            except Exception:  # pragma: no cover - network hiccup
                logger.warning("WS send failed match=%s", match_id, exc_info=True)
                self.disconnect(match_id, conn.websocket)

    async def send_personal(self, websocket: WebSocket, payload: dict) -> None:
        try:
            await websocket.send_json(payload)
        except Exception:  # pragma: no cover
            logger.warning("WS personal send failed", exc_info=True)

    def presence(self, match_id: uuid.UUID) -> set[uuid.UUID]:
        return {c.user_id for c in self._rooms.get(match_id, [])}


manager = ConnectionManager()
