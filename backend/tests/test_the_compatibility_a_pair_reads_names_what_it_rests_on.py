"""A percentage a pair cannot account for is a decoration, not an explanation.

The engine already knows three things it never tells the screen: how many of its seven bands
rest on answers that were actually compared (`has_data`) and how much weight that is, what kind of
difference a gap is (the map decides harmony / complementarity / discussion at
`universe._band`, the explanation screen stayed mute), and what the two could start talking about.
This row asks the read of a pair's own compatibility to say all three, in words the engine's data
supports and nothing more.

The rule is stated before it is implemented, so the test is the argument: a band nobody answered
must be named as neutral rather than drawn as a measured percent, and a difference must be called
by the one rule the map already uses, not by a second opinion invented here.
"""

from __future__ import annotations

from httpx import AsyncClient

from app.compatibility.engine import CompatibilityInput, compute_compatibility
from app.compatibility.explanation import build_explanation
from app.compatibility.traits import TRAIT_CATEGORIES_BY_KEY, connection_for

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

BANDS_TOTAL = 7


def _vector(**categories: dict[str, float]) -> dict[str, dict[str, float]]:
    return dict(categories)


def _full(category_key: str, value: float) -> dict[str, float]:
    cat = TRAIT_CATEGORIES_BY_KEY[category_key]
    return {trait.key: value for trait in cat.traits}


def test_a_difference_is_named_by_the_one_rule_the_map_uses() -> None:
    assert connection_for(0.9) == "harmony"
    assert connection_for(0.5) == "complementarity"
    assert connection_for(0.2) == "discussion"


def test_the_result_counts_the_bands_that_were_actually_compared() -> None:
    a = CompatibilityInput(vector=_vector(values=_full("values", 0.8)), interests=set(), dating_goal="")
    b = CompatibilityInput(vector=_vector(values=_full("values", 0.8)), interests=set(), dating_goal="")
    result = compute_compatibility(a, b)
    assert result.bands_total == BANDS_TOTAL
    assert result.bands_measured == 1
    assert result.measured_weight == 0.25


def test_a_pair_without_comparable_answers_admits_it_rests_on_nothing() -> None:
    result = compute_compatibility(CompatibilityInput(), CompatibilityInput())
    assert result.bands_measured == 0
    assert result.measured_weight == 0.0
    assert result.overall_percent == 50  # the engine's neutral, not a measured 50


def test_the_explanation_carries_the_kind_of_every_line_it_prints() -> None:
    a = CompatibilityInput(
        vector=_vector(values=_full("values", 0.8), lifestyle=_full("lifestyle", 0.9)),
        interests={"пешие прогулки", "джаз"},
        dating_goal="relationship",
    )
    b = CompatibilityInput(
        vector=_vector(values=_full("values", 0.78), lifestyle=_full("lifestyle", 0.1)),
        interests={"пешие прогулки", "рок"},
        dating_goal="relationship",
    )
    result = compute_compatibility(a, b)
    explanation = build_explanation(a, b, result)
    assert explanation.strengths and explanation.differences
    for item in explanation.strengths + explanation.differences:
        assert item.connection in {"harmony", "complementarity", "discussion"}
        # The line's kind is the similarity's kind, decided once, not a second opinion.
        assert item.connection == connection_for(item.score)
    assert explanation.bands_measured == result.bands_measured
    assert explanation.measured_weight == result.measured_weight


def test_a_shared_interest_gives_the_pair_a_place_to_start() -> None:
    a = CompatibilityInput(interests={"джаз"})
    b = CompatibilityInput(interests={"джаз"})
    explanation = build_explanation(a, b, compute_compatibility(a, b))
    assert explanation.starter == "Начните с общего интереса: «джаз»"


def test_the_first_word_is_deterministic_and_names_its_own_basis() -> None:
    empty_a, empty_b = CompatibilityInput(), CompatibilityInput()
    first = build_explanation(empty_a, empty_b, compute_compatibility(empty_a, empty_b))
    second = build_explanation(empty_a, empty_b, compute_compatibility(empty_a, empty_b))
    assert first.starter == second.starter
    assert "нет" in first.starter and "сравн" in first.starter


async def _ready(client: AsyncClient, email: str, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def test_the_pair_read_prints_what_its_number_rests_on(client: AsyncClient) -> None:
    a = await _ready(client, "s125_expl_a@befos.app", "Аня", "female")
    b = await _ready(client, "s125_expl_b@befos.app", "Боря", "male")
    await client.post(f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"]))
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    match_id = mutual.json()["match_id"]

    body = (
        await client.get(f"/api/v1/matches/{match_id}/compatibility", headers=auth_headers(a["token"]))
    ).json()

    assert body["bands_total"] == BANDS_TOTAL
    assert 1 <= body["bands_measured"] <= BANDS_TOTAL
    assert body["measured_weight"] == round(
        sum(c["weight"] for c in body["categories"] if c["has_data"]), 4
    )
    assert all(item["connection"] in {"harmony", "complementarity", "discussion"}
               for item in body["strengths"] + body["differences"])
    assert body["starter"]

    outsider = await _ready(client, "s125_expl_c@befos.app", "Вика", "female")
    refusal = await client.get(
        f"/api/v1/matches/{match_id}/compatibility", headers=auth_headers(outsider["token"])
    )
    assert refusal.status_code == 404, refusal.text
