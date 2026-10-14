"""A question that measures one thing can be asked on a scale instead of a stack of cards.

The questionnaire has asked every axis the same way since the first catalogue: four cards, one tap
each. Six of its axes — how important family is, how much a person develops, how open they are to
new experience, how much contact they need, how active their days are, how much of their leisure is
intellectual — are gradations of a single thing, and a person standing on one of them reads «set the
thumb where you stand» faster than they read four phrases and decide which one is closest. So those
six are asked on a scale.

One column, and it says how the question is *put*, not what the answer is. The stops of the scale
are the `test_options` rows the question already has, in the order it already has them, so the
person's answer is still written to `test_answers.option_id` and the engine still reads its value
off `test_options.value`. Nothing stored is re-interpreted: an answer given to «Насколько для вас
важна семья?» in a deployment that ran this revision means exactly what it meant in one that has
not, which is the property that made stage 71 refuse to rewrite a question the database already
held.

`server_default` is not decoration. The column is NOT NULL on a table that every deployment already
has rows in, and without a default Postgres refuses the ALTER over those twenty-one rows — which
would make the schema change the very thing the stage is not allowed to do to existing data. With
it, the existing rows come back as `choice`, the shape they were already being asked in, and the
UPDATE below is what carries the catalogue's editorial choice into a database whose rows exist: the
seed names a questionnaire it disagrees with and never rewrites one (`app/seed.py::_report_drift`),
so a catalogue edit reaching an already-seeded base is a data migration's job and this is it.

The UPDATE is keyed on `(category, trait)` — the pair the compatibility engine reads the answer
through, and the pair `_require_declared_axes` refuses anything outside of — rather than on
`position` or `id`, so a deployment that reordered its questionnaire or reseeds on new keys still
has the right six questions asked as scales. It runs once, at upgrade.

revision: see `down_revision` — the two columns of an agreed meeting time are the revision before.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7a3f2b81c64"
down_revision: Union[str, None] = "c9b4e7a2d5f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The six axes `questions_catalog.SCALE_AXES` declares. Written out rather than imported: a
# migration states the shape its own database had at this moment, and importing the catalogue would
# make the migration follow every later edit of it.
_SCALE_AXES = [
    ("values", "family"),
    ("values", "growth"),
    ("personality", "openness"),
    ("communication", "frequency"),
    ("lifestyle", "activity_level"),
    ("leisure", "intellectual"),
]


def upgrade() -> None:
    op.add_column(
        "test_questions",
        sa.Column("kind", sa.String(length=16), server_default="choice", nullable=False),
    )
    pairs = ", ".join(f"('{category}', '{trait}')" for category, trait in _SCALE_AXES)
    op.execute(
        sa.text(f"UPDATE test_questions SET kind = 'scale' WHERE (category, trait) IN ({pairs})")
    )


def downgrade() -> None:
    op.drop_column("test_questions", "kind")
