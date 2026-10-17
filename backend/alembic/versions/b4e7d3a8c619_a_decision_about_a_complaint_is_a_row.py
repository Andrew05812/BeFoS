"""A decision about a complaint is a row of its own.

`reports` has carried a `status` since the first revision, and nothing could write to it. The
column could be moved by hand through `psql` — the recipe `docs/OPERATIONS.md` §14 gave — and when
it was, the database held the answer to «what is the state of this complaint» and nothing at all to
«who put it there, when, and on what grounds». A moderation surface that only overwrites one column
would keep that hole open while adding a route to fall into it, so this revision gives the change
its own table instead of a new column on the complaint.

`report_reviews` holds one row per status change: which complaint, whose hand, which status it left
and which it entered, the note the moderator recorded with it, and the instant the row was written.
The pair of statuses is stored rather than only the new one because a queue read afterwards has to
tell a complaint dismissed on sight from one that was opened twice, and one column cannot answer
both. `from_status <> to_status` is the same claim at the door: a row that records no change is not
a decision, and letting it in would make the history unreadable at the exact place it exists to be
read. The moderator key is `RESTRICT`, not `CASCADE` — accounts are never hard-deleted in this
product, and a record of what was decided about a person should not be reachable by the question of
whether the decider still works here.

`users.is_moderator` is the second half, and it is a column rather than a table because there is
one privilege in the product and no expiry, reason or author that a second row would have to hold.
It is added with `server_default="false"` so every account that already exists gets an answer, and
the default is dropped right after: the write path is an operator typing one statement on purpose,
and an INSERT that forgot the column should fail rather than be told by the database that whoever
it was is nobody's moderator.

The queue is what makes the third change necessary. `ix_reports_status` answered `WHERE status =
'open'` and then sorted the whole bucket in the reader, which was fine while nobody read that
predicate from a route; a moderator paging the open complaints oldest-first does, so the ordering
columns move into the key and the single-column index — its own left prefix, and therefore never
asked for by a read again — is dropped the way stage 67 dropped the others.

revision: see `down_revision` — the pair that arranges one thing that has an hour and a place is
the revision before.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4e7d3a8c619"
down_revision: Union[str, None] = "f2b7c90ad341"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_moderator", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.alter_column("users", "is_moderator", server_default=None)

    op.create_table(
        "report_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("moderator_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=False),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("from_status <> to_status", name="ck_report_review_moves_status"),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["moderator_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_report_reviews_report_order",
        "report_reviews",
        ["report_id", "created_at", "id"],
        unique=False,
    )

    op.drop_index("ix_reports_status", table_name="reports")
    op.create_index(
        "ix_reports_status_created_at", "reports", ["status", "created_at", "id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_reports_status_created_at", table_name="reports")
    op.create_index("ix_reports_status", "reports", ["status"], unique=False)
    op.drop_index("ix_report_reviews_report_order", table_name="report_reviews")
    op.drop_table("report_reviews")
    op.drop_column("users", "is_moderator")
