"""the deck pages the visible population newest-first, and no key was in that order

Revision ID: f3a07c2d5b18
Revises: e6b28c4a13d0
Create Date: 2026-10-10 18:52:41.000000

``DiscoveryRepository.new_candidate_ids`` asks for ``ORDER BY profiles.created_at DESC,
profiles.user_id LIMIT 150``. Nothing in the schema offered that order, so the plan read the whole
visible population and sorted it before anything was kept: ``Limit -> Nested Loop -> ... -> Gather
Merge -> Sort (Sort Key: profiles.created_at DESC, profiles.user_id, quicksort) -> Parallel Seq
Scan on profiles rows=25000 loops=2``. The two workers open all 50 000 profiles between them and
sort them; the anti-joins then see the head of that sorted stream — 248 rows reach them, 150 leave
it.
Measured on the 50 000-profile stand against the application's own statement (docs/SCALE_PLAN.md,
«Парные прогоны стадии 55»), the read costs 5.1 ms with this index instead of 43.5 ms, and the
whole refill call — selecting a batch for a viewer with 20 000 passes behind it — 195.3/196.1 ms
instead of 578.1/562.3 ms, with its candidate read at 15.0/15.1 ms instead of 381.2/381.7 ms and
the chat read of the same run unchanged at 2.5-2.7 ms in all four positions.

The predicate is the deck's visibility rule, as far as an index over ``profiles`` can state it, and
not decoration. Registration leaves a profile shell with ``onboarding_completed_at`` NULL and the
deck refuses it (``b7e3d0a9c421``), and a hidden profile is withdrawn from introductions; neither
can ever be a candidate, so neither belongs in the index. The other two conditions the deck puts on
every row it can show — ``users.is_deleted IS FALSE`` and ``users.is_active IS TRUE`` — belong to the
joined table, and Postgres refuses them here outright: ``CREATE INDEX ... WHERE (SELECT is_deleted
FROM users WHERE users.id = profiles.user_id) IS FALSE`` answers ``ERROR: cannot use subquery in
index predicate``. So they stay in the join, and the index keeps an entry for an account that is
deleted while its profile was visible — on the working database that leak is empty today: 94 rows
satisfy the predicate and 0 of them are deleted or inactive.

The size side is measured the same way (``docs/SCALE_PLAN.md``, «Индекс порядка колоды: что он
берёт с записи»): 1 000 registrations leave the finished index at 2 039 808 bytes — nothing enters
it — and completing their onboarding grows it by 49 152 bytes, six 8 KiB pages, or 49.2 bytes per
row against the 40.8 an entry of the finished index averages. Hiding them again does not grow it at
all: the entries stay as dead space until VACUUM collects them, which is also why the paired write
run — it hides and restores 200 profiles before reading the size — ends one page larger at
2 097 152 bytes. The write side is the reason this revision was not applied on the read number
alone: 1 000 rows crossing into the index cost 53.2 ms against 53.0 ms without it, and one statement
hiding 200 profiles 20.5 ms against 18.1 ms — about 12 microseconds per profile inside that batch,
the only write shift the paired run showed larger than the spread within a configuration.

``DESC`` binds to ``created_at`` alone. The tiebreaker is the deck's own ascending ``user_id``, and
Postgres stores ``(created_at DESC, user_id)`` and ``(created_at DESC, user_id ASC)`` as the same
index: both spellings read back the identical ``indexdef`` and the same 2 039 808 bytes, and with
either of them the deck's read runs as ``Index Scan using ix_profiles_deck_order on profiles
rows=248 loops=1`` with no ``Gather Merge`` and no ``Sort`` node above it (re-measured inside one
rolled-back transaction on the stand, ``docs/SCALE_PLAN.md`` «Приложение: Замер индекса порядка
колоды»: 44.484 ms without the key, 5.104 and 4.962 ms with it). The same key serves a bare
``ORDER BY ... LIMIT`` as ``Limit -> Index Only Scan`` (``Heap Fetches: 0``, 0.243 and 0.176 ms),
but the repository's own read is not index-only — its filters name ``birth_date`` and ``gender``,
which the key does not carry, so its scan goes to the heap. The distinction matters because the
alternative reading — that a bare column inherits the leading ``DESC`` — would have shipped an
index the planner cannot stop early on.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a07c2d5b18"
down_revision: Union[str, None] = "e6b28c4a13d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_profiles_deck_order",
        "profiles",
        [sa.text("created_at DESC"), "user_id"],
        postgresql_where=sa.text("is_hidden IS FALSE AND onboarding_completed_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_profiles_deck_order", table_name="profiles")
