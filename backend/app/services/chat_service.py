from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.tracker import Event, tracker
from app.core.exceptions import NotFoundError, ValidationError
from app.models.chat import KIND_TEXT
from app.repositories.activity_repo import ActivityRepository
from app.repositories.chat_repo import ChatRepository
from app.repositories.social_repo import SocialRepository


def message_frame(dto: dict) -> dict:
    """The frame a chat line travels in, so every door that writes one opens it the same way.

    Three routes put a line in front of a pair — a REST send, a socket send and an accepted hour —
    and a client that has to read three spellings of the same event reads one of them wrong. The
    instants go out as text here because the frame crosses a wire, while the DTO keeps them objects
    for the schema that validates the REST body.
    """
    plan = dto["plan"]
    return {
        "type": "message",
        "id": dto["id"],
        "client_msg_id": dto["client_msg_id"],
        "match_id": dto["match_id"],
        "sender_id": dto["sender_id"],
        "body": dto["body"],
        "created_at": dto["created_at"].isoformat(),
        "is_read": dto["is_read"],
        "kind": dto["kind"],
        "plan": (
            None
            if plan is None
            else {**plan, "when": None if plan["when"] is None else plan["when"].isoformat()}
        ),
    }


def message_dto(
    msg, viewer_id: uuid.UUID, *, is_read: bool, activity=None, is_latest: bool = False
) -> dict:
    """One chat line as the API answers it, for whoever has the row and the viewer.

    The hour that arranges a plan holds a `Message` it just wrote and needs the same shape the
    conversation read returns, so the shape lives beside the reader rather than inside it.
    """
    return {
        "id": str(msg.id),
        "match_id": str(msg.match_id),
        "sender_id": str(msg.sender_id),
        "body": msg.body,
        "created_at": msg.created_at,
        "is_read": is_read,
        "is_own": msg.sender_id == viewer_id,
        "client_msg_id": msg.client_msg_id,
        "kind": msg.kind,
        # The plan is the card a client draws; `body` is the sentence the line was born with.
        # They are both sent because they answer differently: the fields say what the plan is
        # now — the title comes from the catalogue, so a rename shows — while the body says
        # what was decided at the moment it was decided, which is all an old build can read.
        "plan": (
            None
            if msg.kind == KIND_TEXT
            else {
                "activity_id": msg.plan_activity_id,
                "activity_title": None if activity is None else activity.title,
                "when": msg.plan_when,
                # The arrangement this line records, so a card in the chat can open the plan it
                # speaks about instead of guessing which of the pair's plans the idea became. Absent
                # for a line written before the plan entity existed: the sentence stays true, only
                # the tap target is missing.
                "plan_id": None if msg.plan_id is None else str(msg.plan_id),
                # The newest word the pair wrote about this idea. Not «still true of the moment»:
                # a cancellation is a newest word too, and the two kinds together are what lets a
                # card say «договорённость в силе» about one line and «отменена» about the next.
                "is_latest": is_latest,
            }
        ),
    }


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ChatRepository(session)
        self.social = SocialRepository(session)
        self.activities = ActivityRepository(session)

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
        return message_dto(msg, sender_id, is_read=False), created

    async def history(
        self, match_id: uuid.UUID, user_id: uuid.UUID, *, limit: int = 50, before_id: uuid.UUID | None = None
    ) -> dict:
        await self._require_membership_for_write(match_id, user_id)
        lines = await self.repo.list_messages(match_id, limit=limit + 1, before_id=before_id)
        has_more = len(lines) > limit
        lines = lines[-limit:]  # ascending window: the extra probe row sits at the front
        journal = [line for line in lines if line.message.kind != KIND_TEXT]
        if journal:
            newest = await self.repo.latest_plan_events(match_id)
            titles = await self.activities.get_by_ids(
                sorted({line.message.plan_activity_id for line in journal if line.message.plan_activity_id})
            )
        else:
            # A page of sentences somebody typed pays nothing for a plan it does not carry.
            newest, titles = {}, {}
        marked = await self.repo.mark_read(match_id, user_id)
        await self.session.commit()
        page = [
            message_dto(
                line.message,
                user_id,
                is_read=line.is_read,
                activity=titles.get(line.message.plan_activity_id),
                is_latest=line.message.id == newest.get(line.message.plan_activity_id),
            )
            for line in lines
        ]
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
