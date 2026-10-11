"""seven activities were tagged with interests nobody can select

Revision ID: 7c4f2a91be36
Revises: f3a07c2d5b18
Create Date: 2026-10-11 04:30:12.000000

The recommendation engine scores an activity by the share of its own tag list a pair covers
(``0.6*|both|/|A| + 0.4*|any|/|A|``, weight 0.40 — ``app/recommendations/engine.py``). Seven of the
25 shipped activities carried one tag that is not an interest slug at all but an interest
*category* name — ``nature`` on ``hiking_trip``, ``picnic``, ``volunteering``, ``dog_walk``,
``food`` on ``cooking_class`` and ``food_market``, ``art`` on ``art_exhibition``. No screen offers
those three words as an interest: the picker reads the ``interests`` table, and the table holds 40
slugs, none of them named ``nature``, ``food`` or ``art``. Read off the working database before
this revision: ``select slug, interests from activities`` returned those three inside seven tag
lists, and every one of them sat next to tags that do exist.

Such a tag can never be covered, so it only ever raises the denominator: the activity is scored
below its own ceiling for every pair, forever, and nothing in the product can lift it. Measured on
one fixed pair — both people naming every interest the activity really lists, the best case there
is — the shipped tag lists and the repaired ones give, on the same input:

    art_exhibition  4 tags -> 3   62 %  72 %   +10
    hiking_trip     3 -> 2        59 %  72 %   +13
    cooking_class   3 -> 2        59 %  72 %   +13
    picnic          4 -> 3        62 %  72 %   +10
    volunteering    2 -> 1        52 %  72 %   +20
    food_market     3 -> 2        59 %  72 %   +13
    dog_walk        3 -> 2        59 %  72 %   +13

``volunteering`` lost half of the interest weight because it had only two tags and one of them was
unreadable. The same pair over the whole catalogue also moves the delivered page: the six cards
come back in a different order (``theatre_night`` falls from fourth to sixth behind three cards
that reached 72).

The repair drops the dead tag and keeps the rest of the list in its original order. Nothing about
the card is lost with it: the word names a *group* of interests, not one — ``nature``, ``food`` and
``art`` are three of the ten categories the 40 selectable interests are grouped into, and in six of
these seven rows at least one of the tags left behind belongs to exactly that group (``hiking`` and
``camping`` under ``nature``, ``cooking`` and ``wine_tasting`` under ``food``, ``painting``,
``theatre`` and ``design`` under ``art``). The seventh says the word was never read from the row at
all: ``volunteering`` carried ``nature`` while its only real tag, ``volunteering``, is a social
interest. No activity is left with an empty list: the smallest surviving list is one tag.

Each UPDATE is keyed on the array it replaces, not on the slug alone: ``WHERE slug = ... AND
interests = <the shipped array>``. An operator who retagged one of these activities by hand does
not match the predicate and keeps their own list — the revision repairs the catalogue it shipped,
not a deployment's editorial choices. Downgrade restores the exact arrays this revision replaced,
so the pair of revisions moves a database back and forth without losing that difference.

The stored pages are a separate matter and are not touched here: ``recommendations.score`` is
written when the page is first built and rebuilt by ``?force=true``, so a page stored before this
revision keeps the number the dead tag produced. Read off the working database after the upgrade:
25 matches, 16 stored cards on 2 of them, and 4 of those 16 rows are activities this revision
re-tagged — the interest component the stored score carries is 0.4667 where the engine now gets
0.7000 (``hiking_trip``), 0.2000 against 0.4000 (``volunteering``), 0.3333 against 0.5000
(``cooking_class``) and 0.2000 against 0.2667 (``picnic``), i.e. 0.0267 to 0.0933 of the total
score. Those pages rebuild on the next ``?force=true``, and nothing in the response says which side
of the revision their number came from.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import bindparam

revision: str = "7c4f2a91be36"
down_revision: Union[str, None] = "f3a07c2d5b18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# slug, the array as shipped, the array after dropping the tag no picker offers.
INTEREST_TAGS: list[tuple[str, list[str], list[str]]] = [
    ("art_exhibition", ["painting", "design", "theatre", "art"], ["painting", "design", "theatre"]),
    ("hiking_trip", ["hiking", "camping", "nature"], ["hiking", "camping"]),
    ("cooking_class", ["cooking", "food", "wine_tasting"], ["cooking", "wine_tasting"]),
    ("picnic", ["nature", "dogs", "cats", "city_walks"], ["dogs", "cats", "city_walks"]),
    ("volunteering", ["volunteering", "nature"], ["volunteering"]),
    ("food_market", ["food", "coffee", "cooking"], ["coffee", "cooking"]),
    ("dog_walk", ["dogs", "nature", "city_walks"], ["dogs", "city_walks"]),
]

_TAG_TYPE = ARRAY(sa.String(80))


def _rewrite(forward: bool) -> None:
    """Swap one shipped array for the other, and only where the row still carries the first."""
    activities = sa.table(
        "activities",
        sa.column("slug", sa.String),
        sa.column("interests", _TAG_TYPE),
    )
    bind = op.get_bind()
    for slug, shipped, repaired in INTEREST_TAGS:
        old, new = (shipped, repaired) if forward else (repaired, shipped)
        bind.execute(
            activities.update()
            .where(activities.c.slug == slug)
            .where(
                activities.c.interests
                == bindparam("old_tags", value=old, type_=_TAG_TYPE, expanding=False)
            )
            .values(interests=bindparam("new_tags", value=new, type_=_TAG_TYPE))
        )


def upgrade() -> None:
    _rewrite(forward=True)


def downgrade() -> None:
    _rewrite(forward=False)
