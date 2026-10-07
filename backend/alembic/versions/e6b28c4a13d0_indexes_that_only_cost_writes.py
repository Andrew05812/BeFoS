"""indexes that only cost writes: every one of these is a left prefix of another key

Revision ID: e6b28c4a13d0
Revises: d8f4b2c6a157
Create Date: 2026-10-07 12:40:11.482035

`ops/scale_probe.py` measured the hot read paths at 1 000, 10 000 and 50 000 profiles, and none of
them bent: the slowest call (the deck rebuild) stayed at 322–336 ms across all three, and its
candidate fetch reads `profiles` sequentially — a plan a prefix index here would not have changed
either way. What the same run made visible is the part the reads do *not* explain: every single
write to `passes`, `likes` and `messages` maintains an index whose columns are already the leading
columns of another key on the same table. A btree over (from_user_id, to_user_id) answers
`WHERE from_user_id = ?` exactly as a btree over (from_user_id) does, so the second one is never
needed for a read and is updated on every insert anyway.

Measured on the throwaway scale database with the SQL recorded in `docs/SCALE_PLAN.md`: inserting
100 000 rows into a copy of `passes` with the extra index took 4 047 ms, the same rows into the
same table without it took 3 514 ms; for `messages` it was 4 234 ms against 3 518 ms, and the
relation itself shrank from 28 MB to 24 MB. A swipe is one insert into `passes`, so this is paid
on the most frequent write in the product.

The single-column declarations are gone from the models too, otherwise `alembic check` reports the
schema as drifted and the next autogenerate re-creates what this migration drops.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e6b28c4a13d0"
down_revision: Union[str, None] = "d8f4b2c6a157"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# index name -> (table, columns). Every entry is a leading prefix of another key on the same
# table, listed next to it so the reason is readable at the call site.
REDUNDANT: dict[str, tuple[str, list[str]]] = {
    "ix_activity_preferences_user_id": ("activity_preferences", ["user_id"]),
    "ix_blocks_blocker_id": ("blocks", ["blocker_id"]),
    "ix_likes_from_user_id": ("likes", ["from_user_id"]),
    "ix_match_users": ("matches", ["user_a_id", "user_b_id"]),
    "ix_matches_user_a_id": ("matches", ["user_a_id"]),
    "ix_message_reads_message_id": ("message_reads", ["message_id"]),
    "ix_messages_match_id": ("messages", ["match_id"]),
    "ix_passes_from_user_id": ("passes", ["from_user_id"]),
    "ix_recommendations_match_id": ("recommendations", ["match_id"]),
    "ix_refresh_tokens_user_id": ("refresh_tokens", ["user_id"]),
    "ix_reports_reporter_id": ("reports", ["reporter_id"]),
    "ix_answer_user_question": ("test_answers", ["user_id", "question_id"]),
    "ix_test_answers_user_id": ("test_answers", ["user_id"]),
    "ix_test_questions_category": ("test_questions", ["category"]),
    "ix_test_results_user_id": ("test_results", ["user_id"]),
}


def upgrade() -> None:
    for name, (table, _columns) in REDUNDANT.items():
        op.drop_index(name, table_name=table)


def downgrade() -> None:
    for name, (table, columns) in REDUNDANT.items():
        op.create_index(name, table, columns)
