from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func, and_, exists, or_, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Match, Message, MessageRead


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_match(self, match_id: uuid.UUID) -> Match | None:
        return await self.session.get(Match, match_id)

    async def is_member(self, match_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        match = await self.get_match(match_id)
        return bool(match and (match.user_a_id == user_id or match.user_b_id == user_id))

    async def add_message(
        self,
        match_id: uuid.UUID,
        sender_id: uuid.UUID,
        body: str,
        client_msg_id: str | None = None,
    ) -> tuple[Message, bool]:
        """Store a message and report whether this call is the one that stored it.

        With a `client_msg_id` the write is idempotent: the same id from the same sender
        in the same match names one row, and a retry gets that row back instead of a
        second copy. `ON CONFLICT DO NOTHING` waits for the row it collides with to
        resolve, so the follow-up read sees it even when two attempts arrived together.
        """
        if client_msg_id is not None:
            msg = (
                await self.session.execute(
                    pg_insert(Message)
                    .values(
                        match_id=match_id,
                        sender_id=sender_id,
                        body=body,
                        client_msg_id=client_msg_id,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["match_id", "sender_id", "client_msg_id"],
                        index_where=text("client_msg_id IS NOT NULL"),
                    )
                    .returning(Message)
                )
            ).scalar_one_or_none()
            if msg is not None:
                self._note_read_by_sender(msg.id, sender_id)
                await self.session.flush()
                return msg, True

            stored = await self.find_by_client_id(match_id, sender_id, client_msg_id)
            if stored is not None:
                return stored, False
            # Only a row that collided and then went away again (rolled back, deleted
            # between the two statements) reaches here. The key is free again, so the
            # plain write below is the honest answer rather than a refusal.

        msg = Message(
            match_id=match_id, sender_id=sender_id, body=body, client_msg_id=client_msg_id
        )
        self.session.add(msg)
        await self.session.flush()
        self._note_read_by_sender(msg.id, sender_id)
        await self.session.flush()
        return msg, True

    def _note_read_by_sender(self, message_id: uuid.UUID, sender_id: uuid.UUID) -> None:
        """A sender has read their own message; without this row the unread count counts them."""
        self.session.add(
            MessageRead(
                message_id=message_id, reader_id=sender_id, read_at=datetime.now(timezone.utc)
            )
        )

    async def find_by_client_id(
        self, match_id: uuid.UUID, sender_id: uuid.UUID, client_msg_id: str
    ) -> Message | None:
        stmt = select(Message).where(
            Message.match_id == match_id,
            Message.sender_id == sender_id,
            Message.client_msg_id == client_msg_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_messages(
        self, match_id: uuid.UUID, *, limit: int = 50, before_id: uuid.UUID | None = None
    ) -> list[Message]:
        stmt = (
            select(Message)
            .options(selectinload(Message.reads))
            .where(Message.match_id == match_id, Message.is_deleted.is_(False))
        )
        if before_id is not None:
            anchor = await self.session.get(Message, before_id)
            if anchor is not None:
                stmt = stmt.where(Message.created_at < anchor.created_at)
        stmt = stmt.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)
        rows = list((await self.session.execute(stmt)).scalars().all())
        rows.reverse()  # return ascending order
        return rows

    async def mark_read(self, match_id: uuid.UUID, reader_id: uuid.UUID) -> int:
        """Mark all messages in a match not sent by reader as read. Returns count."""
        # The already-read test runs in SQL: this fires on every chat open, and reading
        # the whole history into Python to drop it again made the cost grow with the
        # length of the conversation instead of the number of unread messages.
        unread = select(Message.id).where(
            Message.match_id == match_id,
            Message.sender_id != reader_id,
            ~exists()
            .where(MessageRead.message_id == Message.id, MessageRead.reader_id == reader_id)
            .correlate(Message),
        )
        pending = [row[0] for row in (await self.session.execute(unread)).all()]
        if not pending:
            return 0
        now = datetime.now(timezone.utc)
        # Two devices (or the REST call and the socket) can mark the same message read at
        # once; the constraint decides which one recorded it, and RETURNING counts the rows
        # this call actually inserted so the receipt is broadcast only for those.
        inserted = (
            await self.session.execute(
                pg_insert(MessageRead)
                .values([{"message_id": mid, "reader_id": reader_id, "read_at": now} for mid in pending])
                .on_conflict_do_nothing(constraint="uq_message_read")
                .returning(MessageRead.id)
            )
        ).all()
        return len(inserted)

    async def last_message(self, match_id: uuid.UUID) -> Message | None:
        stmt = (
            select(Message)
            .where(Message.match_id == match_id, Message.is_deleted.is_(False))
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def unread_count(self, match_id: uuid.UUID, user_id: uuid.UUID) -> int:
        sub_read = select(MessageRead.message_id).where(
            MessageRead.reader_id == user_id
        )
        stmt = select(func.count(Message.id)).where(
            Message.match_id == match_id,
            Message.sender_id != user_id,
            Message.is_deleted.is_(False),
            Message.id.not_in(sub_read),
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def last_messages(self, match_ids: list[uuid.UUID]) -> dict[uuid.UUID, Message]:
        if not match_ids:
            return {}
        # PostgreSQL DISTINCT ON picks the newest row per match in one pass.
        stmt = (
            select(Message)
            .distinct(Message.match_id)
            .where(Message.match_id.in_(match_ids), Message.is_deleted.is_(False))
            .order_by(Message.match_id, Message.created_at.desc())
        )
        return {m.match_id: m for m in (await self.session.execute(stmt)).scalars()}

    async def unread_counts(self, match_ids: list[uuid.UUID], user_id: uuid.UUID) -> dict[uuid.UUID, int]:
        if not match_ids:
            return {}
        sub_read = select(MessageRead.message_id).where(MessageRead.reader_id == user_id)
        stmt = (
            select(Message.match_id, func.count(Message.id))
            .where(
                Message.match_id.in_(match_ids),
                Message.sender_id != user_id,
                Message.is_deleted.is_(False),
                Message.id.not_in(sub_read),
            )
            .group_by(Message.match_id)
        )
        counts = {mid: int(n) for mid, n in (await self.session.execute(stmt)).all()}
        return {mid: counts.get(mid, 0) for mid in match_ids}
