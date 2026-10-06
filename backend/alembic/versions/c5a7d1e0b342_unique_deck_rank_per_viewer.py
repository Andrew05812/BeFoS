"""a rank is a cursor position, so it may not be occupied twice

Revision ID: c5a7d1e0b342
Revises: b7e3d0a9c421
Create Date: 2026-10-06 03:52:11.402871

Two refills of one viewer's deck can run at the same moment — a second launch, a retry
after a dropped connection, a client paging with the cursor it already holds. Each of
them reads `max(rank) + 1` as its ceiling before either has written, and when the two
candidate sets differ by one row (somebody hid, somebody new signed up, a like landed and
removed a candidate from the other's selection) the later batch puts a fresh candidate on
a rank the earlier batch already used. `deck_claim` then pages with `rank > :after`, so
one of the two rows shares a cursor step with its neighbour and is never served: a person
disappears from the deck without a trace, and the pair constraint cannot see it because
the two rows are different pairs.

The index makes the illegal state unrepresentable. `deck_append` inserts with
`ON CONFLICT DO NOTHING`, so the loser of the collision is simply not queued — it stays
outside the deck and the next refill picks it up, which is a delay, not a loss.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c5a7d1e0b342"
down_revision: Union[str, None] = "b7e3d0a9c421"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Decks that already reached the duplicated state have to be made legal before the
    # unique index can be built. Which of two rows on one rank survives is decided by
    # `candidate_id`, so the choice is the same on every run and on every replica. The
    # deleted rows hold no user data: a deck row is a promise about who has been queued,
    # and dropping it re-queues the person on the next refill rather than losing them.
    op.execute(
        """
        DELETE FROM discovery_queue dup
        USING discovery_queue keep
        WHERE dup.viewer_id = keep.viewer_id
          AND dup.rank = keep.rank
          AND dup.candidate_id > keep.candidate_id
        """
    )
    op.create_index(
        "uq_discovery_queue_viewer_rank",
        "discovery_queue",
        ["viewer_id", "rank"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_discovery_queue_viewer_rank", table_name="discovery_queue")
