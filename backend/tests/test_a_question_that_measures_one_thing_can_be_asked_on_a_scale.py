"""Six axes of the questionnaire measure one thing on a line, and the screen asked them the way it
asks a set of four different places: tap the card whose sentence is closest to you.

Every axis in the catalogue is a gradation — `values/family` runs from «Семья — главный приоритет»
down to «Карьера и свобода важнее», and the same shape holds for how much a person develops, how
open they are to new experience, how much contact they need, how active their days are, and how much
of their leisure is intellectual. A person who knows where they stand on such a line recognises a
slider before they have read four sentences and worked out which one they meant. So those six are
now asked on a scale, and the rest stay cards: «Где вы предпочитаете отдыхать?» names four different
places, and a thumb over it would claim a line the answers do not have.

What the checks below pin is the part that is easy to get wrong while doing it — that a scale is a
way of asking, not a different kind of answer. Its stops are the `test_options` rows the question
already shipped, in the order they already have, so an answer set with a thumb means what the same
answer set by tap meant: the same row is written, the same section count moves, and the same value
reaches the compatibility vector. A deployment holding months of answers to «Насколько для вас важна
семья?» therefore reads those answers the same way after the change as before it, which is the
property that made stage 71 refuse to rewrite a question a database already had.

`kind` is checked where it is decided (the catalogue), where it is stored (the seeded rows), where
it leaves the server (`GET /api/v1/tests`), and where it must change nothing (the written answer and
the vector built from it).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compatibility.traits import TRAIT_CATEGORIES_BY_KEY
from app.models import CompatibilityProfile
from app.models import TestQuestion as QuestionRow
from app.seed_data.questions_catalog import CHOICE, QUESTIONS, SCALE, SCALE_AXES, question_kind

from .conftest import auth_headers, register_and_auth

_EMAILS = ["s84_scale@befos.app", "s84_stops@befos.app"]


def _shipped(category: str, trait: str) -> list[tuple[str, float]]:
    """The stops one axis carries in the catalogue, in the order the catalogue lists them."""
    matches = [options for cat, tr, _text, options in QUESTIONS if (cat, tr) == (category, trait)]
    assert len(matches) == 1, f"{category}/{trait} is asked {len(matches)} times in the catalogue"
    return matches[0]


async def _catalog(client: AsyncClient, token: str) -> dict:
    resp = await client.get("/api/v1/tests", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _answer(client: AsyncClient, token: str, pairs: list[tuple[int, int]]) -> dict:
    resp = await client.post(
        "/api/v1/tests/answers",
        json={"answers": [{"question_id": q, "option_id": o} for q, o in pairs]},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _progress(client: AsyncClient, token: str) -> dict:
    resp = await client.get("/api/v1/tests/progress", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_every_section_of_the_questionnaire_is_also_asked_on_a_scale() -> None:
    """The point of the declaration is that no section is only cards any more.

    A scale that only ever appears in one section leaves the other four with the same four taps they
    always had, which is the monotony this is here to break. An axis named here that the catalogue
    does not ask, or that the engine does not declare, would make `kind` a claim about a question
    whose answer nobody reads back — the same silence `_require_declared_axes` refuses an answer to.
    """
    asked = {(category, trait) for category, trait, _text, _options in QUESTIONS}
    declared_by_function = {
        (category, trait) for category, trait, _text, _options in QUESTIONS
        if question_kind(category, trait) == SCALE
    }
    assert declared_by_function == SCALE_AXES, (
        f"the catalogue's own declaration names {sorted(SCALE_AXES)} and `question_kind` answers "
        f"scale for {sorted(declared_by_function)} — the seed and the wire follow the function"
    )
    assert SCALE_AXES <= asked, (
        f"{sorted(SCALE_AXES - asked)} are declared scales but the catalogue asks no such question"
    )
    for category, trait in sorted(SCALE_AXES):
        declared = TRAIT_CATEGORIES_BY_KEY.get(category)
        assert declared is not None, f"{category} is not a category the engine reads"
        assert trait in {t.key for t in declared.traits}, (
            f"{category}/{trait} folds into a vector the engine never reads back"
        )

    scale_categories = {category for category, _trait in SCALE_AXES}
    asked_categories = {category for category, _trait in asked}
    assert scale_categories >= asked_categories, (
        f"sections {sorted(asked_categories - scale_categories)} are still cards only"
    )


def test_a_scale_question_carries_ordered_stops_reaching_both_ends() -> None:
    """A thumb is only an honest picture of answers that lie on one line.

    Every item the catalogue ships is a four-stop gradation today, so this fires the day a
    categorical set is declared as a scale by mistake — which is exactly the mistake the comment on
    `SCALE_AXES` warns about. The two words the screen prints under the slider are the first and the
    last stop, so a scale that does not reach both ends of its axis would label the line wrongly.
    """
    scales = [(category, trait, text, options) for category, trait, text, options in QUESTIONS
              if question_kind(category, trait) == SCALE]
    assert scales, "no question is asked on a scale, so the loop below names nothing at all"
    for category, trait, text, options in scales:
        assert len(options) >= 3, f"{text!r} is asked on a scale of {len(options)} stops"
        values = [value for _option_text, value in options]
        assert all(0.0 <= value <= 1.0 for value in values), f"{text!r} ships a stop outside 0..1"
        descending = all(a > b for a, b in zip(values, values[1:]))
        ascending = all(a < b for a, b in zip(values, values[1:]))
        assert descending or ascending, (
            f"{text!r} is asked as a scale, but its stops run {values} — no line to set a thumb on"
        )
        low, high = (values[-1], values[0]) if descending else (values[0], values[-1])
        assert low == 0.0 and high == 1.0, (
            f"{text!r} asks the ends of {category}/{trait} at {low} and {high}, "
            "not at the ends of the axis the engine scores"
        )


async def test_the_catalogue_route_names_the_scale_and_still_ships_its_stops(client: AsyncClient) -> None:
    """A client that knows nothing about scales keeps working, and one that does can draw a thumb.

    The second half matters as much as the first: the stops are what an answer is written against,
    so a `kind` that arrived without them would leave a slider with nothing to point at, and an old
    client would have no cards to tap either.
    """
    creds = await register_and_auth(client, _EMAILS[0])
    questions = (await _catalog(client, creds["token"]))["questions"]

    for question in questions:
        expected = question_kind(question["category"], question["trait"])
        assert question["kind"] == expected, (
            f"{question['text']!r} is asked {question['kind']} on the wire and {expected} in the catalogue"
        )
        assert question["options"], f"{question['text']!r} reaches the client with no stops"

    scales = [q for q in questions if q["kind"] == SCALE]
    assert len(scales) == len(SCALE_AXES), (
        f"the wire carries {len(scales)} scales, the catalogue ships {len(SCALE_AXES)}"
    )
    assert {(q["category"], q["trait"]) for q in scales} == SCALE_AXES
    assert any(q["kind"] == CHOICE for q in questions), "the whole questionnaire became a scale"


async def test_an_answer_set_on_a_scale_means_the_same_value_to_the_engine(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The vector is read off the option the thumb landed on, as it is off the card that was tapped.

    Both kinds are answered on their second stop and the profile the engine consumes is then read
    back: if a scale answer reached it any other way, the pair's percent would move when nothing the
    person believes about themselves did. The card question in the same batch is the control —
    without it this check would pass on a questionnaire whose answers were ignored altogether.
    """
    creds = await register_and_auth(client, _EMAILS[0])
    questions = (await _catalog(client, creds["token"]))["questions"]
    scale_question = next(q for q in questions if q["kind"] == SCALE)
    card_question = next(q for q in questions if q["kind"] == CHOICE)

    body = await _answer(
        client,
        creds["token"],
        [(q["id"], q["options"][1]["id"]) for q in questions],
    )
    assert body["answered"] == len(questions), f"the whole questionnaire counted {body['answered']}"

    marked = (await _catalog(client, creds["token"]))["questions"]
    by_id = {q["id"]: q for q in marked}
    for question in (scale_question, card_question):
        assert by_id[question["id"]]["selected_option_id"] == question["options"][1]["id"], (
            f"{question['text']!r} was answered and comes back unmarked, so the person cannot see "
            "their own stop"
        )

    completed = await client.post("/api/v1/tests/complete", headers=auth_headers(creds["token"]))
    assert completed.status_code == 200, completed.text

    profile = await session.scalar(
        select(CompatibilityProfile).where(CompatibilityProfile.user_id == uuid.UUID(creds["user_id"]))
    )
    assert profile is not None, "finishing the test left no profile for the engine to read"
    for question in (scale_question, card_question):
        shipped = _shipped(question["category"], question["trait"])[1][1]
        measured = profile.vector[question["category"]][question["trait"]]
        assert measured == pytest.approx(shipped), (
            f"{question['category']}/{question['trait']} was asked {question['kind']!r} and the "
            f"engine reads {measured} off the second stop, which the catalogue ships at {shipped}"
        )


async def test_a_scale_counts_as_one_question_of_its_section(client: AsyncClient) -> None:
    """The band math a section shows must not change because one of its questions grew a thumb.

    Stage 83 publishes `answered`/`total` per section, and the compatibility screen sends a person
    into the section whose band is empty. A scale that counted twice — or not at all — would send
    them to a section that is already finished.
    """
    creds = await register_and_auth(client, _EMAILS[1])
    questions = (await _catalog(client, creds["token"]))["questions"]
    scale_question = next(q for q in questions if q["kind"] == SCALE)
    section = scale_question["category"]
    of_section = [q for q in questions if q["category"] == section]

    await _answer(client, creds["token"], [(q["id"], q["options"][0]["id"]) for q in of_section])
    entry = next(s for s in (await _progress(client, creds["token"]))["categories"] if s["key"] == section)

    assert entry["total"] == len(of_section), (
        f"section {section} holds {len(of_section)} catalogue questions and counts {entry['total']}"
    )
    assert entry["answered"] == entry["total"], (
        f"a section answered to its last question reads {entry['answered']} of {entry['total']}"
    )


async def test_the_seeded_database_asks_the_axes_the_catalogue_declares(session: AsyncSession) -> None:
    """The column has to say what the catalogue says, or the wire and the rows disagree.

    A fresh database gets `kind` from the seed; a database that already held the questionnaire gets
    it from revision `d7a3f2b81c64`, whose UPDATE names the same six axes. This reads the rows the
    seed wrote, so either half drifting away from the declaration goes red here.
    """
    rows = (await session.execute(select(QuestionRow))).scalars().all()
    assert rows, "this stand holds no questionnaire, so the seed has not been asked anything"
    for row in rows:
        assert row.kind == question_kind(row.category, row.trait), (
            f"question {row.id} ({row.category}/{row.trait}) is stored as {row.kind!r}"
        )
    assert {row.kind for row in rows} == {CHOICE, SCALE}
