"""The guard that refuses a stand whose schema predates the models.

Nothing in the product is exercised here. What is pinned is the harness's own honesty: the suite
builds its schema with `create_all`, which only adds tables that are absent and never alters one
that exists, so a database left behind by an earlier stage keeps the shape that stage gave it.
Every later stage that widened a table then fails on the endpoint that touches the widening, and
the run prints that as a product regression. Measured on 2026-10-11 on `main` with a stand from
before stage 63: 11 failed and 4 errors over 684.09 s, all of them in the recommendation family,
the first `UndefinedColumnError: column activity_preferences.match_id does not exist` — while the
same seven files on a freshly built stand passed 59 in 133.60 s, and the CI job on the very same
commit was green because its database had never existed before the run. The refusal is what stops
the stand from spending eleven minutes to lie.
"""

from __future__ import annotations

import asyncio

import pytest
from _pytest.outcomes import Exit
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    text,
)

from .conftest import (
    _drift_between,
    _refuse_a_stale_schema,
    _schema_drift,
    engine,
)


def _pair_table(meta: MetaData, *, with_match: bool) -> Table:
    """The pair-page preference card, in the shape stage 62 left it and the shape stage 63 asked for."""
    columns = [
        Column("id", String, primary_key=True),
        Column("user_id", String, ForeignKey("users.id"), nullable=False),
        Column("activity_id", Integer, nullable=False),
        Column("score", Integer, nullable=False),
    ]
    args = [UniqueConstraint("user_id", "activity_id", name="uq_activity_pref")]
    if with_match:
        columns.append(Column("match_id", String, nullable=True))
        args[0] = UniqueConstraint("user_id", "activity_id", "match_id", name="uq_activity_pref")
        args.append(Index("ix_probe_match_id", "match_id"))
    return Table("activity_preferences", meta, *columns, *args)


def test_the_stand_this_session_runs_on_is_the_shape_the_models_describe() -> None:
    """The guard is not decorative on the database this run is actually using.

    Were the session to stop checking, or were `befos_test` to be reused from an older tree,
    this is the assertion that would notice — before any product test is given a chance to
    mistake the stand for the product. The engine is disposed on the way out for the same reason
    the session fixture disposes it: a pooled connection left bound to a loop this test closed is
    paid for by whichever test comes next. Measured on this tree, a first draft that skipped the
    disposal cost `test_ws_receipt_multi_device.py` an `Event loop is closed` error in its setup,
    two files away from the one that caused it.
    """

    async def _read() -> list[str]:
        async with engine.connect() as conn:
            problems = await conn.run_sync(_schema_drift)
        await engine.dispose()
        return problems

    problems = asyncio.run(_read())

    assert problems == [], "\n  ".join(problems)


def test_a_column_a_later_stage_added_is_named_by_table_and_column() -> None:
    """What the stand is missing has to be readable from the refusal, not from a traceback."""
    models, stand = MetaData(), MetaData()
    _pair_table(models, with_match=True)
    _pair_table(stand, with_match=False)

    problems = _drift_between(models, stand)

    assert "activity_preferences.match_id: the column is missing" in problems, problems
    assert any("uq_activity_pref" in p for p in problems), problems
    assert any("ix_probe_match_id" in p for p in problems), problems


def test_a_clean_rebuild_of_the_same_table_costs_no_complaint() -> None:
    """The guard has to stay silent when the stand really is the models.

    A check that fires on a correct database is worse than no check: the next stage would read
    the refusal as another regression and start looking for the product fault that is not there.
    """
    models, stand = MetaData(), MetaData()
    _pair_table(models, with_match=True)
    _pair_table(stand, with_match=True)

    assert _drift_between(models, stand) == []


def test_an_index_built_on_an_expression_is_not_accused_of_being_the_wrong_index() -> None:
    """`ix_profiles_deck_order` walks `created_at DESC`, which the model side reports as no column.

    Comparing the columns of indexes therefore accuses a correct database; comparing their names
    does not. This is the false accusation the first draft of the guard made on the real stand,
    and it is pinned so it cannot come back.
    """
    models, stand = MetaData(), MetaData()
    Table("profiles", models, Column("user_id", String, primary_key=True),
          Column("created_at", DateTime, nullable=False),
          Index("ix_profiles_deck_order", text("created_at DESC"), "user_id"))
    Table("profiles", stand, Column("user_id", String, primary_key=True),
          Column("created_at", DateTime, nullable=False),
          Index("ix_profiles_deck_order", "created_at", "user_id"))

    assert _drift_between(models, stand) == []


def test_the_revision_bookkeeping_table_a_migrated_stand_carries_is_not_drift() -> None:
    """A stand brought up by the revision chain also holds `alembic_version`, which no model declares."""
    models, stand = MetaData(), MetaData()
    _pair_table(models, with_match=True)
    _pair_table(stand, with_match=True)
    Table("alembic_version", stand, Column("version_num", String(32), primary_key=True))

    assert _drift_between(models, stand) == []


def test_a_table_the_models_dropped_still_counts_as_drift() -> None:
    """Left-over tables change what a read scans, so the stand is not honest just because the columns match."""
    models, stand = MetaData(), MetaData()
    _pair_table(models, with_match=True)
    _pair_table(stand, with_match=True)
    Table("legacy_cardinality", stand, Column("id", Integer, primary_key=True))

    problems = _drift_between(models, stand)

    assert problems == ["legacy_cardinality: a table the models no longer declare"], problems


def test_the_refusal_ends_the_run_naming_the_column_and_the_way_out() -> None:
    """The session does not limp on with a stale stand; it stops, and says what to do.

    A guard that only printed would be read as a broken test and investigated as one, which is
    the mistake this stage exists to prevent.
    """
    models, stand = MetaData(), MetaData()
    _pair_table(models, with_match=True)
    _pair_table(stand, with_match=False)

    with pytest.raises(Exit) as refusal:
        _refuse_a_stale_schema(_drift_between(models, stand))

    message = str(refusal.value)
    assert "activity_preferences.match_id" in message, message
    assert "create_all" in message, "the refusal has to name the mechanism, not just the symptom"
    assert "BEFOS_TEST_DB" in message, "the refusal has to name the way out, not just the wall"


def test_a_stand_that_agrees_with_the_models_is_allowed_to_run() -> None:
    """The other half of the guard: silence is the normal answer, and it must not exit."""
    assert _refuse_a_stale_schema([]) is True
