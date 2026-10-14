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

from app.compatibility.traits import (
    NEUTRAL_SIDE,
    TRAIT_CATEGORIES_BY_KEY,
    describe_side,
    goal_compatibility,
)

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


def _shared_side(values: list[float], low_label: str, high_label: str) -> str | None:
    """The one named side all of the numbers sit on, or nothing when they do not.

    A bullet may say "this is your side" only when every value behind the claim answers the same
    word. `describe_side` is the app's single rendering of that word (stage 75 removed a second
    one), so the comparison reads its answer instead of re-deriving the thresholds here, and the
    neutral answer counts as no side at all: "умеренно" says nothing about which way a person
    leans, and a card would claim a preference nobody named.
    """
    sides = {describe_side(_clamp01(v), low_label, high_label) for v in values}
    if len(sides) != 1:
        return None
    side = sides.pop()
    return None if side == NEUTRAL_SIDE else side


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
    # The other half of the arithmetic went unexplained: the score reads `shared_any` at 0.4, so a
    # tag only one of the two chose already moved the number, while the card said nothing about it
    # and the pair could not tell a shared taste from somebody's own one. Which of the two is not
    # named on purpose — the page is the same text for both halves, and a name would be a statement
    # about one of them that the other never asked for.
    alone = sorted(shared_any - shared_both)[:3]
    if alone:
        alone_label = "Интерес одного из вас" if len(alone) == 1 else "Интересы одного из вас"
        alone_titles = ", ".join(
            a.interest_titles.get(s, b.interest_titles.get(s, s)) for s in alone
        )
        reasons.append(f"{alone_label} — {alone_titles}")
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
    # The bullet names the axis instead of the category, and it is spoken only when both halves and
    # the idea answer the same side of it. The number above is the mean of two similarities and can
    # pass 0.7 on one person who is exactly this idea and one who is not, so the line the card used
    # to print over it — «Подходит вашему стилю досуга» — claimed a taste to a pair that does not
    # share it. Measured on the working database before this change: it was the only bullet on 7 of
    # the 8 cards of one real pair, and the same sentence on 15 of the 16 cards both pairs had.
    vec_a = a.vector.get("leisure", {})
    vec_b = b.vector.get("leisure", {})
    candidates: list[tuple[float, str, str]] = []
    for trait in leisure.traits:
        if trait.key not in act_traits or trait.key not in vec_a or trait.key not in vec_b:
            continue
        side = _shared_side(
            [act_traits[trait.key], float(vec_a[trait.key]), float(vec_b[trait.key])],
            trait.low_label,
            trait.high_label,
        )
        if side is None:
            continue
        # One axis per card: the idea's own sharpest answer, so the bullet says what the card is
        # about rather than whichever axis the taxonomy happens to list first.
        candidates.append(
            (
                abs(act_traits[trait.key] - 0.5),
                trait.key,
                f"{trait.label}: и вы, и идея — {side}",
            )
        )
    reasons = []
    if candidates:
        candidates.sort(key=lambda c: (-c[0], c[1]))
        reasons.append(candidates[0][2])
    return score, reasons


def _lifestyle_match(a: UserSignal, b: UserSignal) -> tuple[float, list[str]]:
    vec_a = a.vector.get("lifestyle", {})
    vec_b = b.vector.get("lifestyle", {})
    sim = _trait_similarity(vec_a, vec_b)
    if sim < 0.7:
        return sim, []
    # "У вас близкий ритм жизни" without a noun behind it is a claim about four answers at once,
    # and the mean says nothing about which of them carried it. Name the axis the pair is closest
    # on, in the words the taxonomy gives that axis; when no pair of answers lands on a named side
    # the mean still says the two rhythms are alike, and the plain sentence stays true.
    lifestyle = TRAIT_CATEGORIES_BY_KEY["lifestyle"]
    named: list[tuple[float, str, str]] = []
    for trait in lifestyle.traits:
        if trait.key not in vec_a or trait.key not in vec_b:
            continue
        va = _clamp01(float(vec_a[trait.key]))
        vb = _clamp01(float(vec_b[trait.key]))
        side = _shared_side([va, vb], trait.low_label, trait.high_label)
        if side:
            named.append((1.0 - abs(va - vb), trait.key, f"{trait.label.lower()} ({side})"))
    if not named:
        return sim, ["У вас близкий ритм жизни"]
    named.sort(key=lambda c: (-c[0], c[1]))
    return sim, [f"Близкий ритм жизни: {named[0][2]}"]


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
    reasons = []
    if a_ok and b_ok:
        # The sentence has to agree with how many cities the pair actually has: two people living in
        # two of the listed ones were told the idea runs "in your city", which is a city neither of
        # them shares with the other.
        reasons.append(
            "Проходит в вашем городе"
            if a.city.lower() == b.city.lower()
            else "Проходит в ваших городах"
        )
    elif a_ok or b_ok:
        # The 0.4 this half-match costs the card went unexplained: the page looked as though the
        # idea were available to the pair, while it is available to one of them.
        reasons.append("Проходит в городе одного из вас")
    return score, reasons


def _goal_match(a: UserSignal, b: UserSignal) -> tuple[float, list[str]]:
    # An unanswered goal is not an opposite one. The compatibility engine reads this as neutral with
    # `has_data=False` (`NEUTRAL_SCORE`, and stage 60 applied the same rule to interests), and
    # `_interest_match` beside this one already returns 0.5 for an empty tag list; `goal_compatibility`
    # answers 0.0 for any pair it has no row for, including the empty string the signal builder uses
    # when a profile is missing. Measured before this stage: the card a pair with two named goals was
    # shown at 82 % came back at 72 % when one side named nothing — the whole `goal` band, charged to
    # an answer that was never given.
    if not a.dating_goal or not b.dating_goal:
        return 0.5, []
    score = goal_compatibility(a.dating_goal, b.dating_goal)
    # Two different facts used to print the same sentence. `goal_compatibility` answers 1.0 for two
    # halves that named the same goal and 0.85 for a pair the matrix calls complementary
    # (`marriage` beside `relationship`), and both got "Цели знакомства совпадают" — which is a
    # statement one of those pairs never made. The goal itself is not spelled out: the words a
    # person chose live on the client's option list, and a second rendering of the same answer is
    # what stage 75 removed for percents.
    if score < 0.8:
        return score, []
    same = a.dating_goal == b.dating_goal
    return score, ["Цель знакомства у вас одна" if same else "Цели знакомства не расходятся"]


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
