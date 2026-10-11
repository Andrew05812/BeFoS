from __future__ import annotations

"""Recommendation Engine for pairs.

Deterministic scoring of shared activities for two matched users. No randomness.

    activity_score =
        interest_match        (weight 0.40)
      + leisure_match         (weight 0.20)
      + lifestyle_match       (weight 0.15)
      + location_compatibility(weight 0.15)
      + goal_compatibility    (weight 0.10)

Each component is normalised to 0..1 and the total is clamped to 0..1. Every
recommendation carries human-readable reasons derived from the actual data.
"""

from dataclasses import dataclass, field

from app.compatibility.traits import TRAIT_CATEGORIES_BY_KEY, goal_compatibility

# The five numbers the score adds up, keyed by the components the docstring lists, in the order
# `score_activity` multiplies them. Written in one place only: a weight edited where the score does
# not read it is the silent failure the check below exists to catch.
WEIGHTS: dict[str, float] = {
    "interest": 0.40,
    "leisure": 0.20,
    "lifestyle": 0.15,
    "location": 0.15,
    "goal": 0.10,
}


def validate_weights(weights: dict[str, float] = WEIGHTS) -> float:
    """Raise unless the weights sum to 1.0, the way `WeightConfig.validate` guards compatibility."""
    total = round(sum(weights.values()), 6)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Recommendation weights must sum to 1.0, got {total}")
    return total


# A weight edited away from the sum is a broken import, not a page that quietly returns a different
# ceiling: below 1.0 the best pair the product can offer is shown as less than the 100 the scale
# promises, and above 1.0 the defect is invisible through scores at all, because `_clamp01`
# saturates it.
validate_weights()


@dataclass(frozen=True)
class UserSignal:
    interests: set[str] = field(default_factory=set)
    vector: dict[str, dict[str, float]] = field(default_factory=dict)
    city: str = ""
    dating_goal: str = ""
    interest_titles: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ActivitySignal:
    activity_id: int
    slug: str
    title: str
    category: str
    interests: list[str]
    cities: list[str]
    energy: float
    social: float


@dataclass(frozen=True)
class ScoredActivity:
    activity_id: int
    score: float
    reasons: list[str]

    @property
    def percent(self) -> int:
        return int(round(self.score * 100))


def _clamp01(v: float) -> float:
    if v != v:  # NaN guard
        return 0.0
    return max(0.0, min(1.0, v))


def _trait_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    # Sorted for the same reason as the compatibility engine: the sum of the terms is
    # order-sensitive in binary floating point, and a set iterates in hash order.
    shared = sorted(vec_a.keys() & vec_b.keys())
    if not shared:
        return 0.5
    total = sum(1.0 - abs(_clamp01(vec_a[k]) - _clamp01(vec_b[k])) for k in shared)
    return _clamp01(total / len(shared))


def _interest_match(act: ActivitySignal, a: UserSignal, b: UserSignal) -> tuple[float, list[str]]:
    if not act.interests:
        return 0.5, []
    act_set = set(act.interests)
    shared_both = act_set & a.interests & b.interests
    shared_any = (act_set & a.interests) | (act_set & b.interests)
    score = _clamp01(0.6 * (len(shared_both) / len(act_set)) + 0.4 * (len(shared_any) / len(act_set)))
    titles = [a.interest_titles.get(s, b.interest_titles.get(s, s)) for s in sorted(shared_both)[:3]]
    # One noun phrase rather than a verb template: it stays grammatical for one or for three.
    reasons = []
    if titles:
        label = "Общий интерес" if len(titles) == 1 else "Общие интересы"
        reasons.append(f"{label} — {', '.join(titles)}")
    return score, reasons


def _leisure_match(act: ActivitySignal, a: UserSignal, b: UserSignal) -> tuple[float, list[str]]:
    leisure = TRAIT_CATEGORIES_BY_KEY.get("leisure")
    if not leisure:
        return 0.5, []
    # Map activity energy/social to leisure traits and compare with both users.
    act_traits = {"outdoor": act.energy, "social_leisure": act.social, "relaxation": 1.0 - act.energy}
    sim_a = _trait_similarity(act_traits, a.vector.get("leisure", {}))
    sim_b = _trait_similarity(act_traits, b.vector.get("leisure", {}))
    score = _clamp01((sim_a + sim_b) / 2)
    reasons = []
    if score >= 0.7:
        reasons.append("Подходит вашему стилю досуга")
    return score, reasons


def _lifestyle_match(a: UserSignal, b: UserSignal) -> tuple[float, list[str]]:
    sim = _trait_similarity(a.vector.get("lifestyle", {}), b.vector.get("lifestyle", {}))
    reasons = ["У вас близкий ритм жизни"] if sim >= 0.7 else []
    return sim, reasons


def _location_match(act: ActivitySignal, a: UserSignal, b: UserSignal) -> tuple[float, list[str]]:
    if not act.cities:
        # The catalogue simply does not restrict this activity, which says nothing about
        # the pair. Full score, no bullet: "подходит всем" under "почему подходит именно
        # вам" is filler, and the list would otherwise repeat one identical line per card.
        return 1.0, []
    cities = {c.lower() for c in act.cities}
    a_ok = a.city.lower() in cities
    b_ok = b.city.lower() in cities
    score = 1.0 if (a_ok and b_ok) else (0.4 if (a_ok or b_ok) else 0.0)
    reasons = ["Проходит в вашем городе"] if (a_ok and b_ok) else []
    return score, reasons


def _goal_match(a: UserSignal, b: UserSignal) -> tuple[float, list[str]]:
    score = goal_compatibility(a.dating_goal, b.dating_goal)
    reasons = ["Цели знакомства совпадают"] if score >= 0.8 else []
    return score, reasons


def score_activity(act: ActivitySignal, a: UserSignal, b: UserSignal) -> ScoredActivity:
    interest, r1 = _interest_match(act, a, b)
    leisure, r2 = _leisure_match(act, a, b)
    lifestyle, r3 = _lifestyle_match(a, b)
    location, r4 = _location_match(act, a, b)
    goal, r5 = _goal_match(a, b)

    total = _clamp01(
        interest * WEIGHTS["interest"]
        + leisure * WEIGHTS["leisure"]
        + lifestyle * WEIGHTS["lifestyle"]
        + location * WEIGHTS["location"]
        + goal * WEIGHTS["goal"]
    )
    reasons = [r for r in (r1 + r2 + r3 + r4 + r5) if r]
    return ScoredActivity(activity_id=act.activity_id, score=total, reasons=reasons)


def recommend(
    activities: list[ActivitySignal],
    a: UserSignal,
    b: UserSignal,
    *,
    top_n: int = 6,
) -> list[ScoredActivity]:
    scored = [score_activity(act, a, b) for act in activities]
    # Deterministic ordering: score desc, then activity_id asc as a stable tiebreak.
    scored.sort(key=lambda s: (-s.score, s.activity_id))
    return scored[:top_n]
