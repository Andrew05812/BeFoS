"""A pair that has chosen an idea still has no moment to meet at.

The page answers «what to do» and the chat answers «do we want it», and between them sits the
question this table was already carrying the answer to: whose decision is this. A proposal of a
time is one person's answer about one card of one pair's page, exactly like `proposed` and
`declined`, so it lives on the same row rather than in a second table that would have to re-derive
which pair, which card and which person it belongs to.

Two columns, not one state machine. `meeting_time` is the moment this person names; `accepted_time`
is the moment this person agreed to, and the only instant a person can agree to is the other half's.
Both are nullable, because a card can hold one, both or neither — and the pair has a plan when one
row's `accepted_time` equals the other row's `meeting_time`, which is a read over rows that already
exist rather than a fourth flag to keep in step with them. Moving a proposal therefore needs no
cleanup: the agreement stops being one on its own.

revision: see `down_revision` — the two answers of a pushed-away idea are the revision before.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9b4e7a2d5f1"
down_revision: Union[str, None] = "a1c9e4f7d2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "activity_preferences",
        sa.Column("meeting_time", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "activity_preferences",
        sa.Column("accepted_time", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("activity_preferences", "accepted_time")
    op.drop_column("activity_preferences", "meeting_time")
