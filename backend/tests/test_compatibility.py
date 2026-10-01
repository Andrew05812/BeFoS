from __future__ import annotations

import math

import pytest

from app.compatibility.engine import CompatibilityInput, compute_compatibility
from app.compatibility.explanation import build_explanation
from app.compatibility.weights import build_weight_config


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
