"""the two lists that turn pages by a moment get the keys that let them stop

Revision ID: c8f2b5d7a140
Revises: f7c2a9d4e6b1
Create Date: 2026-11-02 11:41:03.221760

Stage 126 put a cursor on `GET /discover/liked-me` and `GET /discover/passed`, then priced the walk
each one made possible on the 50 000-profile stand (`s126_scale_a.json`, база `befos_s126scale_a`,
дерево `e648054`, окно 2026-11-02 08:14:53…08:17:53 UTC). The first page and the page behind its own
link came out like this:

    liked_me        56.8 мс плана / 59.5 мс стены,  worst node Seq Scan profiles 27.3 мс × 2 loops
    liked_me_tail   90.6 мс плана / 67.1 мс стены
    passed          93.8 мс плана / 96.9 мс стены
    passed_tail    195.6 мс плана / 264.8 мс стены,  worst node Index Scan profiles, 15 456 loops

Both doors read one reader's rows newest-first and resume below a `(created_at, id)` pair, and neither
table carried a key that answers that shape on the reader's half. `likes` had `ix_likes_to_user_id`
(one column, no order) and `passes` had `ix_passes_to_user_id` plus `uq_pass_pair (from_user_id,
to_user_id)` — whose leading column answers «whose passes» and then answers a question the walk never
asks, which person rather than when. So the planner gathered the reader's whole history, visited a
profile per row (15 456 of them for a reader with 15 506 passes), sorted, and only then took the page.

The comparison that settles it is already in the schema: the same read on the tapper's side —
`GET /discover/liked`, identical projection, identical ORDER BY, identical boundary — costs 4.8 мс of
plan and 38.3 мс of wall, because `ix_likes_tapper_order` (stage 123) lets it stop inside the index.
So this adds that key twice more: over `likes.to_user_id` for the inbox, and over `passes.from_user_id`
for the pass list.

Neither key is partial, and neither is unique, for the two reasons stage 123 wrote out and stage 125
confirmed on the same tables: everything this pair of reads excludes lives in the tables it joins
(`users.is_deleted`, `users.is_active`, `profiles.is_hidden`, the pair, the block), and Postgres
refuses a predicate over another table in an index; while uniqueness over `(from_user_id, …)` is
already decided by `uq_pass_pair` / `uq_like_pair` and a second unique key would only refuse rows the
first one permits. `created_at` comes from `TimestampMixin` and `id` is the primary key, both NOT NULL,
so the direction bit in `pg_index.indoption` is the only choice these keys make.

The narrow `ix_likes_to_user_id` goes with this change rather than staying beside it, and the reason is
the repository's own rule: a btree over one column is a left prefix of a btree that starts with the
same column, so it is written on every tap and never needed for a read — the rule
`test_schema_index_redundancy.py` holds, with the 100 000-row insert measurement behind it (4 047 мс
against 3 514 мс) recorded in `docs/SCALE_PLAN.md`. The two reads that could have cared were timed on
this stand before the drop and after it (`s126_drop_narrow_index.json`): the inbox page answered
0.76 мс with the narrow key present and 0.75 мс without it, planning on the new key both times; and the
account's own export, which orders the same rows `created_at, id` ASC, answered 4.93 against 4.90 мс.
With sequential scans switched off — the state a real account's handful of taps against a much larger
table produces — the export moved from the narrow index to `ix_likes_target_inbox_order`, 4.773 against
4.894 мс, which is the backward-scan claim made as a number instead of an assertion.

`ix_passes_to_user_id` stays: it is not a prefix of anything. The new pass key starts on the other half
of the pair, and the reader who is *being* passed is still a lookup this product makes (the purge of a
deleted account walks `or_(from_user_id, to_user_id)`).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8f2b5d7a140"
down_revision: Union[str, None] = "f7c2a9d4e6b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_likes_target_inbox_order",
        "likes",
        # `sa.text` for the direction terms: a plain string in a column list is an identifier, and
        # «"created_at DESC"» as an identifier names a column that does not exist.
        ["to_user_id", sa.text("created_at DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_passes_tapper_order",
        "passes",
        ["from_user_id", sa.text("created_at DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.drop_index("ix_likes_to_user_id", table_name="likes")


def downgrade() -> None:
    op.create_index("ix_likes_to_user_id", "likes", ["to_user_id"], unique=False)
    op.drop_index("ix_passes_tapper_order", table_name="passes")
    op.drop_index("ix_likes_target_inbox_order", table_name="likes")
