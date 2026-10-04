"""discovery deck, and the indexes the hot reads actually ask for

Revision ID: 4f2a1c9d7b30
Revises: 03f0ea587029
Create Date: 2026-10-04 15:40:12.103421

The candidate query filters ``lower(profiles.city)`` and a ``birth_date`` range,
so the three plain indexes on ``city``/``dating_goal`` could never serve it --
measured on a 120k-row copy: a ``lower(email)``-style expression predicate is a
sequential scan removing every row (76 ms) where the matching functional index
is 0.11 ms. The unread count filters ``message_reads.reader_id`` alone, which no
index led with. Both are fixed here, and the deck table lands with them because
discovery paging now reads it instead of re-ranking a pool per request.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4f2a1c9d7b30"
down_revision: Union[str, None] = "03f0ea587029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "discovery_queue",
        sa.Column("viewer_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status in ('ready', 'seen')", name="ck_discovery_queue_status"),
        sa.ForeignKeyConstraint(["candidate_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["viewer_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("viewer_id", "candidate_id"),
        sa.UniqueConstraint("viewer_id", "candidate_id", name="uq_discovery_queue_pair"),
    )
    op.create_index(
        "ix_discovery_queue_viewer_status_rank",
        "discovery_queue",
        ["viewer_id", "status", "rank"],
    )

    op.create_index(
        "ix_profiles_city_lower_birth",
        "profiles",
        [sa.text("lower(city)"), "birth_date"],
    )
    op.drop_index("ix_profiles_city_goal", table_name="profiles")
    op.drop_index("ix_profiles_city", table_name="profiles")
    op.drop_index("ix_profiles_dating_goal", table_name="profiles")

    op.create_index(
        "ix_message_reads_reader_message",
        "message_reads",
        ["reader_id", "message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_message_reads_reader_message", table_name="message_reads")
    op.create_index("ix_profiles_dating_goal", "profiles", ["dating_goal"])
    op.create_index("ix_profiles_city", "profiles", ["city"])
    op.create_index("ix_profiles_city_goal", "profiles", ["city", "dating_goal"])
    op.drop_index("ix_profiles_city_lower_birth", table_name="profiles", postgresql_using="drop")
    op.drop_index("ix_discovery_queue_viewer_status_rank", table_name="discovery_queue")
    op.drop_table("discovery_queue")
