"""The Compatibility Universe: two worlds, seven layers, one source of truth.

This module does not score anything. Every number it moves already lives in
``CompatibilityResult`` from ``app.compatibility.engine`` — the percents, weights and ``has_data``
flags of the seven bands — and every band word it prints follows from the two values the node
itself shows, using the same ``STRENGTH_THRESHOLD`` and ``DIFFERENCE_THRESHOLD`` the explanation
already reads in ``app.compatibility.explanation``. What the universe adds is the missing half of
the sentence: not one percent per band, but the pair of answers the percent was summed from.

Every evidence line names those answers in the unit the mark above it already prints — a percent,
rounded half away from zero the way the client's ``roundToInt()`` rounds it — so a tap opens a
sentence about the number it sits under rather than a second rendering of the same fact.

Four connection types, and the fourth is load-bearing:

* ``harmony`` — two named answers sit in the same top band (similarity >= ``STRENGTH_THRESHOLD``).
* ``complementarity`` — two named answers sit apart without opposing (between the thresholds).
* ``discussion`` — two named answers sit in the opposite band (<= ``DIFFERENCE_THRESHOLD``).
* ``unknown`` — there is no comparison to make. A trait one person never answered, an interest the
  other never named, a goal only one declared. ``unknown`` is never painted as a meeting: it is the
  absence of data, and the percent of the layer keeps sitting at whatever the engine already said
  about it, including the neutral half of ``NEUTRAL_SCORE`` that stage 72 moved onto the wire as
  ``has_data=False``.

The document is pair-global: ``a`` and ``b`` are the pair's own ``user_a``/``user_b`` order, so both
partners open one map of two worlds, not requester-first mirrors of each other (the asymmetry class
stage 70 named for the matrix).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.compatibility.engine import CompatibilityInput, CompatibilityResult, _clamp01
from app.compatibility.explanation import DIFFERENCE_THRESHOLD, STRENGTH_THRESHOLD
from app.compatibility.traits import ALL_CATEGORIES, TRAIT_CATEGORIES_BY_KEY, goal_compatibility

HARMONY = "harmony"
COMPLEMENTARITY = "complementarity"
DISCUSSION = "discussion"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class UniverseNode:
    key: str
    label: str
    a_value: float | None
    b_value: float | None
    has_data: bool
    connection: str
    evidence: str


@dataclass(frozen=True)
class UniverseLayer:
    key: str
    label: str
    score: int
    weight: float
    has_data: bool
    coverage: float
    nodes: tuple[UniverseNode, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Universe:
    overall_percent: int
    version: int
    layers: tuple[UniverseLayer, ...]


def _band(sim: float) -> str:
    if sim >= STRENGTH_THRESHOLD:
        return HARMONY
    if sim <= DIFFERENCE_THRESHOLD:
        return DISCUSSION
    return COMPLEMENTARITY


def _percent(value: float) -> str:
    """The number the mark under this node prints, not the engine's 0..1 scale value.

    Half always rounds away from zero because that is what the client does
    (``(value * 100f).roundToInt()``); Python's own rounding sends 0.125 to 12 while the mark
    next to this sentence shows 13.
    """
    return str(int(math.floor(_clamp01(float(value)) * 100 + 0.5)))


def _trait_nodes(category_key: str, a: CompatibilityInput, b: CompatibilityInput) -> list[UniverseNode]:
    category = TRAIT_CATEGORIES_BY_KEY[category_key]
    a_vector = a.vector.get(category_key, {})
    b_vector = b.vector.get(category_key, {})
    nodes: list[UniverseNode] = []
    for trait in category.traits:
        va = a_vector.get(trait.key)
        vb = b_vector.get(trait.key)
        if va is None and vb is None:
            continue
        if va is not None and vb is not None:
            sim = 1.0 - abs(_clamp01(float(va)) - _clamp01(float(vb)))
            nodes.append(
                UniverseNode(
                    key=trait.key,
                    label=trait.label,
                    a_value=_clamp01(float(va)),
                    b_value=_clamp01(float(vb)),
                    has_data=True,
                    connection=_band(sim),
                    evidence=(
                        f"{trait.label}: {_percent(_clamp01(float(va)))} против "
                        f"{_percent(_clamp01(float(vb)))}, сходство ответов {_percent(sim)}"
                    ),
                )
            )
        else:
            nodes.append(
                UniverseNode(
                    key=trait.key,
                    label=trait.label,
                    a_value=_clamp01(float(va)) if va is not None else None,
                    b_value=_clamp01(float(vb)) if vb is not None else None,
                    has_data=False,
                    connection=UNKNOWN,
                    evidence=(
                        f"{trait.label}: назвал только "
                        f"{'первый' if va is not None else 'второй'}, сравнивать не с чем"
                    ),
                )
            )
    return nodes


def _interest_nodes(a: CompatibilityInput, b: CompatibilityInput) -> list[UniverseNode]:
    nodes: list[UniverseNode] = []
    for slug in sorted(a.interests | b.interests):
        both = slug in a.interests and slug in b.interests
        nodes.append(
            UniverseNode(
                key=slug,
                label=slug,
                a_value=1.0 if slug in a.interests else None,
                b_value=1.0 if slug in b.interests else None,
                has_data=both,
                connection=HARMONY if both else UNKNOWN,
                evidence=(
                    "назвали оба" if both
                    else "назвал только " + ("первый" if slug in a.interests else "второй")
                ),
            )
        )
    return nodes


def _goal_nodes(a: CompatibilityInput, b: CompatibilityInput) -> list[UniverseNode]:
    if a.dating_goal and b.dating_goal:
        cell = goal_compatibility(a.dating_goal, b.dating_goal)
        return [
            UniverseNode(
                key="goal",
                label="Цели знакомства",
                a_value=cell,
                b_value=cell,
                has_data=True,
                connection=_band(cell),
                evidence=f"цели «{a.dating_goal}» и «{b.dating_goal}» дают {_percent(cell)}",
            )
        ]
    return [
        UniverseNode(
            key="goal",
            label="Цели знакомства",
            a_value=1.0 if a.dating_goal else None,
            b_value=1.0 if b.dating_goal else None,
            has_data=False,
            connection=UNKNOWN,
            evidence="цель назвал только " + ("первый" if a.dating_goal else "второй"),
        )
    ]


def build_universe(
    a: CompatibilityInput,
    b: CompatibilityInput,
    result: CompatibilityResult,
) -> Universe:
    """Derive the two-world map from the answers the engine has already scored.

    ``result`` must come from ``compute_compatibility(a, b)`` — the layers copy their percent,
    weight and ``has_data`` out of it rather than recompute them, which is the guarantee that the
    map and the compatibility screen can never show the pair two different numbers.
    """
    layers: list[UniverseLayer] = []
    for category in ALL_CATEGORIES:
        cat_score = result.category(category.key)
        if category.key in TRAIT_CATEGORIES_BY_KEY:
            nodes = _trait_nodes(category.key, a, b)
        elif category.key == "interests":
            nodes = _interest_nodes(a, b)
        else:
            nodes = _goal_nodes(a, b)
        compared = sum(1 for n in nodes if n.has_data)
        layers.append(
            UniverseLayer(
                key=category.key,
                label=category.label,
                score=cat_score.percent,
                weight=cat_score.weight,
                has_data=cat_score.has_data,
                coverage=compared / len(nodes) if nodes else 0.0,
                nodes=tuple(nodes),
            )
        )
    return Universe(
        overall_percent=result.overall_percent,
        version=result.version,
        layers=tuple(layers),
    )
