"""A catalogue edit reached no database that already had the rows, and the seed said it had seeded.

Measured on 2026-10-12 against a throwaway stand built the way the shipped commands build one
(``alembic upgrade head``, then ``python -m app.seed`` with ``DEMO_ENABLED=false``, artifact
``s71_seed_silence.txt``): one ``UPDATE`` put ``art`` back on ``art_exhibition`` — the exact array
revision ``7c4f2a91be36`` replaced — and the very command ``docker-compose.yml`` runs before
uvicorn on every container start answered ``exit 0`` with
``DEMO_ENABLED=false: catalogues seeded, no demo accounts created`` and left the row carrying the
tag no picker offers. Read field by field over the three live databases (``s71_drift.txt``, 02:28
UTC) the working stand and the pytest stand agreed with the catalogue in 0 places each, and the
50 000-profile stand disagreed in 48 fields — 34 of them being slugs the stand never had, which a
run adds without a word. What a run cannot add it names, and counted with the shipped helpers over
those same three databases (``s71_scale_lines.txt``, 03:15…03:16 UTC) that is 16 lines on the
50 000-profile stand and 0 on the other two: seven activity tag lists still carrying
``nature``/``food``/``art``, seven field lines for five interest rows still named or grouped the way
an older catalogue named them, and two slugs (``music``, ``games``) the catalogue no longer ships at
all. The questionnaire adds no line on any of the three: all 21 positions and their options agree
with the shipped catalogue even on the stand seeded before it grew.

The mechanism was one line of policy, applied three times: every reference table was written only
when it was still empty. A new interest reaches an existing database (the loop adds missing slugs);
a renamed one, a retagged activity, a new card or a reworded question never does. And an activity
the database does not have yet is a card the pair is never offered, so the empty-table rule silently
dropped catalogue additions too.

What the checks below pin is the repair and its one deliberate limit. The seed adds what is absent
and names what differs, and it does not rewrite a row the database already holds: a retagged
activity may be that deployment's own editorial choice, which is why revision ``7c4f2a91be36`` keyed
its ``UPDATE``s on the array it shipped rather than on the slug — and the questionnaire is named,
never rewritten, because ``test_answers.option_id`` points at the option a person actually chose.
Nothing here raises either: the same command is what boots the container.
"""

from __future__ import annotations

import logging

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
# Aliased the way `test_a_question_naming_an_undeclared_axis_is_refused.py` aliases its model:
# pytest tries to collect any module-level name starting with `Test`.
from app.models import Activity, Interest
from app.models import TestOption as OptionRow
from app.models import TestQuestion as QuestionRow
from app.seed import _seed_catalogs
from app.seed_data.activities_catalog import ACTIVITIES
from app.seed_data.interests_catalog import INTERESTS
from app.seed_data.questions_catalog import QUESTIONS

# The array revision 7c4f2a91be36 replaced: three tags a person can pick and one nobody can.
_STALE_TAGS = ["painting", "design", "theatre", "art"]
_SHIPPED_TAGS = ["painting", "design", "theatre"]


async def _lines(session: AsyncSession) -> list[str]:
    return (await _seed_catalogs(session))["drift"]


async def _writes_during(session: AsyncSession, coro) -> list[str]:
    """The SQL one seeding call actually issues, so a name can be told from a rewrite."""
    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        await coro
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
    return [s for s in seen if s.startswith(("insert", "update", "delete"))]


def _about(lines: list[str], needle: str) -> list[str]:
    return [line for line in lines if needle in line]


async def test_the_stand_the_catalogue_seeded_reports_no_drift(session: AsyncSession) -> None:
    """The guard under the guard: a check that fires on a clean stand would name nothing at all.

    ``conftest`` builds the stand's reference rows out of these same catalogue tuples at session
    start, so zero lines here is what every later assertion in this file rests on — and it is the
    invariant stage 61 established: the shipped catalogues and a database they seeded agree.
    """
    assert await _lines(session) == []


async def test_a_stale_activity_tag_is_named_and_left_exactly_as_it_was(session: AsyncSession) -> None:
    row = await session.scalar(select(Activity).where(Activity.slug == "art_exhibition"))
    assert row is not None
    row.interests = _STALE_TAGS
    await session.flush()

    lines = _about(await _lines(session), "activity art_exhibition")

    assert len(lines) == 1, lines
    assert f"interests={_STALE_TAGS!r}" in lines[0], lines[0]
    assert f"interests={_SHIPPED_TAGS!r}" in lines[0], lines[0]
    assert f"id={row.id}" in lines[0], "a name without the row it belongs to is not a name"


async def test_a_named_drift_writes_nothing_over_the_row_it_names(session: AsyncSession) -> None:
    row = await session.scalar(select(Activity).where(Activity.slug == "art_exhibition"))
    assert row is not None
    row.interests = _STALE_TAGS
    row.energy = 0.9
    await session.flush()

    writes = await _writes_during(session, _lines(session))

    assert not [s for s in writes if s.startswith("update activities")], (
        f"the seed rewrote what it was supposed to name: {writes}"
    )
    session.expire_all()
    stored = await session.scalar(select(Activity).where(Activity.slug == "art_exhibition"))
    assert stored is not None
    assert stored.interests == _STALE_TAGS and stored.energy == 0.9, (
        "an operator's own retag has to survive a re-run of the seed, the way revision "
        "7c4f2a91be36 kept the list of a row it did not recognise"
    )


async def test_every_column_of_a_drifting_row_is_named_not_just_the_first(session: AsyncSession) -> None:
    row = await session.scalar(select(Activity).where(Activity.slug == "cooking_class"))
    assert row is not None
    row.interests = ["cooking", "food", "wine_tasting"]
    row.title = "Кулинарный класс"
    await session.flush()

    lines = _about(await _lines(session), "activity cooking_class")

    assert len(lines) == 2, lines
    assert _about(lines, "interests=") and _about(lines, "title="), lines


async def test_a_renamed_interest_is_named_with_both_sides_of_it(session: AsyncSession) -> None:
    row = await session.scalar(select(Interest).where(Interest.slug == "cooking"))
    assert row is not None
    # What the interest catalogue looked like before it grew to forty slugs.
    row.name = "Готовка"
    row.category = "lifestyle"
    await session.flush()

    lines = _about(await _lines(session), "interest cooking")

    assert len(lines) == 2, lines
    assert _about(lines, "name='Готовка'") and _about(lines, "name='Кулинария'"), lines
    assert _about(lines, "category='lifestyle'") and _about(lines, "category='food'"), lines


async def test_a_row_the_catalogue_no_longer_ships_is_named_and_kept(session: AsyncSession) -> None:
    # Two slugs of the 50 000-profile stand are exactly this: `music` and `games`.
    stale = Interest(slug="politics", name="Политика", category="social")
    session.add(stale)
    await session.flush()

    lines = _about(await _lines(session), "interest politics")

    assert len(lines) == 1, lines
    assert "the catalogue does not ship the slug" in lines[0], lines[0]
    session.expire_all()
    assert await session.scalar(select(Interest).where(Interest.slug == "politics")) is not None, (
        "the row carries `user_interests` through an ON DELETE CASCADE, so naming it is all the "
        "seed is allowed to do with it"
    )


async def test_a_card_the_database_does_not_have_is_added_rather_than_only_named(session: AsyncSession) -> None:
    shipped = ACTIVITIES[0]
    row = await session.scalar(select(Activity).where(Activity.slug == shipped[0]))
    assert row is not None
    row_id = row.id
    await session.delete(row)
    await session.flush()

    lines = await _lines(session)
    session.expire_all()
    rebuilt = await session.scalar(select(Activity).where(Activity.slug == shipped[0]))

    assert rebuilt is not None, "a card the catalogue ships and the database lost stays unoffered"
    assert rebuilt.id != row_id
    assert _about(lines, f"activity {shipped[0]}") == [], lines
    assert rebuilt.title == shipped[1] and rebuilt.interests == shipped[4]


async def test_a_question_this_database_reworded_is_named_and_not_rewritten(session: AsyncSession) -> None:
    shipped_text = QUESTIONS[0][2]
    row = await session.scalar(select(QuestionRow).where(QuestionRow.position == 0))
    assert row is not None
    row.text = "Насколько для вас важна семья по утрам?"
    await session.flush()

    lines: list[str] = []

    async def _seed() -> None:
        lines.extend(await _lines(session))

    writes = await _writes_during(session, _seed())
    named = [line for line in lines if line.startswith("question (id=")]

    assert len(named) == 1, lines
    assert f"position={row.position}" in named[0], named[0]
    assert "Насколько для вас важна семья по утрам?" in named[0] and shipped_text in named[0], named[0]
    assert not [s for s in writes if s.startswith("update test_questions")], writes


async def test_options_are_compared_as_a_list_and_a_drift_there_is_named(session: AsyncSession) -> None:
    question = await session.scalar(select(QuestionRow).where(QuestionRow.position == 1))
    assert question is not None
    option = await session.scalar(
        select(OptionRow).where(OptionRow.question_id == question.id).order_by(OptionRow.position).limit(1)
    )
    assert option is not None
    option.value = 0.42
    await session.flush()

    lines = _about(await _lines(session), f"options of question (id={question.id}")

    assert len(lines) == 1, lines
    assert "0.42" in lines[0], lines[0]


async def test_the_drift_is_written_to_the_log_the_operator_reads(session, caplog) -> None:
    row = await session.scalar(select(Activity).where(Activity.slug == "volunteering"))
    assert row is not None
    row.interests = ["volunteering", "nature"]
    await session.flush()

    with caplog.at_level(logging.WARNING, logger="app.seed"):
        await _seed_catalogs(session)

    warned = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warned) == 1, [r.getMessage()[:120] for r in warned]
    text = warned[0].getMessage()
    assert "Catalogue drift: 1 reference row(s)" in text, text
    assert "activity volunteering" in text and "nature" in text, text
    assert "data migration" in text, "the log has to say where the edit belongs"


async def test_a_database_holding_drift_still_finishes_the_run(session: AsyncSession) -> None:
    """Naming is not raising: this same command is what boots the container.

    ``docker-compose.yml`` runs ``python -m app.seed --if-empty`` before uvicorn starts, so a check
    that refused to return would stop a deployment over a stale tag.
    """
    row = await session.scalar(select(Activity).where(Activity.slug == "picnic"))
    assert row is not None
    row.interests = ["nature", "dogs", "cats", "city_walks"]
    await session.flush()

    catalogs = await _seed_catalogs(session)

    assert len(catalogs["drift"]) == 1, catalogs["drift"]
    assert len(catalogs["interests"]) == len(INTERESTS)
    assert len(catalogs["questions"]) == len(QUESTIONS)
