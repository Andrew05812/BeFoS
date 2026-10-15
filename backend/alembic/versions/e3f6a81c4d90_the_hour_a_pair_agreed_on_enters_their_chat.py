"""The hour a pair agreed on is something their chat says.

A plan is a fact about the pair, and until now it lived only in `activity_preferences`: two rows
whose instants happen to line up. The conversation that produced the agreement never learned about
it — a person who agreed to 19:00 saw the card change and the chat stay silent, so the chat, which
is where the pair actually talks, was the one place the plan was missing. Three columns on
`messages` let the agreement stand in it as itself rather than as a sentence somebody typed.

`kind` says which of the two a line is. `sender_id` is NOT NULL and points at a real person, so a
plan cannot be passed off as one of their messages, and a client that renders bubbles by author
would put a system event in somebody's gutter. A typed value separates them without inventing a
sender, and `text` — the answer every existing row already is — is the `server_default`, which is
what lets the column be NOT NULL over a database full of conversations without rewriting one word
of them.

The other two are the plan, kept as fields rather than folded into `body`. A card the pair agreed
on has a title, a moment and a status, and the moment has to be an instant the client can format on
the viewer's clock; a frozen sentence would say «завтра в 19:00» to somebody who opened the chat a
week later. `body` still carries the sentence the line was born with, so a build that predates this
revision reads something true instead of nothing. `plan_activity_id` is a number and not a phrase
because the catalogue may rename the idea — the title then comes from the read, and the row keeps
pointing at what it was about. Its `SET NULL` is deliberate: a card leaving the catalogue must not
take a pair's conversation with it, and the tap target simply disappearing from a still-readable
line is the whole of that trade.

revision: see `down_revision` — the `kind` column that asks six questions on a scale is the
revision before.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e3f6a81c4d90"
down_revision: Union[str, None] = "d7a3f2b81c64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("kind", sa.String(length=32), server_default="text", nullable=False),
    )
    op.add_column(
        "messages",
        sa.Column(
            "plan_activity_id",
            sa.Integer(),
            sa.ForeignKey("activities.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("messages", sa.Column("plan_when", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "plan_when")
    op.drop_column("messages", "plan_activity_id")
    op.drop_column("messages", "kind")
