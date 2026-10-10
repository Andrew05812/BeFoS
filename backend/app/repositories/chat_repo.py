from __future__ import annotations

import uuid
from collections import namedtuple
from datetime import datetime, timezone

from sqlalchemy import select, func, and_, bindparam, exists, or_, text, tuple_, DateTime
from sqlalchemy.dialects.postgresql import UUID as pg_uuid, insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Match, Message, MessageRead

# What the pair list answers with per conversation: the newest body, its time, and how many of the
# partner's lines the reader has not receipted. A row of the narrow `chat_summaries` read.
PairLine = namedtuple("PairLine", "body created_at unread")

# A line of the chat page with the one thing about it that does not live in the `messages` row:
# whether anybody other than its author has read it. A row of the `list_messages` read.
HistoryLine = namedtuple("HistoryLine", "message is_read")


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_match(self, match_id: uuid.UUID) -> Match | None:
        return await self.session.get(Match, match_id)

    async def match_still_present(self, match_id: uuid.UUID) -> bool:
        """Ask the database, not the identity map, whether the match row is still there.

        ``get_match`` goes through ``session.get``, which hands back an object this session
        already loaded without re-querying — correct in a normal request, but after a block
        on another connection has committed its DELETE the cached ``Match`` is a row that no
        longer exists. Reading the id column asks the current snapshot instead, which is what
        a post-lock re-check needs to see the dissolve.
        """
        stmt = select(Match.id).where(Match.id == match_id)
        return (await self.session.execute(stmt)).first() is not None

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
    ) -> list[HistoryLine]:
        """One page of the conversation, each line carrying its own receipt flag.

        `is_read` answers «has anyone but the author seen this line», and the page is the only
        consumer of that answer. It used to arrive as a second round trip — `selectinload` of
        `Message.reads` — which on the stage-50 stand (a 500-line thread, a 50-line page, 40 500
        receipts in the table) brought 76 rows and as many ORM objects back to be reduced to fifty
        booleans in Python. The correlated EXISTS asks the same question inside the read that
        already picks the page, so one trip carries both. The base does not work less: the two old
        plans sum to 1.22 ms, the new one to 1.19 ms — what goes away is the conversation and the
        objects.

        The condition stays `reader_id <> sender_id`, and that is the whole answer: every sent line
        carries its author's own receipt (`_note_read_by_sender`), so a flag built on
        `message_id = messages.id` alone would tell the author their line was read before the
        partner had opened the chat.
        """
        read_by_someone_else = exists(
            select(MessageRead.id)
            .where(
                MessageRead.message_id == Message.id,
                MessageRead.reader_id != Message.sender_id,
            )
            .correlate(Message)
        ).label("is_read")
        stmt = (
            select(Message, read_by_someone_else)
            .where(Message.match_id == match_id, Message.is_deleted.is_(False))
        )
        if before_id is not None:
            anchor = await self.session.get(Message, before_id)
            if anchor is not None:  # the page ranks by (created_at, id), so the cut ranks by both
                stmt = stmt.where(tuple_(Message.created_at, Message.id) < (anchor.created_at, anchor.id))
        stmt = stmt.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)
        rows = list((await self.session.execute(stmt)).all())
        rows.reverse()  # return ascending order
        return [HistoryLine(message=message, is_read=bool(flag)) for message, flag in rows]

    async def mark_read(self, match_id: uuid.UUID, reader_id: uuid.UUID) -> int:
        """Mark every message of the match the reader did not send as read. Returns the count.

        The already-read test stays in SQL, and so do the ids it finds. This used to be two
        round trips that asked one question: a SELECT carried the unread ids into Python and an
        INSERT carried the same ids back as one parameter group per message. Written as
        ``INSERT … SELECT`` the ids never leave the table, so opening a chat with a backlog
        costs one statement instead of two and the text of the write no longer grows with the
        length of the conversation.

        Two devices (or the REST call and the socket) can mark the same message read at once;
        the constraint decides which one recorded it, and RETURNING counts the rows this call
        actually inserted so the receipt is broadcast only for those.
        """
        pending = (
            select(
                func.gen_random_uuid(),
                Message.id,
                bindparam("receipt_reader", reader_id, type_=pg_uuid(as_uuid=True)),
                bindparam(
                    "receipt_at", datetime.now(timezone.utc), type_=DateTime(timezone=True)
                ),
            ).where(
                Message.match_id == match_id,
                Message.sender_id != reader_id,
                ~exists()
                .where(MessageRead.message_id == Message.id, MessageRead.reader_id == reader_id)
                .correlate(Message),
            )
        )
        inserted = (
            await self.session.execute(
                pg_insert(MessageRead)
                .from_select(["id", "message_id", "reader_id", "read_at"], pending)
                .on_conflict_do_nothing(constraint="uq_message_read")
                .returning(MessageRead.id)
            )
        ).all()
        return len(inserted)

    async def chat_summaries(
        self, match_ids: list[uuid.UUID], reader_id: uuid.UUID
    ) -> dict[uuid.UUID, PairLine]:
        """The newest line and the unread counter of every pair, in one pass over ``messages``.

        Two statements used to walk the same rows of the same table for the same list of match ids:
        ``DISTINCT ON`` picked the newest message of each pair, a second ``count(…) GROUP BY``
        counted the waiting ones. A window aggregate over the pair's partition puts that counter on
        the row ``DISTINCT ON`` keeps, so one read carries both columns of the card.

        The projection stops there. A ``Message`` entity carries eight columns of the row while this
        read answers with three — the pair, the line, its time — and the card asks for no author, no
        client id, no deletion flag and no updated stamp of the newest message (stage 49,
        `docs/SCALE_PLAN.md`).

        The receipt is joined on the reader, so a row written by the partner — and every sent
        message carries its author's own receipt — leaves this counter alone. The join cannot fan a
        message into two rows: ``uq_message_read`` allows one receipt per (message, reader).

        A pair without messages simply does not appear, which is what the caller expects: no line,
        zero waiting.
        """
        if not match_ids:
            return {}
        waiting = and_(Message.sender_id != reader_id, MessageRead.id.is_(None))
        stmt = (
            select(
                Message.match_id,
                Message.body,
                Message.created_at,
                func.count()
                .filter(waiting)
                .over(partition_by=Message.match_id)
                .label("unread"),
            )
            .outerjoin(
                MessageRead,
                and_(
                    MessageRead.message_id == Message.id,
                    MessageRead.reader_id == reader_id,
                ),
            )
            .where(Message.match_id.in_(match_ids), Message.is_deleted.is_(False))
            # PostgreSQL DISTINCT ON picks the newest row per match in one pass. The id breaks a
            # same-microsecond tie the same way the chat page does, so the card and the screen
            # name the same line; `created_at` alone leaves that choice to the scan order.
            .distinct(Message.match_id)
            .order_by(Message.match_id, Message.created_at.desc(), Message.id.desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return {row.match_id: PairLine(row.body, row.created_at, int(row.unread)) for row in rows}
