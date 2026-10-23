"""the walk of one's own taps gets a key that starts where the reader stands

Revision ID: f7c2a9d4e6b1
Revises: b4e7d3a8c619
Create Date: 2026-10-24 02:12:41.207315

Stage 123 gave `GET /discover/liked` a cursor and then priced the walk it made possible — the same
read repeated behind the link the previous page handed out, at the three scales the stand keeps (88,
893 and 4 493 taps of one viewer, `s123_pages.json`). A page cost 27.2 мс at 88 taps, 37.7 мс at 893
and 61.2 мс at 4 493. That is not the shape of a read that costs its page: it is the shape of a read
that first gathers the reader's whole history. The plan says so in as many nodes —
`Limit -> Sort (rows=N) -> Index Scan using uq_like_pair on likes`, the sort growing with the history
while the page stays at fifty rows.

`likes` carries one key that reaches these rows at all: `uq_like_pair (from_user_id, to_user_id)`. Its
leading column answers the walk's equality, and its second column answers a question the walk never
asks — which person, not when. `ix_likes_from_user_id` was dropped by `e6b28c4a13d0` as a left prefix
of that pair, which was right then (no read ordered on anything) and stopped being right the moment the
list learned to turn a page.

So the ordering belongs in the key: whose taps, then newest first, then the id that decides the tie the
timestamp cannot (`ix_likes_tapper_order`). The two directions are written out because the walk orders
DESC on both, and the id is in the key because the cursor is the pair `(created_at, id)` — a key
without it would sort the page's ties in the reader instead of walking past them.

Not partial, and that is a fact about the read rather than an oversight: what this walk excludes lives
in the tables it joins (`users.is_deleted`, `users.is_active`, `profiles.is_hidden`, the pair, the
block), and Postgres refuses a predicate over another table in an index — `cannot use subquery in
index predicate`. The write cost is therefore the honest price of the read, and it is measured and
named in `docs/SCALE_PLAN.md` rather than hidden in a predicate that could not hold the rule anyway.

Both columns are NOT NULL (`created_at` from `TimestampMixin`, `id` is the primary key), so the nulls
order the key stores is the one the ORDER BY would have used regardless; it is recorded here because
the direction bit in `pg_index.indoption` is what the pairing test reads, and a reader checking that
bit wants to know why nothing else is in it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7c2a9d4e6b1"
down_revision: Union[str, None] = "b4e7d3a8c619"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_likes_tapper_order",
        "likes",
        # The directions are `sa.text`, not strings: in a column list a plain string is an identifier,
        # and «"created_at DESC"» as an identifier names a column that does not exist. This is the same
        # shape `f3a07c2d5b18` used for the deck's order key.
        ["from_user_id", sa.text("created_at DESC"), sa.text("id DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_likes_tapper_order", table_name="likes")
