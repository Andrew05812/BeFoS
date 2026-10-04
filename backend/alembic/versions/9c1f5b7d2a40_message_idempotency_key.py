"""a send the client named is one message, not two

Revision ID: 9c1f5b7d2a40
Revises: 4f2a1c9d7b30
Create Date: 2026-10-04 21:40:03.118702

A POST whose response never arrived is indistinguishable, from the client's side, from
a POST that was refused. Retrying it therefore inserts a second identical message and
the peer reads the same sentence twice. The client's own id for the send becomes the
dedup key; the index is partial because the key is optional -- rows written before this
revision, and any caller that sends without an id, must not collide on NULL.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9c1f5b7d2a40"
down_revision: Union[str, None] = "4f2a1c9d7b30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("client_msg_id", sa.String(length=64), nullable=True))
    op.create_index(
        "uq_message_sender_client_id",
        "messages",
        ["match_id", "sender_id", "client_msg_id"],
        unique=True,
        postgresql_where=sa.text("client_msg_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_message_sender_client_id", table_name="messages")
    op.drop_column("messages", "client_msg_id")
