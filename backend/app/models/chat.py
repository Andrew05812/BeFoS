from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
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
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
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
