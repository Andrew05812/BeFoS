"""A question row can name an axis the trait taxonomy never declared, and the answer path took it.

The invariant was written down once in this repository, in ``TestService.validate_categories`` —
and that method had no caller anywhere in the tree, while its body skipped any question whose
category was unknown instead of refusing it. Measured on the live stand before this stage (one row
inserted into ``test_questions`` at ``category='leisure', trait='gaming_taste'`` with two options,
then ``POST /api/v1/tests/answers`` with the whole 22-answer batch from a throwaway account): the
route answered ``200``, ``'gaming_taste'`` appeared in the stored ``compatibility_profiles.vector``,
and two people who answered that question oppositely were a pair whose percent the phantom axis
moved from 92 to 91 — ``_trait_similarity`` divides by the size of the key intersection, so an extra
key of the intersection is an extra term of the average. The same screen then explained them with
``Разное отношение: gaming_taste — gaming_taste vs gaming_taste``, because ``_trait_label`` falls
back to the raw slug when the taxonomy has no such trait, both on the label and on the two polarity
words. A declared axis on the same screen reads ``Похожее отношение: творчество (творчество и
искусство)``.

What the checks below pin: the answer write refuses a drifted row and names it, a refusal leaves
the batch unwritten and the answers already given untouched, an unknown category is refused too, a
drifted row nobody is answering does not stop the declared ones, and the seeded catalogue agrees
with the taxonomy in both directions.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import delete, func, select

from app.compatibility.traits import TRAIT_CATEGORIES_BY_KEY
from app.models import CompatibilityProfile
# Aliased because pytest tries to collect any module-level name starting with `Test`, and these
# three are SQLAlchemy models with constructors — importing them by their own names cost the run
# three collection warnings for nothing.
from app.models import TestAnswer as AnswerRow
from app.models import TestOption as OptionRow
from app.models import TestQuestion as QuestionRow
from app.seed_data.questions_catalog import QUESTIONS

from .conftest import auth_headers, register_and_auth

PHANTOM_TRAIT = "gaming_taste"
PHANTOM_CATEGORY = "leisure"
# A trait the taxonomy does declare, hanging off a category it does not: the other half of the
# silence, because such a row is keyed into the vector and never read back out of it.
UNKNOWN_CATEGORY = "careers"


async def _add_question(session, *, category: str, trait: str) -> int:
    question = QuestionRow(
        category=category, trait=trait,
        text="Насколько вы любите настольные игры?", position=999,
    )
    session.add(question)
    await session.flush()
    for position, (text, value) in enumerate([("Обожаю", 1.0), ("Равнодушен", 0.0)]):
        session.add(OptionRow(question_id=question.id, text=text, value=value, position=position))
    await session.commit()
    return question.id


async def _drop_question(session, question_id: int) -> None:
    await session.execute(delete(OptionRow).where(OptionRow.question_id == question_id))
    await session.execute(delete(QuestionRow).where(QuestionRow.id == question_id))
    await session.commit()


async def _questions(client: AsyncClient, token: str) -> list[dict]:
    resp = await client.get("/api/v1/tests", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["questions"]


def _batch(questions: list[dict], *, skip: int | None = None) -> list[dict]:
    return [
        {"question_id": q["id"], "option_id": q["options"][0]["id"]}
        for q in questions
        if q["id"] != skip and q["options"]
    ]


async def _post(client: AsyncClient, token: str, answers: list[dict]):
    return await client.post("/api/v1/tests/answers", json={"answers": answers},
                             headers=auth_headers(token))


async def _answer_count(session, user_id: str) -> int:
    # Rollback, not a cached read: the write landed on the request's session.
    await session.rollback()
    return await session.scalar(
        select(func.count()).select_from(AnswerRow).where(AnswerRow.user_id == uuid.UUID(user_id))
    )


async def _vector(session, user_id: str) -> dict:
    await session.rollback()
    row = await session.scalar(
        select(CompatibilityProfile).where(CompatibilityProfile.user_id == uuid.UUID(user_id))
    )
    return dict(row.vector) if row is not None else {}


def _declared_axes() -> set[tuple[str, str]]:
    return {(c.key, t.key) for c in TRAIT_CATEGORIES_BY_KEY.values() for t in c.traits}


def _vector_axes(vector: dict) -> set[tuple[str, str]]:
    return {(category, trait)
            for category, traits in vector.items() if isinstance(traits, dict)
            for trait in traits}


async def test_an_axis_the_taxonomy_does_not_declare_is_refused(client: AsyncClient, session) -> None:
    """The answer used to be a 200 and a stored slug; now it is a refusal that names it."""
    creds = await register_and_auth(client, "s69_trait@befos.app")
    question_id = await _add_question(session, category=PHANTOM_CATEGORY, trait=PHANTOM_TRAIT)
    try:
        answers = _batch(await _questions(client, creds["token"]))
        assert len(answers) == 22, f"the drifted row must be in the batch: {len(answers)}"

        resp = await _post(client, creds["token"], answers)

        assert resp.status_code == 422, resp.text
        body = resp.json()["error"]
        assert body["code"] == "validation_error", body
        assert PHANTOM_TRAIT in body["message"], body
        assert await _answer_count(session, creds["user_id"]) == 0
        assert await _vector(session, creds["user_id"]) == {}
    finally:
        await _drop_question(session, question_id)


async def test_the_refusal_names_the_question_and_lists_the_axes_it_does_declare(
    client: AsyncClient, session
) -> None:
    """The caller has to be able to tell which row to fix, and what that row may name."""
    creds = await register_and_auth(client, "s69_names@befos.app")
    question_id = await _add_question(session, category=PHANTOM_CATEGORY, trait=PHANTOM_TRAIT)
    try:
        resp = await _post(client, creds["token"], _batch(await _questions(client, creds["token"])))

        message = resp.json()["error"]["message"]
        assert str(question_id) in message, message
        assert PHANTOM_CATEGORY in message, message
        for key in TRAIT_CATEGORIES_BY_KEY[PHANTOM_CATEGORY].traits:
            assert key.key in message, f"{key.key} missing from {message}"
    finally:
        await _drop_question(session, question_id)


async def test_a_refused_batch_leaves_the_answers_already_given_untouched(
    client: AsyncClient, session
) -> None:
    """Refusing the drifted row must not rewrite what the person answered before it.

    The guard runs before ``upsert_answers``, so a person who answered the declared catalogue and
    then meets a drifted row keeps the vector they had: the refusal costs them nothing but the one
    answer it refuses.
    """
    creds = await register_and_auth(client, "s69_keep@befos.app")
    question_id = await _add_question(session, category=PHANTOM_CATEGORY, trait=PHANTOM_TRAIT)
    try:
        questions = await _questions(client, creds["token"])
        resp = await _post(client, creds["token"], _batch(questions, skip=question_id))
        assert resp.status_code == 200, resp.text
        before = await _vector(session, creds["user_id"])
        assert PHANTOM_TRAIT not in before[PHANTOM_CATEGORY], before

        resp = await _post(client, creds["token"], _batch(questions))

        assert resp.status_code == 422, resp.text
        assert await _answer_count(session, creds["user_id"]) == 21
        assert await _vector(session, creds["user_id"]) == before
    finally:
        await _drop_question(session, question_id)


async def test_a_category_the_taxonomy_does_not_declare_is_refused_too(
    client: AsyncClient, session
) -> None:
    """A declared trait under an undeclared category is the same silence, one level up."""
    creds = await register_and_auth(client, "s69_category@befos.app")
    question_id = await _add_question(session, category=UNKNOWN_CATEGORY, trait="outdoor")
    try:
        resp = await _post(client, creds["token"], _batch(await _questions(client, creds["token"])))

        assert resp.status_code == 422, resp.text
        message = resp.json()["error"]["message"]
        assert UNKNOWN_CATEGORY in message, message
        assert await _answer_count(session, creds["user_id"]) == 0
    finally:
        await _drop_question(session, question_id)


async def test_a_drifted_question_nobody_answers_does_not_stop_the_declared_batch(
    client: AsyncClient, session
) -> None:
    """The check reads the rows this batch names, not the whole catalogue.

    A bad row parked in the table is an administration fault; it must not turn every honest answer
    of every user into a refusal.
    """
    creds = await register_and_auth(client, "s69_alone@befos.app")
    question_id = await _add_question(session, category=PHANTOM_CATEGORY, trait=PHANTOM_TRAIT)
    try:
        resp = await _post(
            client, creds["token"],
            _batch(await _questions(client, creds["token"]), skip=question_id),
        )

        assert resp.status_code == 200, resp.text
        assert PHANTOM_TRAIT not in (await _vector(session, creds["user_id"]))[PHANTOM_CATEGORY]
    finally:
        await _drop_question(session, question_id)


def test_the_seeded_catalogue_names_exactly_the_declared_axes() -> None:
    """The agreement the guard protects, measured both ways over the source catalogue.

    A pair the catalogue asks and the taxonomy does not declare is the phantom axis above. The
    reverse half costs as much: an axis declared but never asked can still be carried by the users
    ``app/seed.py::_latent_traits`` generates, because that list walks ``ALL_TRAITS`` rather than the
    question rows, so on such a base a perfectly matching pair is averaged over six axes instead of
    five — measured at 1.000000 against 0.900000 for the same answers with the sixth axis apart by
    0.6.
    """
    declared = _declared_axes()
    asked = {(category, trait) for category, trait, _text, _options in QUESTIONS}
    assert asked - declared == set()
    assert declared - asked == set()
    assert len(asked) == 21, f"one question per axis expected, got {len(asked)}"


async def test_a_full_honest_answer_writes_only_declared_axes(client: AsyncClient, session) -> None:
    """The accepted path, so the refusal above is not mistaken for the whole behaviour."""
    creds = await register_and_auth(client, "s69_clean@befos.app")

    resp = await _post(client, creds["token"], _batch(await _questions(client, creds["token"])))

    assert resp.status_code == 200, resp.text
    vector = await _vector(session, creds["user_id"])
    axes = _vector_axes(vector)
    declared = _declared_axes()
    assert axes == declared, f"extra: {sorted(axes - declared)}, missing: {sorted(declared - axes)}"
    assert len(vector) == 5, sorted(vector)
