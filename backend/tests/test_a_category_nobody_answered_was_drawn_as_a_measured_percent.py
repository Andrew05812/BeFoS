"""A category nobody answered is not a measurement, and it must not travel the wire as one.

The engine keeps two facts about every category it returns: the number, and whether anything
produced it (``has_data`` on ``CategoryScore`` in ``app/compatibility/engine.py``). The
explanation reads the second fact and stays quiet about a subject neither person spoke on, but
``CategoryScoreOut`` carried only the first, so the pair page received a bare ``50`` for every
skipped band and painted it with the same filled bar as a band two people answered.

Measured with this file's fixture, on the pair where one person took the questionnaire and the
other never opened it (``app/compatibility/engine.py`` for the bands, the live route for the wire):

    values 50  personality 50  communication 50  lifestyle 50  leisure 50
    interests 100  goals 100      overall 60      bands in the response: 7
    bands the response could name as answered or not: none — every read of ``has_data`` on the
    route's JSON raised ``KeyError`` (``s72_red_new_tests.txt``, 11:38:55…11:39:08 UTC)

Five of those seven bands are traits from a questionnaire the second person never opened, so the
``50`` there is the engine's ``NEUTRAL_SCORE`` standing in for absent data, not a middle of the
scale two people landed on — and the client drew each of them as a filled bar next to the two
bands that were measured. The screen's summary line called the result «среднее по категориям», a
second over-claim: the overall is a weighted sum (``app/compatibility/weights.py``) that counts
those filler halves at 0.25+0.15+0.15+0.15+0.10 of its weight.

The fix is to let the flag leave the process. It stays a flag, not a number: a category without
data keeps its neutral score so the overall does not move, and the client marks the band instead
of presenting its percentage as read off two people.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.compatibility.engine import CompatibilityInput, compute_compatibility
from app.schemas.schemas import CategoryScoreOut

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

_TRAIT_CATEGORIES = (
    "values",
    "personality",
    "communication",
    "lifestyle",
    "leisure",
)

_VEC = {
    "values": {"honesty": 0.8, "family": 0.6},
    "personality": {"warm": 0.7, "open": 0.5},
    "communication": {"direct": 0.6, "listen": 0.6},
    "lifestyle": {"sleep": 0.4, "sport": 0.5},
    "leisure": {"outdoors": 0.5, "culture": 0.5},
}


def _person(*, answered: bool, interests: set[str], goal: str = "relationship") -> CompatibilityInput:
    return CompatibilityInput(
        vector=dict(_VEC) if answered else {}, interests=interests, dating_goal=goal
    )


def test_the_engine_marks_a_band_it_could_not_compare() -> None:
    """The fact this file is about: the engine already knows which bands are filler."""
    result = compute_compatibility(
        _person(answered=True, interests={"hiking"}), _person(answered=False, interests=set())
    )
    for key in _TRAIT_CATEGORIES:
        category = result.category(key)
        assert category.has_data is False, f"{key} claims data it does not have"
        assert category.score == 0.5, f"{key} left its neutral value: {category.score}"
    assert result.category("interests").has_data is False
    assert result.category("goals").has_data is True, (
        "two people who both named a goal are comparable, and the band must say so"
    )


def test_a_band_both_people_answered_keeps_reporting_data() -> None:
    result = compute_compatibility(
        _person(answered=True, interests={"hiking", "cooking"}),
        _person(answered=True, interests={"hiking", "opera"}),
    )
    for key in _TRAIT_CATEGORIES:
        assert result.category(key).has_data is True, f"{key} stopped reporting its own answers"
    assert result.category("interests").has_data is True


def test_the_response_model_refuses_to_forget_the_flag() -> None:
    """No default on the server side: a route that omits the flag fails here, not silently.

    A defaulted field would let a future route send "measured" for bands it never checked, which
    is the state this file exists to end.
    """
    with pytest.raises(ValidationError):
        CategoryScoreOut(category="values", label="Ценности", score=50, weight=0.25)


async def _pair(client: AsyncClient, *, anya_test: bool, borya_test: bool):
    """Two accounts that can see each other's pair page, per the questionnaire each one opened."""
    anya = await register_and_auth(client, "hasdata_a@befos.app")
    await complete_onboarding(client, anya["token"], name="Аня", gender="female")
    borya = await register_and_auth(client, "hasdata_b@befos.app")
    await complete_onboarding(client, borya["token"], name="Боря", gender="male")
    if anya_test:
        await answer_all_questions(client, anya["token"])
    if borya_test:
        await answer_all_questions(client, borya["token"])

    await client.post(
        f"/api/v1/users/{borya['user_id']}/like", json={}, headers=auth_headers(anya["token"])
    )
    back = await client.post(
        f"/api/v1/users/{anya['user_id']}/like", json={}, headers=auth_headers(borya["token"])
    )
    assert back.status_code == 200, back.text
    return anya, borya, back.json()["match_id"]


async def _categories(client: AsyncClient, token: str, match_id: str) -> dict[str, dict]:
    resp = await client.get(
        f"/api/v1/matches/{match_id}/compatibility", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    return {c["category"]: c for c in resp.json()["categories"]}


async def test_the_pair_route_names_the_bands_nobody_answered(client: AsyncClient) -> None:
    """The screen a person reads: a filler half and a measured half cannot look the same."""
    anya, _borya, match_id = await _pair(client, anya_test=True, borya_test=False)
    bands = await _categories(client, anya["token"], match_id)

    silent = [key for key, band in bands.items() if not band["has_data"]]
    assert sorted(silent) == sorted(_TRAIT_CATEGORIES), (
        "the bands nobody answered are not the ones the route names: "
        f"silent={sorted(silent)}"
    )
    for key in _TRAIT_CATEGORIES:
        assert bands[key]["score"] == 50, (
            f"{key} stopped sitting at the neutral value, so the flag is now carrying a number"
        )
    for key in ("interests", "goals"):
        assert bands[key]["has_data"] is True, (
            f"Аня and Боря both filled {key} in onboarding, and the route calls it empty"
        )


async def test_answering_the_test_is_what_turns_the_flag(client: AsyncClient) -> None:
    """The flag tracks the answers, because the same pair flips it by taking the questionnaire."""
    anya, borya, match_id = await _pair(client, anya_test=True, borya_test=False)
    before = await _categories(client, anya["token"], match_id)
    assert any(not band["has_data"] for band in before.values())

    await answer_all_questions(client, borya["token"])
    after = await _categories(client, anya["token"], match_id)
    assert all(band["has_data"] for band in after.values()), (
        "Боря answered every question and the page still says nobody did: "
        f"{[k for k, b in after.items() if not b['has_data']]}"
    )


async def test_clearing_interests_silences_only_the_interest_band(client: AsyncClient) -> None:
    """One band going empty mid-pair must not read as every band going empty."""
    anya, borya, match_id = await _pair(client, anya_test=True, borya_test=True)
    await client.patch(
        "/api/v1/users/me", json={"interests": []}, headers=auth_headers(borya["token"])
    )
    bands = await _categories(client, anya["token"], match_id)
    assert bands["interests"]["has_data"] is False
    assert bands["goals"]["has_data"] is True
    for key in _TRAIT_CATEGORIES:
        assert bands[key]["has_data"] is True, (
            f"Аня and Боря both answered the test and {key} reports no data"
        )


async def test_the_public_profile_card_carries_the_flag_too(client: AsyncClient) -> None:
    """The candidate card draws the same bands with the same component.

    ``GET /users/{id}`` builds its ``categories`` by hand out of the same engine result, so this
    route can lose the flag without the pair route losing it — and the card would then promise a
    measured percent for a questionnaire the person never opened.
    """
    anya, borya, _match_id = await _pair(client, anya_test=True, borya_test=False)
    resp = await client.get(
        f"/api/v1/users/{borya['user_id']}", headers=auth_headers(anya["token"])
    )
    assert resp.status_code == 200, resp.text
    bands = {c["category"]: c for c in resp.json()["categories"]}
    silent = sorted(k for k, band in bands.items() if not band["has_data"])
    assert silent == sorted(_TRAIT_CATEGORIES), (
        f"the card names the bands it cannot compare differently than the pair page does: {silent}"
    )
    assert bands["interests"]["has_data"] is True and bands["goals"]["has_data"] is True


async def test_the_personal_result_carries_the_same_field(client: AsyncClient) -> None:
    """Both routes answer the same question, so the client has one rule, not two.

    The personal screen scores one person's own answers, so a band it lists is a band that person
    filled in; a skipped band is absent from the response rather than present and silent.
    """
    anya = await register_and_auth(client, "hasdata_self@befos.app")
    await complete_onboarding(client, anya["token"], name="Аня", gender="female")
    await answer_all_questions(client, anya["token"])

    resp = await client.post(
        "/api/v1/tests/complete", json={}, headers=auth_headers(anya["token"])
    )
    assert resp.status_code == 200, resp.text
    bands = resp.json()["categories"]
    assert bands, "the personal result lost its categories"
    assert all(band["has_data"] is True for band in bands), (
        f"a band the person answered reports no data: "
        f"{[b['category'] for b in bands if not b['has_data']]}"
    )
