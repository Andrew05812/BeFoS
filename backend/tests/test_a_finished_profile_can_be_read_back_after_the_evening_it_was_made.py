"""A profile finished in the evening used to be readable only in that evening.

``POST /api/v1/tests/complete`` is the one route that hands a person their own bands and axes, and it
is a write: it rebuilds the vector, re-ranks the deck, refreshes every pair percent and reports
``TEST_COMPLETED``. Nothing in the app could read that profile back afterwards — measured on this
tree before the stage, the routers mounted under ``/api/v1`` offered ``GET /tests`` (the catalogue),
``GET /tests/progress`` (counts), ``POST /tests/answers`` and ``POST /tests/complete``, and no route
in ``users.py`` touched ``compatibility_profiles`` at all. So the twenty-one positions a person's own
questionnaire produced lived in a row the app had no way to show them again, and the screen that
printed them was reachable only by finishing the test a second time.

What the checks below pin: reading the profile back answers with the same two lists the results
screen printed; a person is read as themselves, with no identifier the caller can point at; an empty
or half answered questionnaire comes back as it is — bands only where answers exist, never a zero
invented for a section nobody answered; the reading rebuilds and restamps nothing; and after an
answer changes, the read carries the new numbers and the new moment without anyone finishing again.
"""

from __future__ import annotations

import inspect
import uuid
from collections import defaultdict
from datetime import datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.tests import get_profile
from app.compatibility.traits import TRAIT_CATEGORIES_BY_KEY
from app.main import app
from app.models import CompatibilityProfile

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

_FIRST = "s89_read_first@befos.app"
_SECOND = "s89_read_second@befos.app"
_EMPTY = "s89_read_empty@befos.app"
_HALF = "s89_read_half@befos.app"
_LATER = "s89_read_later@befos.app"

_PROFILE = "/api/v1/tests/profile"


async def _finished(client: AsyncClient, email: str, *, option_index: int = 0) -> dict:
    """A person who got as far as the results screen, with the body that screen printed."""
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"])
    await answer_all_questions(client, creds["token"], option_index=option_index)
    resp = await client.post("/api/v1/tests/complete", headers=auth_headers(creds["token"]))
    assert resp.status_code == 200, resp.text
    return {"creds": creds, "result": resp.json()}


async def _read(client: AsyncClient, token: str) -> dict:
    resp = await client.get(_PROFILE, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _answer(client: AsyncClient, token: str, answers: list[dict]) -> None:
    resp = await client.post(
        "/api/v1/tests/answers", json={"answers": answers}, headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text


async def _catalogue(client: AsyncClient, token: str) -> list[dict]:
    resp = await client.get("/api/v1/tests", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["questions"]


async def _stored(session: AsyncSession, user_id: str) -> CompatibilityProfile:
    """The row as the database holds it, read again rather than recalled from the session."""
    session.expire_all()
    row = await session.scalar(
        select(CompatibilityProfile).where(CompatibilityProfile.user_id == uuid.UUID(user_id))
    )
    assert row is not None, "a scored person has no compatibility profile row to read back"
    return row


async def _card_with_two_different_ends(session: AsyncSession, questions: list[dict]) -> dict:
    """A question whose first and last option the catalogue scores differently.

    The wire does not carry option values — a person reads the texts, and only the engine reads the
    number — so the check that a moved answer moves the profile has to look the values up. Choosing
    the card by its position alone would test a pair of options that can be equal, and a profile that
    correctly did not move would fail it.
    """
    # Imported here rather than at the top of the module: `TestOption` is a SQLAlchemy model whose
    # name pytest reads as a test class, and collecting it by name is a warning on every run.
    from app.models import TestOption

    rows = list(
        (
            await session.execute(
                select(TestOption.question_id, TestOption.id, TestOption.value)
                .where(TestOption.question_id.in_({q["id"] for q in questions}))
                .order_by(TestOption.question_id, TestOption.position, TestOption.id)
            )
        ).all()
    )
    by_question: dict[int, list[tuple[int, int, float]]] = defaultdict(list)
    for question_id, option_id, value in rows:
        by_question[question_id].append((question_id, option_id, value))

    for question in questions:
        options = by_question[question["id"]]
        if len(options) > 1 and options[0][2] != options[-1][2]:
            return {"question": question, "from": options[0][1], "to": options[-1][1]}
    raise AssertionError(
        "no question of the catalogue scores its two ends differently, so the scenario this test "
        "exists for — one answer moved, one position changed — cannot be built on it"
    )


async def test_reading_the_profile_back_answers_with_what_the_results_screen_printed(
    client: AsyncClient,
) -> None:
    """The two screens cannot disagree, because they are handed the same two lists.

    The bands and axes a person read on the evening they finished are what they read on the way back:
    same order, same percents, same polarity words. A second screen built from a near-enough copy of
    the same numbers is how one profile starts to mean two different things.
    """
    finished = await _finished(client, _FIRST)
    assert finished["result"]["axes"], "the fixture finished with no axes to compare against"

    profile = await _read(client, finished["creds"]["token"])
    assert profile["categories"] == finished["result"]["categories"]
    assert profile["axes"] == finished["result"]["axes"]


async def test_a_band_the_profile_prints_is_the_average_of_the_axes_under_it(
    client: AsyncClient,
) -> None:
    """The read takes its bands from ``test_results`` and its axes from the stored vector.

    Those are rows one recompute wrote together, so this is the check that they still say the same
    thing on the way back: a band that stopped being the mean of the positions listed under it would
    be a percent the answers on the screen do not produce.
    """
    profile = await _read(client, (await _finished(client, _SECOND))["creds"]["token"])
    by_category: dict[str, list[float]] = {}
    for axis in profile["axes"]:
        by_category.setdefault(axis["category"], []).append(axis["value"])

    assert {band["category"] for band in profile["categories"]} == set(by_category), (
        "a band was listed with no axes under it, or axes with no band over them"
    )
    for band in profile["categories"]:
        values = by_category[band["category"]]
        assert band["score"] == int(round(sum(values) / len(values) * 100)), (
            f"{band['label']}: {band['score']}% is not the average of the axes the same response "
            f"lists ({[round(v, 3) for v in values]})"
        )


async def test_the_route_names_no_person_the_caller_can_point_at(client: AsyncClient) -> None:
    """Whose profile this is is decided by the token, and by nothing the client can send.

    Three halves of one promise: a stranger is not served at all, the mounted handler takes no person
    argument of any kind, and the two accounts on this database each read their own numbers from the
    same URL. ``GET /users/{user_id}`` is the route that carries an identifier, and it answers with a
    public card — the measured profile is not on it.
    """
    anonymous = await client.get(_PROFILE)
    assert anonymous.status_code == 401, (
        f"a caller with no token was served {anonymous.status_code} of someone's profile"
    )

    assert list(inspect.signature(get_profile).parameters) == ["current_user", "session"], (
        "the profile route grew an argument a caller could fill in, which is a second way to ask "
        "for somebody else's answers"
    )
    mounted = [route for route in app.routes if getattr(route, "path", "") == _PROFILE]
    assert mounted, "the profile route is not mounted"
    assert "{" not in mounted[0].path, "the profile route carries an identifier in its path"

    low = await _finished(client, _FIRST, option_index=0)
    high = await _finished(client, _SECOND, option_index=-1)
    mine = await _read(client, low["creds"]["token"])
    theirs = await _read(client, high["creds"]["token"])
    assert {a["value"] for a in mine["axes"]} != {a["value"] for a in theirs["axes"]}, (
        "two people who answered opposite questions read the same profile"
    )


async def test_a_profile_nobody_ever_scored_reads_back_empty_rather_than_zeroed(
    client: AsyncClient,
) -> None:
    """An account that never answered has nothing measured, and the route says so with nothing.

    Five bands at 0 % would be the worst answer this screen can give: a person who has not started
    would read it as a profile the questionnaire tried to build and failed to build, and the app
    would be publishing a claim about them that no answer produced.
    """
    creds = await register_and_auth(client, _EMPTY)
    await complete_onboarding(client, creds["token"])

    profile = await _read(client, creds["token"])
    assert profile["categories"] == []
    assert profile["axes"] == []
    assert profile["updated_at"] is None, (
        "an unscored profile came back dated, and that date belongs to no measurement"
    )


async def test_a_half_answered_questionnaire_reads_back_the_sections_it_answered(
    client: AsyncClient,
) -> None:
    """A person who stopped after one section sees that section, and only that one.

    ``build_vector`` leaves a category out of the vector when none of its traits carry an answer, so
    the read has nothing to invent for the sections left empty. The gaps themselves are named by
    ``GET /tests/progress``, which counts the catalogue rather than guessing from a zero — and the two
    answers have to fit together, or the screen would show a section as both measured and missing.
    """
    creds = await register_and_auth(client, _HALF)
    await complete_onboarding(client, creds["token"])
    questions = await _catalogue(client, creds["token"])
    first_section = questions[0]["category"]
    taken = [q for q in questions if q["category"] == first_section]
    await _answer(
        client,
        creds["token"],
        [{"question_id": q["id"], "option_id": q["options"][0]["id"]} for q in taken],
    )

    profile = await _read(client, creds["token"])
    assert {band["category"] for band in profile["categories"]} == {first_section}, (
        "a section nobody answered appeared in the profile as a measured band"
    )
    assert {a["trait"] for a in profile["axes"]} == {q["trait"] for q in taken}, (
        "the axes read back are not the positions the answers on file measured"
    )
    # The order the disclosure groups by is the taxonomy's, so the profile screen and the results
    # screen list one section's positions top to bottom the same way.
    declared = TRAIT_CATEGORIES_BY_KEY[first_section]
    answered_traits = [q["trait"] for q in taken]
    assert [a["trait"] for a in profile["axes"]] == [
        trait.key for trait in declared.traits if trait.key in answered_traits
    ]
    assert all(band["has_data"] is True for band in profile["categories"])

    progress = (
        await client.get("/api/v1/tests/progress", headers=auth_headers(creds["token"]))
    ).json()
    assert progress["completed"] is False
    open_sections = {c["key"] for c in progress["categories"] if c["answered"] < c["total"]}
    assert open_sections and first_section not in open_sections, (
        "the progress route did not name this person's gaps, so the screen has nothing to offer "
        "for a profile this read says is partial"
    )


async def test_the_read_rebuilds_nothing_and_restamps_nothing(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Opening a profile is not finishing a test again.

    The write path re-ranks the deck, refreshes pair percents and stamps ``updated_at``. A screen a
    person visits on the way past cannot afford that, and it must not look — to the database or to
    any later reader — like a person who had changed their answers.
    """
    creds = (await _finished(client, _FIRST))["creds"]
    before = await _stored(session, creds["user_id"])
    vector, stamped = before.vector, before.updated_at

    await _read(client, creds["token"])
    await _read(client, creds["token"])

    after = await _stored(session, creds["user_id"])
    assert after.vector == vector, "reading the profile rebuilt the vector it was asked to show"
    assert after.updated_at == stamped, (
        "reading the profile restamped it, so opening one's own screen moved the date that screen "
        "prints"
    )


async def test_an_answer_moved_afterwards_shows_up_without_finishing_the_test_again(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The scenario this stage exists for: a profile read, one answer changed, the profile read again.

    The moved card comes back moved on the next visit, and the date the screen prints moves with it.
    That date is the part that was broken before this stage: an ON CONFLICT statement does not run
    the ORM ``onupdate`` the column declares, so ``updated_at`` stayed on the instant the row was
    first written — measured live on 2026-10-15, created 03:57:54.337135, updated 03:57:54.337141,
    unchanged by a recompute seconds later — and a screen dating a profile off that row printed the
    evening it was started as the moment it last changed.
    """
    creds = await register_and_auth(client, _LATER)
    await complete_onboarding(client, creds["token"])
    questions = await _catalogue(client, creds["token"])
    await _answer(
        client,
        creds["token"],
        [{"question_id": q["id"], "option_id": q["options"][0]["id"]} for q in questions],
    )

    first = await _read(client, creds["token"])
    assert first["categories"], "the answers were saved but the profile read back empty"
    stamped = datetime.fromisoformat(first["updated_at"])
    assert stamped.tzinfo is not None, (
        "the profile date arrived without an offset, so a screen could read tonight as last week"
    )
    assert stamped == (await _stored(session, creds["user_id"])).updated_at

    moved = await _card_with_two_different_ends(session, questions)
    await _answer(
        client, creds["token"], [{"question_id": moved["question"]["id"], "option_id": moved["to"]}]
    )

    second = await _read(client, creds["token"])
    assert datetime.fromisoformat(second["updated_at"]) > stamped, (
        "the profile was rebuilt from a new answer and still prints the date it was first written"
    )
    before = {a["trait"]: a["value"] for a in first["axes"]}
    after = {a["trait"]: a["value"] for a in second["axes"]}
    assert set(before) == set(after), "moving one answer changed which positions the profile holds"
    trait = moved["question"]["trait"]
    assert before[trait] != after[trait], (
        f"the answer moved on {trait} and the profile did not notice"
    )
