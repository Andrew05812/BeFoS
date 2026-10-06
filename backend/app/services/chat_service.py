from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.tracker import Event, tracker
from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.chat_repo import ChatRepository


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ChatRepository(session)

    async def _require_membership(self, match_id: uuid.UUID, user_id: uuid.UUID):
        match = await self.repo.get_match(match_id)
        # One answer for "this row is not yours" and "this row does not exist": a 403 on the
        # chat routes while `GET /matches/{id}` answers 404 for the same row on the same
        # condition turns the difference into an oracle that says which pairings are real.
        if match is None or not (match.user_a_id == user_id or match.user_b_id == user_id):
            raise NotFoundError("Match not found.")
        return match

    async def send(
        self,
        match_id: uuid.UUID,
        sender_id: uuid.UUID,
        body: str,
        client_msg_id: str | None = None,
    ) -> tuple[dict, bool]:
        """Write a send and report whether it is new, so a retry is not counted and shown twice."""
        body = (body or "").strip()
        if not body:
            raise ValidationError("Message cannot be empty.")
        if len(body) > 4000:
            raise ValidationError("Message is too long.")
        await self._require_membership(match_id, sender_id)
        msg, created = await self.repo.add_message(
            match_id, sender_id, body, (client_msg_id or "").strip() or None
        )
        await self.session.commit()
        if created:
            tracker.track(Event.MESSAGE_SENT, str(sender_id), match=str(match_id))
        # The only read row on a brand-new message is the sender's implicit one, and
        # `msg.reads` is not loaded here — state the known value instead of querying it.
        return self._to_dto(msg, sender_id, is_read=False), created

    async def history(
        self, match_id: uuid.UUID, user_id: uuid.UUID, *, limit: int = 50, before_id: uuid.UUID | None = None
    ) -> dict:
        await self._require_membership(match_id, user_id)
        messages = await self.repo.list_messages(match_id, limit=limit + 1, before_id=before_id)
        has_more = len(messages) > limit
        messages = messages[:limit]
        marked = await self.repo.mark_read(match_id, user_id)
        await self.session.commit()
        return {
            "messages": [self._to_dto(m, user_id) for m in messages],
            "has_more": has_more,
            # The count is reported so the caller can broadcast the receipt: opening a chat
            # is how a reader consumes a backlog, and if the mark happens here in silence the
            # follow-up POST /read finds nothing left and the sender never sees «прочитано».
            "marked_read": marked,
        }

    async def mark_read(self, match_id: uuid.UUID, user_id: uuid.UUID) -> int:
        await self._require_membership(match_id, user_id)
        count = await self.repo.mark_read(match_id, user_id)
        await self.session.commit()
        return count

    def _to_dto(self, msg, viewer_id: uuid.UUID, *, is_read: bool | None = None) -> dict:
        is_own = msg.sender_id == viewer_id
        if is_read is None:
            is_read = any(r.reader_id != msg.sender_id for r in msg.reads)
        return {
            "id": str(msg.id),
            "match_id": str(msg.match_id),
            "sender_id": str(msg.sender_id),
            "body": msg.body,
            "created_at": msg.created_at,
            "is_read": is_read,
            "is_own": is_own,
            "client_msg_id": msg.client_msg_id,
        }
