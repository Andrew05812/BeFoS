"""A pair arranges one thing, and that thing has a name of its own.

A plan used to be a composite: `(match_id, activity_id)` read out of two `activity_preferences`
rows, with the conversation holding a second copy of the outcome as journal lines. That shape answers
"did these two land on this hour" and nothing else — a screen listing the pair's plans had no row to
point at, a reschedule had no field to hold the hour being asked about, completion had nowhere to be
recorded, and "cancelled" did not exist at all. `shared_plans` is the row those features need, and
`shared_plan_members` is the pair's two answers about it.

Nothing is rewritten here, and nothing is copied in: the table starts empty and fills itself from the
rows the pair's taps already wrote, on that pair's first read (`PlanService.sync_pair`), by the same
rule the card page has always used. A migration that backfilled the plans here would be a second
implementation of that rule — one able to disagree with the live one — and it would have to decide
`was_planned` from the outside, which is the one fact the old rows cannot tell. Deriving it in the
service means the plans a pair sees after this revision are produced by the same code that keeps
deriving them from then on.

`messages.plan_id` points a journal line at the plan it records. `SET NULL`, the trade
`plan_activity_id` already made: a plan going away must not un-say what the conversation already
said, it only costs that line its tap target.

revision: see `down_revision` — the hour a pair agreed on entering their chat is the revision
before.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b7c90ad341"
down_revision: Union[str, None] = "e3f6a81c4d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shared_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("place", sa.String(length=200), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pending_hour", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pending_by", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="proposed", nullable=False),
        sa.Column("was_planned", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('proposed', 'accepted', 'planned', 'rescheduled', 'completed', "
            "'declined', 'cancelled')",
            name="ck_shared_plan_status",
        ),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cancelled_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pending_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "activity_id", name="uq_shared_plan_pair_activity"),
    )
    op.create_index("ix_shared_plan_match_status", "shared_plans", ["match_id", "status"])
    op.create_index("ix_shared_plan_start", "shared_plans", ["status", "starts_at"])

    op.create_table(
        "shared_plan_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("personal_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision in ('pending', 'joined', 'declined')",
            name="ck_shared_plan_member_decision",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["shared_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "user_id", name="uq_shared_plan_member"),
    )
    op.create_index("ix_shared_plan_members_user_id", "shared_plan_members", ["user_id"])

    op.add_column("messages", sa.Column("plan_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_messages_plan_id",
        "messages",
        "shared_plans",
        ["plan_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_messages_plan_id", "messages", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_plan_id", table_name="messages")
    op.drop_constraint("fk_messages_plan_id", "messages", type_="foreignkey")
    op.drop_column("messages", "plan_id")
    op.drop_index("ix_shared_plan_members_user_id", table_name="shared_plan_members")
    op.drop_table("shared_plan_members")
    op.drop_index("ix_shared_plan_start", table_name="shared_plans")
    op.drop_index("ix_shared_plan_match_status", table_name="shared_plans")
    op.drop_table("shared_plans")
