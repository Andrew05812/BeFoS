"""An invitation is a one-person door, and a waiting mark remembers the city.

Stage 132. Two tables, no columns on anything that already exists:

* `invitations` carries the personal link a registered account can hand to somebody who is not
  in BeFoS yet. The row is keyed by a random `code` and not by the inviter, because the code is the
  bearer secret the invitee presents; `accepted_by_user_id` is UNIQUE and nullable, which is the
  anti-inflation rule at the schema level — one account can trip one invitation, and a spent code
  cannot be spent again by a second insert even if two registrations race past the service's read.
  `expires_at` and `revoked_at` are separate for the reason `auth_challenges` keeps `expires_at` and
  `consumed_at` separate: «the link aged out» and «the inviter took it back» are different answers
  to the same person asking why it stopped working. The accepted column is SET NULL rather than
  CASCADE, which is the one place this table disagrees with the rest: erasing an invited account
  must not erase the evidence that the inviter's link was spent, or an erasure would quietly turn a
  used link back into a live one.
* `waitlist_entries` is one voluntary mark per account — `user_id` is UNIQUE — with the city the
  person chose, the moment they withdrew (`cancelled_at`) and the moment a future delivery channel
  told them something (`notified_at`). It stores no coordinates and no device data; `notified_at`
  is present and unused until such a channel exists, and no screen promises it will be written.

Indexes follow what will be read: the code lookup is the public preview, `(inviter_id, created_at
DESC, id)` is the inviter's own newest-first list closing with the id tiebreaker stage 54 taught
the paged reads, and `user_id` needs no second index because its UNIQUE constraint is one key.

revision: see `down_revision` — the chain runs `... -> a7d4f0b2c318 -> b1f4a9c2e7d3 -> this`.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2f8a4c9b1e7"
down_revision: Union[str, None] = "b1f4a9c2e7d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("inviter_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["inviter_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("accepted_by_user_id", name="uq_invitation_invited_account"),
    )
    op.create_index(
        op.f("ix_invitations_code"), "invitations", ["code"], unique=True
    )
    op.create_index(
        "ix_invitations_inviter_created",
        "invitations",
        ["inviter_id", sa.text("created_at DESC"), "id"],
        unique=False,
    )

    op.create_table(
        "waitlist_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_waitlist_entry_account"),
    )


def downgrade() -> None:
    op.drop_table("waitlist_entries")
    op.drop_index("ix_invitations_inviter_created", table_name="invitations")
    op.drop_index(op.f("ix_invitations_code"), table_name="invitations")
    op.drop_table("invitations")
