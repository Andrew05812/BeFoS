from __future__ import annotations

from dataclasses import dataclass, field

from app.compatibility.traits import (
    ALL_CATEGORIES,
    TRAIT_CATEGORIES_BY_KEY,
    goal_compatibility,
)
from app.compatibility.weights import DEFAULT_WEIGHT_CONFIG, WeightConfig

# Score used when there is no data to compare a category on. Neutral so that
# incomplete profiles neither get rewarded nor punished, and the engine never
# crashes or returns NaN.
NEUTRAL_SCORE = 0.5


@dataclass(frozen=True)
class CompatibilityInput:
    """Everything the engine needs about one user.

    Attributes:
        vector: ``{category: {trait: value_in_0_1}}`` from tests/profile.
        interests: set of interest slugs.
        dating_goal: one of the DatingGoal values.
    """

    vector: dict[str, dict[str, float]] = field(default_factory=dict)
    interests: set[str] = field(default_factory=set)
    dating_goal: str = ""


@dataclass(frozen=True)
class CategoryScore:
    key: str
    label: str
    score: float  # 0..1
    weight: float
    has_data: bool

    @property
    def percent(self) -> int:
        return int(round(self.score * 100))

    @property
    def contributed(self) -> float:
        return self.score * self.weight


@dataclass(frozen=True)
class CompatibilityResult:
    overall: float  # 0..1
    categories: tuple[CategoryScore, ...]
    version: int

    @property
    def overall_percent(self) -> int:
        return int(round(self.overall * 100))

    def category(self, key: str) -> CategoryScore | None:
        return next((c for c in self.categories if c.key == key), None)


def _clamp01(value: float) -> float:
    if value != value:  # NaN guard
        return 0.0
    return max(0.0, min(1.0, value))


def _trait_similarity(a: dict[str, float], b: dict[str, float]) -> tuple[float, bool]:
    """Mean similarity across shared traits. Returns (score, has_data)."""
    # Sorted, not straight out of the set: a float sum depends on the order the terms
    # come in, and set order is decided by hash randomisation. Without the sort the same
    # two answers can mean out one ulp apart in two processes, which is enough to move a
    # percent sitting on a rounding boundary.
    shared = sorted(a.keys() & b.keys())
    if not shared:
        return NEUTRAL_SCORE, False
    total = 0.0
    for key in shared:
        va = _clamp01(float(a[key]))
        vb = _clamp01(float(b[key]))
        total += 1.0 - abs(va - vb)
    return _clamp01(total / len(shared)), True


def _interest_similarity(a: set[str], b: set[str]) -> tuple[float, bool]:
    """Jaccard similarity of interest sets."""
    if not a and not b:
        return NEUTRAL_SCORE, False
    if not a or not b:
        return 0.0, True
    intersection = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0, True
    return _clamp01(intersection / union), True


def compute_category(key: str, a: CompatibilityInput, b: CompatibilityInput) -> CategoryScore:
    category = next(c for c in ALL_CATEGORIES if c.key == key)

    if key == "interests":
        score, has_data = _interest_similarity(a.interests, b.interests)
    elif key == "goals":
        if a.dating_goal and b.dating_goal:
            score, has_data = goal_compatibility(a.dating_goal, b.dating_goal), True
        else:
            score, has_data = NEUTRAL_SCORE, False
    elif key in TRAIT_CATEGORIES_BY_KEY:
        score, has_data = _trait_similarity(a.vector.get(key, {}), b.vector.get(key, {}))
    else:  # pragma: no cover - defensive
        score, has_data = NEUTRAL_SCORE, False

    return CategoryScore(
        key=key,
        label=category.label,
        score=_clamp01(score),
        weight=0.0,  # filled by compute_compatibility
        has_data=has_data,
    )


def compute_compatibility(
    a: CompatibilityInput,
    b: CompatibilityInput,
    config: WeightConfig = DEFAULT_WEIGHT_CONFIG,
) -> CompatibilityResult:
    """Deterministic weighted compatibility between two users.

    Guarantees: same inputs -> same output; result always in 0..1 (0..100%);
    never NaN or negative; no randomness.
    """
    categories: list[CategoryScore] = []
    overall = 0.0
    for cat in ALL_CATEGORIES:
        score = compute_category(cat.key, a, b)
        weight = config.weight(cat.key)
        weighted = CategoryScore(
            key=score.key,
            label=score.label,
            score=score.score,
            weight=weight,
            has_data=score.has_data,
        )
        categories.append(weighted)
        overall += weighted.contributed

    return CompatibilityResult(
        overall=_clamp01(overall),
        categories=tuple(categories),
        version=config.version,
    )
