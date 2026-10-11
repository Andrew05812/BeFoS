"""a tap on a recommendation card kept the pair it was made for

Revision ID: b4d8f1c07a52
Revises: 7c4f2a91be36
Create Date: 2026-10-11 07:12:40.000000

``POST /api/v1/matches/{match_id}/recommendations/{activity_id}/select`` answers 204 and writes one
row per tap. The url names the pair, the service reads the pair to authorise the tap
(``RecommendationService._require_match``), and then the row drops the pair: the table keyed a
choice on ``(user_id, activity_id)`` alone. Nothing could therefore read it back on the page the
tap came from. That is not a hypothetical — the table had no reader at all: not the recommendation
engine (which sees interests, answer vectors, city and goal), not the stored page, not the route
that wrote it. The consequence the user can walk into is the client's own dedupe: the app keeps the
set of tapped cards in a ViewModel scoped to one visit to the tab, so the next time the person opens
that tab the card reads as untouched and a second tap sends «Идея для нас: X. Что скажете?» into
the pair's chat again.

Making the record readable answers a question that only makes sense per pair — *did this person
already propose this idea to this pair* — so the key has to carry the pair. A user-level flag would
be wrong on the first screen that shows two pairs: the same activity chosen for one partner would
come back marked on the other's page, and the person would be told the idea was already sent to a
chat it was never sent to. So this revision adds ``match_id`` and widens ``uq_activity_pref`` from
two columns to three.

The column is nullable, because a revision cannot invent a pair for a tap that was made before it.
Read off the working database first: ``select count(*) from activity_preferences`` gave 2 rows, on
activities 4 and 12, both with ``score = 1.0``, and both owners still had exactly one match apiece
(``select count(*) ... where not exists (select 1 from matches m where m.user_a_id = ... or
m.user_b_id = ...)`` gave 0). Attributing those two rows to the one match each user happens to have
would be a guess about an event this table never recorded, so they are left unattributed and the
page reads only attributed rows. Nothing is lost by that: an unattributed row is a tap nobody could
read before this revision either.

``ix_activity_preferences_match_id`` is new because the row became a child of the match: ``block``
and ``delete_account`` delete ``matches`` rows, and the cascade now has to find this table's rows by
``match_id``. Without that key the only index the table has starts with ``user_id``, so every
dissolution of a pair would read the whole table. ``uq_activity_pref`` keeps ``user_id`` as its
leading column, which is what the account-deletion purge deletes on and what the page reads with
(``user_id = ? and match_id = ? and activity_id = any(...)``).

Downgrade restores the two-column key, and that narrowing is where it stops: the pair of rows the
upgrade leaves behind can collide once the pair column is gone. Measured on a scratch base with the
shape the working database will have after this revision — one tap recorded before it (``match_id``
NULL) and one recorded after it on the same activity by the same person — the last statement of
``downgrade`` aborts: ``could not create unique index "uq_activity_pref"``, ``Key (user_id,
activity_id)=(7779087b-…, 3) is duplicated``. The case is not rare; on the working database both
legacy rows sit on activities their owners' pairs are still being shown cards for, so a single tap on
a legacy-tapped card is enough. Two attributed rows for one activity across two pairs collide the
same way.

The abort is the chosen behaviour, not a gap in it. ``alembic`` runs a migration in one transaction
and ``env.py`` declares transactional DDL, so the database keeps everything it had: read back after
that failure, ``alembic_version`` was still ``b4d8f1c07a52``, both preference rows were still there
with one of them still attributed, and both ``uq_activity_pref`` and
``activity_preferences_match_id_fkey`` were still the three-column / cascade definitions this
revision wrote. The alternative — have the downgrade DELETE the rows that will not fit the old key —
would take the operator past the point of no return silently, discarding taps the user actually made
to return the schema to a shape from before them. An operator who really needs the old key on such a
database decides which rows to keep first; the revision refuses to make that decision by itself.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4d8f1c07a52"
down_revision: Union[str, None] = "7c4f2a91be36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_activity_pref", "activity_preferences", type_="unique")
    op.add_column(
        "activity_preferences",
        sa.Column("match_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "activity_preferences_match_id_fkey",
        "activity_preferences",
        "matches",
        ["match_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_activity_preferences_match_id"),
        "activity_preferences",
        ["match_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_activity_pref", "activity_preferences", ["user_id", "activity_id", "match_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_activity_pref", "activity_preferences", type_="unique")
    op.drop_index(op.f("ix_activity_preferences_match_id"), table_name="activity_preferences")
    op.drop_constraint("activity_preferences_match_id_fkey", "activity_preferences", type_="foreignkey")
    op.drop_column("activity_preferences", "match_id")
    op.create_unique_constraint("uq_activity_pref", "activity_preferences", ["user_id", "activity_id"])
