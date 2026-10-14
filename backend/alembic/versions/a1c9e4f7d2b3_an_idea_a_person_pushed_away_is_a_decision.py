"""An idea a person pushed away is a decision, not an absence of one.

`activity_preferences` recorded a single fact: this person took this card of this pair's page,
which the read path answers by the row's own existence. A rejection is a second fact, and it
cannot reuse that existence — a row that means both "proposed" and "refused" would leave the page
unable to tell a card whose message is already in the pair's chat from one nobody ever sent, and
the first of those is the card stage 63 exists to keep from going into chat twice.

So the two answers get two columns, both of which can be true of the same card at the same time.
`proposed` is filled with `true` for the rows already in the table: every one of them was written
by a tap that had just put its idea into the chat, and no row ever written by that path means
anything else. `declined` defaults to false, which keeps the read of an untouched page answering
exactly as it did before this revision.

revision: see `down_revision` — the pair a tap was made for is the revision before.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c9e4f7d2b3"
down_revision: Union[str, None] = "b4d8f1c07a52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The server default is the backfill: `NOT NULL` on a table that already has rows needs a
    # value for them, and the two values it needs are the two this revision means. It is dropped
    # straight after, because no other column of this table carries one — the defaults live on
    # the model, and a database that fills them too is a second copy of the rule that `alembic
    # check` would rightly call drift.
    op.add_column(
        "activity_preferences",
        sa.Column("proposed", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "activity_preferences",
        sa.Column("declined", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("activity_preferences", "proposed", server_default=None)
    op.alter_column("activity_preferences", "declined", server_default=None)


def downgrade() -> None:
    op.drop_column("activity_preferences", "declined")
    op.drop_column("activity_preferences", "proposed")
