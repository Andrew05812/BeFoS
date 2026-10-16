from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin

# What the two a line of a conversation can be: something a person typed, or something the pair's
# plan did. A plan is not a message from one of them — it stands only while both halves say the same
# thing about it — so it cannot be smuggled into `body` as if somebody had written it.
#
# The plan kinds are the things a plan does that the pair has to be told about. The two oldest
# (`plan_agreed`, `plan_voided`) say what happened to the hour the pair stands on; the rest name the
# states the hour cannot express — an idea put to the pair, an answer to it, a move being asked for,
# a meeting kept, a plan called off, a card whose place or note moved. A client that groups lines by
# `sender_id` still has to read `kind`: a plan line names the person whose tap produced it, and that
# person is not the author of the sentence.
KIND_TEXT = "text"
KIND_PLAN_AGREED = "plan_agreed"
KIND_PLAN_VOIDED = "plan_voided"
KIND_PLAN_PROPOSED = "plan_proposed"
KIND_PLAN_ACCEPTED = "plan_accepted"
KIND_PLAN_DECLINED = "plan_declined"
KIND_PLAN_RESCHEDULED = "plan_rescheduled"
KIND_PLAN_CANCELLED = "plan_cancelled"
KIND_PLAN_COMPLETED = "plan_completed"
KIND_PLAN_CHANGED = "plan_changed"
PLAN_KINDS = (
    KIND_PLAN_AGREED,
    KIND_PLAN_VOIDED,
    KIND_PLAN_PROPOSED,
    KIND_PLAN_ACCEPTED,
    KIND_PLAN_DECLINED,
    KIND_PLAN_RESCHEDULED,
    KIND_PLAN_CANCELLED,
    KIND_PLAN_COMPLETED,
    KIND_PLAN_CHANGED,
)


class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(
        # ix_message_match_created already covers match_id as its leading column.
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False)
    # The client's own id for the message it is sending. A send whose response never
    # arrived is retried with the same value, and the row has to exist once: without a
    # key the retry is a second identical message to the peer, and the user — who cannot
    # tell "lost" from "refused" — is the one who finds out.
    client_msg_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Which of the two a line is: something a person typed, or something the pair's plan did.
    # A plan is not a message from one of them — it stands only while both rows name the same
    # instant — so it cannot be smuggled into `body` as if somebody had written it, and the idea
    # it belongs to has to stay a number rather than a phrase: `body` is the sentence the line was
    # born with, these fields are the ones a client renders from, and a catalogue that renames
    # the activity is seen in the title the read carries, not in a frozen copy.
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="text", server_default="text"
    )
    plan_activity_id: Mapped[int | None] = mapped_column(
        # SET NULL, not CASCADE: a card leaving the catalogue must not take a pair's conversation
        # with it. The line stays readable on its own sentence, and the tap target is simply gone.
        ForeignKey("activities.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The plan this line is about, once a pair's arrangement has a name of its own. The activity id
    # above says what the idea was; this says which arrangement of it the line records, which is what
    # lets a chat card open the plan's details and a plan's history be read back without guessing
    # from the idea's name. SET NULL for the same reason as the activity: a plan that goes away — the
    # card leaves the catalogue, the pair dissolves — must not un-say what the conversation already
    # said; the line loses its tap target and keeps its sentence.
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("shared_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    plan_when: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    match: Mapped["Match"] = relationship(back_populates="messages")
    reads: Mapped[list["MessageRead"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_message_match_created", "match_id", "created_at"),
        # Partial because the key is optional: messages written before it existed, and
        # any client that sends without one, must not collide on NULL.
        Index(
            "uq_message_sender_client_id",
            "match_id",
            "sender_id",
            "client_msg_id",
            unique=True,
            postgresql_where=text("client_msg_id IS NOT NULL"),
        ),
    )


class MessageRead(Base):
    __tablename__ = "message_reads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        # uq_message_read already covers message_id as its leading column.
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    reader_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    message: Mapped["Message"] = relationship(back_populates="reads")

    __table_args__ = (
        UniqueConstraint("message_id", "reader_id", name="uq_message_read"),
        # The unread count filters reader_id alone, which this table's other keys
        # never led with.
        Index("ix_message_reads_reader_message", "reader_id", "message_id"),
    )
