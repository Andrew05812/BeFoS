"""The screen that finishes a questionnaire promised transparency and printed five numbers.

``TestService.complete()`` builds the trait vector and writes it into ``compatibility_profiles``,
and the results screen opens with «Так алгоритм видит ваши ответы» and closes with «Расчёт
прозрачный: те же ответы всегда дают тот же профиль». Between those two sentences the screen showed
only the five band percents, because ``TestResultOut`` had no field for anything else and the route
threw the vector away on the way out. Measured on the live stand before this stage: a finished
profile carries 21 axis positions in its stored vector, ``POST /tests/complete`` returned
``categories`` of length 5 and nothing else, and the only screen in the app that prints a person's
own position on an axis is the compatibility map of a pair — which a person who has just finished
the questionnaire and has no match yet cannot open.

What the checks below pin: every position the answers produced is named on the way out, each axis
is explained with the word the live taxonomy gives that value, the band a person already saw is the
average of the axes now listed under it, the same answers give the same axes twice, and two people
who answered differently get different axes.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compatibility.traits import NEUTRAL_SIDE, TRAIT_CATEGORIES_BY_KEY, describe_side
from app.models import CompatibilityProfile

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

_FIRST = "s88_axes_first@befos.app"
_SECOND = "s88_axes_second@befos.app"
_THIRD = "s88_axes_third@befos.app"


async def _finished(client: AsyncClient, email: str, *, option_index: int = 0) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"])
    await answer_all_questions(client, creds["token"], option_index=option_index)
    resp = await client.post("/api/v1/tests/complete", headers=auth_headers(creds["token"]))
    assert resp.status_code == 200, resp.text
    return {"creds": creds, "body": resp.json()}


async def _stored_vector(session: AsyncSession, user_id: str) -> dict:
    profile = await session.scalar(
        select(CompatibilityProfile).where(CompatibilityProfile.user_id == uuid.UUID(user_id))
    )
    assert profile is not None, "finishing the test left no profile for the engine to read"
    return profile.vector


async def test_every_axis_the_answers_produced_is_named_on_the_way_out(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The response's axis list and the stored vector are the same set of positions.

    A category absent from the response would be a measurement the person made and never saw; an
    axis the vector does not hold would be a position the questionnaire never asked for.
    """
    finished = await _finished(client, _FIRST)
    axes = finished["body"]["axes"]
    assert axes, "the personal result returned no axes at all"

    stored = await _stored_vector(session, finished["creds"]["user_id"])
    measured = {
        (category, trait)
        for category, traits in stored.items()
        for trait in traits
    }
    assert {(a["category"], a["trait"]) for a in axes} == measured, (
        "the axes the screen can print and the positions the engine stored are different sets"
    )


async def test_an_axis_is_explained_with_the_word_the_taxonomy_gives_its_value(
    client: AsyncClient,
) -> None:
    """`side` is looked up from the live taxonomy, never typed into the route.

    The wording is read here the same way the route reads it — `describe_side` over the value the
    response itself carries — so a taxonomy that renames a polarity side shows up as a failing
    check instead of a screen still quoting the old word.
    """
    axes = (await _finished(client, _SECOND))["body"]["axes"]

    for axis in axes:
        declared = next(
            (t for t in TRAIT_CATEGORIES_BY_KEY[axis["category"]].traits if t.key == axis["trait"]),
            None,
        )
        assert declared is not None, (
            f"{axis['category']}/{axis['trait']} is named as a measured axis the taxonomy does not "
            "declare, so its polarity words cannot be checked"
        )
        assert axis["side"] == describe_side(
            axis["value"], declared.low_label, declared.high_label
        ), f"{axis['label']} was explained by a word its own value does not map to"

    assert any(a["side"] != NEUTRAL_SIDE for a in axes), (
        "every axis came back «умеренно» — the wording is a constant, not a reading of the answers"
    )


async def test_a_band_percent_is_the_average_of_the_axes_listed_under_it(
    client: AsyncClient,
) -> None:
    """The transparency claim on that screen becomes a checkable sentence.

    ``build_vector`` scores a category as the mean of its trait means, so a band that stopped being
    the average of the axes under it would be a percent the listed answers do not produce.
    """
    body = (await _finished(client, _THIRD))["body"]
    by_category: dict[str, list[float]] = {}
    for axis in body["axes"]:
        by_category.setdefault(axis["category"], []).append(axis["value"])

    assert {c["category"] for c in body["categories"]} == set(by_category), (
        "a band was listed without axes, or axes without their band"
    )
    for band in body["categories"]:
        values = by_category[band["category"]]
        assert band["score"] == int(round(sum(values) / len(values) * 100)), (
            f"{band['label']}: {band['score']}% is not the average of the axes the same "
            f"response lists ({[round(v, 3) for v in values]})"
        )


async def test_the_same_answers_come_back_with_the_same_axes(client: AsyncClient) -> None:
    """The screen prints «те же ответы всегда дают тот же профиль» over this list too."""
    creds = (await _finished(client, _FIRST))["creds"]
    first = (
        await client.post("/api/v1/tests/complete", headers=auth_headers(creds["token"]))
    ).json()["axes"]
    second = (
        await client.post("/api/v1/tests/complete", headers=auth_headers(creds["token"]))
    ).json()["axes"]
    assert first == second, "the same answers gave two different axis lists"


async def test_two_people_who_answered_differently_get_different_axes(
    client: AsyncClient,
) -> None:
    """The list tracks the person, not the catalogue.

    One answered every question with its first option, the other with its last; if both came back
    with the same positions, the axes would be read out of the taxonomy rather than out of answers.
    """
    low = (await _finished(client, _FIRST, option_index=0))["body"]["axes"]
    high = (await _finished(client, _SECOND, option_index=-1))["body"]["axes"]

    assert {(a["category"], a["trait"]) for a in low} == {(a["category"], a["trait"]) for a in high}, (
        "the two questionnaires measured different sets of axes"
    )
    assert {a["value"] for a in low} != {a["value"] for a in high}, (
        "opposite answers produced the same positions, so the axes are not read from the answers"
    )
