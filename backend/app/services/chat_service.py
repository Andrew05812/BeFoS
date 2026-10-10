from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.tracker import Event, tracker
from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.chat_repo import ChatRepository
from app.repositories.social_repo import SocialRepository


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ChatRepository(session)
        self.social = SocialRepository(session)

    async def _require_membership(self, match_id: uuid.UUID, user_id: uuid.UUID):
        match = await self.repo.get_match(match_id)
        # One answer for "this row is not yours" and "this row does not exist": a 403 on the
        # chat routes while `GET /matches/{id}` answers 404 for the same row on the same
        # condition turns the difference into an oracle that says which pairings are real.
        if match is None or not (match.user_a_id == user_id or match.user_b_id == user_id):
            raise NotFoundError("Match not found.")
        return match

    async def _require_membership_for_write(self, match_id: uuid.UUID, user_id: uuid.UUID):
        """Membership that still holds at the instant a write into the chat begins.

        A write into a match — a sent message, a read receipt — reads the pair to authorise itself
        and then inserts a child row whose foreign key points at a row the block cascade removes
        (`messages`, and `message_reads` through them). A block taken between the read and the insert
        deletes that parent, and the insert then raises ``ForeignKeyViolation`` — an HTTP 500 to a
        user whose only act was to open or write a chat while being blocked. ``block`` serialises on
        the pair advisory lock (see ``SafetyService.block``), so taking the same lock here makes the
        two transactions take turns: the write happens under the lock and the later block cascades
        its rows away, or the block lands first and the re-check finds no match and returns the same
        404 a write into an absent match already gives. The first read only names the pair to lock;
        the authoritative check is made under the lock, and it reads the database rather than the
        session's identity map, which still holds the match this connection loaded moments ago.
        """
        match = await self._require_membership(match_id, user_id)
        await self.social.lock_pair(match.user_a_id, match.user_b_id)
        if not await self.repo.match_still_present(match_id):
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
        await self._require_membership_for_write(match_id, sender_id)
        msg, created = await self.repo.add_message(
            match_id, sender_id, body, (client_msg_id or "").strip() or None
        )
        await self.session.commit()
        if created:
            tracker.track(Event.MESSAGE_SENT, str(sender_id), match=str(match_id))
        # A line written a moment ago has been seen by nobody except the one who wrote it, and
        # the receipts it already carries are its author's own.
        return self._to_dto(msg, sender_id, is_read=False), created

    async def history(
        self, match_id: uuid.UUID, user_id: uuid.UUID, *, limit: int = 50, before_id: uuid.UUID | None = None
    ) -> dict:
        await self._require_membership_for_write(match_id, user_id)
        lines = await self.repo.list_messages(match_id, limit=limit + 1, before_id=before_id)
        has_more = len(lines) > limit
        lines = lines[:limit]
        marked = await self.repo.mark_read(match_id, user_id)
        await self.session.commit()
        page = [self._to_dto(line.message, user_id, is_read=line.is_read) for line in lines]
        return {
            "messages": page,
            "has_more": has_more,
            # The count is reported so the caller can broadcast the receipt: opening a chat
            # is how a reader consumes a backlog, and if the mark happens here in silence the
            # follow-up POST /read finds nothing left and the sender never sees «прочитано».
            "marked_read": marked,
        }

    async def mark_read(self, match_id: uuid.UUID, user_id: uuid.UUID) -> int:
        await self._require_membership_for_write(match_id, user_id)
        count = await self.repo.mark_read(match_id, user_id)
        await self.session.commit()
        return count

    def _to_dto(self, msg, viewer_id: uuid.UUID, *, is_read: bool) -> dict:
        return {
            "id": str(msg.id),
            "match_id": str(msg.match_id),
            "sender_id": str(msg.sender_id),
            "body": msg.body,
            "created_at": msg.created_at,
            "is_read": is_read,
            "is_own": msg.sender_id == viewer_id,
            "client_msg_id": msg.client_msg_id,
        }
