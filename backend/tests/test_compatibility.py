from __future__ import annotations

import math
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compatibility.engine import CompatibilityInput, compute_compatibility
from app.compatibility.explanation import build_explanation
from app.compatibility.weights import build_weight_config
from app.models import Match
from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)


def _full_vector(value: float) -> dict[str, dict[str, float]]:
    from app.compatibility.traits import TRAIT_CATEGORIES_BY_KEY

    return {
        cat.key: {trait.key: value for trait in cat.traits}
        for cat in TRAIT_CATEGORIES_BY_KEY.values()
    }


def test_identical_profiles_score_high():
    a = CompatibilityInput(vector=_full_vector(0.8), interests={"x", "y", "z"}, dating_goal="relationship")
    b = CompatibilityInput(vector=_full_vector(0.8), interests={"x", "y", "z"}, dating_goal="relationship")
    result = compute_compatibility(a, b)
    assert result.overall_percent >= 95
    for cat in result.categories:
        assert 0 <= cat.percent <= 100


def test_opposite_profiles_score_low():
    a = CompatibilityInput(vector=_full_vector(1.0), interests={"x", "y"}, dating_goal="marriage")
    b = CompatibilityInput(vector=_full_vector(0.0), interests={"p", "q"}, dating_goal="casual")
    result = compute_compatibility(a, b)
    assert result.overall_percent <= 30


def test_partial_match_between_extremes():
    a = CompatibilityInput(vector=_full_vector(0.7), interests={"x", "y", "z"}, dating_goal="relationship")
    b = CompatibilityInput(vector=_full_vector(0.4), interests={"y", "z", "w"}, dating_goal="relationship")
    result = compute_compatibility(a, b)
    assert 30 < result.overall_percent < 95


def test_empty_inputs_return_neutral_not_nan():
    empty = CompatibilityInput()
    result = compute_compatibility(empty, empty)
    assert not math.isnan(result.overall)
    assert 0 <= result.overall_percent <= 100
    assert result.overall_percent == 50  # neutral fallback


def test_missing_interests_one_side():
    a = CompatibilityInput(vector=_full_vector(0.6), interests={"x", "y"}, dating_goal="relationship")
    b = CompatibilityInput(vector=_full_vector(0.6), interests=set(), dating_goal="relationship")
    result = compute_compatibility(a, b)
    interests = result.category("interests")
    assert interests is not None
    assert interests.percent == 0
    assert 0 <= result.overall_percent <= 100


def test_different_goals_lower_score():
    base_vec = _full_vector(0.7)
    same = compute_compatibility(
        CompatibilityInput(vector=base_vec, interests={"x"}, dating_goal="marriage"),
        CompatibilityInput(vector=base_vec, interests={"x"}, dating_goal="marriage"),
    )
    diff = compute_compatibility(
        CompatibilityInput(vector=base_vec, interests={"x"}, dating_goal="marriage"),
        CompatibilityInput(vector=base_vec, interests={"x"}, dating_goal="casual"),
    )
    assert diff.overall_percent < same.overall_percent
    assert diff.category("goals").percent <= 20


def test_determinism_same_inputs_same_output():
    a = CompatibilityInput(vector=_full_vector(0.65), interests={"x", "y"}, dating_goal="friendship")
    b = CompatibilityInput(vector=_full_vector(0.35), interests={"y", "z"}, dating_goal="friendship")
    r1 = compute_compatibility(a, b)
    r2 = compute_compatibility(a, b)
    assert r1.overall == r2.overall
    assert [c.percent for c in r1.categories] == [c.percent for c in r2.categories]


def test_score_never_out_of_range_or_negative():
    import random

    rng = random.Random(42)
    for _ in range(200):
        a = CompatibilityInput(
            vector=_full_vector(rng.random()),
            interests=set(rng.sample(["a", "b", "c", "d", "e"], rng.randint(0, 5))),
            dating_goal=rng.choice(["marriage", "relationship", "friendship", "casual", "networking"]),
        )
        b = CompatibilityInput(
            vector=_full_vector(rng.random()),
            interests=set(rng.sample(["a", "b", "c", "d", "e"], rng.randint(0, 5))),
            dating_goal=rng.choice(["marriage", "relationship", "friendship", "casual", "networking"]),
        )
        result = compute_compatibility(a, b)
        assert 0 <= result.overall <= 1
        assert not math.isnan(result.overall)
        for cat in result.categories:
            assert 0 <= cat.score <= 1


def test_weights_are_configurable_and_sum_validated():
    config = build_weight_config({"values": 0.30, "leisure": 0.05})
    assert config.weights["values"] == 0.30
    a = CompatibilityInput(vector=_full_vector(0.9), interests={"x"}, dating_goal="relationship")
    b = CompatibilityInput(vector=_full_vector(0.9), interests={"x"}, dating_goal="relationship")
    result = compute_compatibility(a, b, config)
    assert result.category("values").weight == 0.30


def test_invalid_weights_rejected():
    with pytest.raises(ValueError):
        build_weight_config({"values": 0.90})  # would not sum to 1.0


def test_explanation_uses_real_data():
    a = CompatibilityInput(
        vector={"values": {"family": 0.9}, "leisure": {"outdoor": 0.9}},
        interests={"photography", "travel"},
        dating_goal="relationship",
    )
    b = CompatibilityInput(
        vector={"values": {"family": 0.85}, "leisure": {"outdoor": 0.2}},
        interests={"photography", "travel"},
        dating_goal="relationship",
    )
    result = compute_compatibility(a, b)
    explanation = build_explanation(a, b, result)
    assert explanation.shared_interests == ["photography", "travel"]
    assert any("семь" in s.text.lower() or "Похожее" in s.text for s in explanation.strengths) or explanation.strengths
    # outdoor differs a lot -> should appear as a difference
    assert any("отдых" in d.text.lower() or "Разное" in d.text for d in explanation.differences)


def test_explanation_lists_each_category_once():
    # Leisure carries five traits; several of them can match at once. Repeating the
    # same label made the list look broken and hid the other categories.
    a = CompatibilityInput(
        vector={"leisure": {"outdoor": 0.9, "creative": 0.9, "relaxation": 0.9}},
        interests={"cinema"},
        dating_goal="relationship",
    )
    b = CompatibilityInput(
        vector={"leisure": {"outdoor": 0.92, "creative": 0.88, "relaxation": 0.91}},
        interests={"cinema"},
        dating_goal="relationship",
    )
    result = compute_compatibility(a, b)
    explanation = build_explanation(a, b, result)
    for items in (explanation.strengths, explanation.differences):
        categories = [i.category for i in items]
        assert len(categories) == len(set(categories))
    assert sum(1 for s in explanation.strengths if s.category == "leisure") == 1


def test_a_pair_has_one_number_whichever_side_is_asked():
    # The match row stores one percent for the pair, and both people read it. That is only
    # honest while the engine gives the same answer whichever of the two is treated as the
    # viewer; categories are compared symmetrically and the weights are fixed per category.
    pairs = [
        (
            CompatibilityInput(vector=_full_vector(0.9), interests={"x", "y"}, dating_goal="marriage"),
            CompatibilityInput(vector=_full_vector(0.2), interests={"y", "z"}, dating_goal="casual"),
        ),
        (
            CompatibilityInput(vector={"values": {"family": 0.4}}, interests=set(), dating_goal=""),
            CompatibilityInput(vector={"values": {"family": 0.8}, "leisure": {"outdoor": 0.1}},
                               interests={"x"}, dating_goal="friendship"),
        ),
    ]
    for a, b in pairs:
        assert compute_compatibility(a, b).overall == compute_compatibility(b, a).overall


# ---------- the number a screen shows ----------


async def _tested(client: AsyncClient, email: str, name: str, gender: str, option_index: int) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"], option_index=option_index)
    return creds


async def _shown_percent(client: AsyncClient, token: str, match_id: str) -> dict:
    """Where this pair's percent is currently read from, per screen."""
    listing = await client.get("/api/v1/matches", headers=auth_headers(token))
    assert listing.status_code == 200, listing.text
    row = next(m for m in listing.json()["matches"] if m["match_id"] == match_id)
    one = await client.get(f"/api/v1/matches/{match_id}", headers=auth_headers(token))
    assert one.status_code == 200, one.text
    live = await client.get(
        f"/api/v1/matches/{match_id}/compatibility", headers=auth_headers(token)
    )
    assert live.status_code == 200, live.text
    return {
        "list": row["compatibility"],
        "match": one.json()["compatibility"],
        "live": live.json()["overall"],
    }


async def _match_a_pair(client: AsyncClient, a: dict, b: dict) -> str:
    await client.post(f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"]))
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    assert mutual.status_code in (200, 201), mutual.text
    return mutual.json()["match_id"]


async def test_a_retake_moves_the_percent_everywhere(client: AsyncClient):
    # A pair's percent is written onto the match row when the like lands, and the match list
    # reads that row back. Before the refresh existed, a partner who retook the test moved
    # the compatibility screen and left the list where it was: measured on the dev cluster,
    # the same pair showed 100 in the list and 46 one tap further away.
    a = await _tested(client, "cur_a@befos.app", "Аня", "female", 0)
    b = await _tested(client, "cur_b@befos.app", "Боря", "male", 0)
    match_id = await _match_a_pair(client, a, b)

    before = await _shown_percent(client, a["token"], match_id)
    assert before["list"] == before["match"] == before["live"]

    await answer_all_questions(client, a["token"], option_index=1)

    after = await _shown_percent(client, a["token"], match_id)
    assert after["live"] != before["live"], "the retake should have moved this pair"
    assert after["list"] == after["live"], f"the list still says {after['list']}: {after}"
    assert after["match"] == after["live"], f"the header still says {after['match']}: {after}"

    from_partner = await _shown_percent(client, b["token"], match_id)
    assert from_partner["list"] == from_partner["live"]


async def test_a_changed_goal_moves_the_percent_in_the_list(client: AsyncClient):
    # The goal is one of the three inputs of a pair's percent and it is editable after the
    # match, so the list needs the same treatment the test retake gets.
    a = await _tested(client, "goal_a@befos.app", "Аня", "female", 0)
    b = await _tested(client, "goal_b@befos.app", "Боря", "male", 0)
    match_id = await _match_a_pair(client, a, b)

    edited = await client.patch(
        "/api/v1/users/me", json={"dating_goal": "casual"}, headers=auth_headers(a["token"])
    )
    assert edited.status_code == 200, edited.text

    shown = await _shown_percent(client, a["token"], match_id)
    assert shown["list"] == shown["live"], f"the list still says {shown['list']}: {shown}"
    assert shown["match"] == shown["live"]


async def test_a_patch_that_changes_nothing_repairs_a_percent_seeded_wrong(
    client: AsyncClient, session: AsyncSession
):
    # docs/OPERATIONS.md §16 tells an operator to repair a stand seeded before the engine
    # was fixed by PATCHing a field back to the value it already has: the refresh seam keys
    # on the field being sent, not on its value changing. Narrow _REC_FIELDS and that
    # recipe becomes a silent no-op, so the recipe is pinned here instead of trusted.
    a = await _tested(client, "seedfix_a@befos.app", "Аня", "female", 0)
    b = await _tested(client, "seedfix_b@befos.app", "Боря", "male", 0)
    match_id = await _match_a_pair(client, a, b)

    stale = await session.get(Match, uuid.UUID(match_id))
    stale.compatibility_score = 0.82
    await session.commit()

    before = await _shown_percent(client, a["token"], match_id)
    assert before["list"] == 82, f"the row should read as the old seed literal: {before}"
    assert before["live"] != 82, f"nothing to repair if the engine also says 82: {before}"

    edited = await client.patch(
        "/api/v1/users/me", json={"city": "Москва"}, headers=auth_headers(a["token"])
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["city"] == "Москва", "the profile itself must not have moved"

    after = await _shown_percent(client, a["token"], match_id)
    assert after["list"] == after["live"], f"the runbook patch left {after['list']}: {after}"
    assert after["match"] == after["live"]

