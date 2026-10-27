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

A tapped node answers three further questions, all of them from the same two values it already
shows, because a detail panel that invents a second measurement is the defect stage 75 caught in the
explanation line:

* ``confidence`` — how far the similarity that keyed the band sits from the band's own boundary, as
  a percent of the distance that would have carried it into the neighbouring band. ``unknown`` is 0:
  a comparison nobody took part in cannot be sure of anything.
* ``questions`` — the questionnaire items whose option values produced this axis. Interests and the
  dating goal are onboarding choices, not scored axes, so they carry no invented question.
* ``suggestion`` — one line the pair can act on, worded from the two answers' own low/high labels.
  It is a product invitation («обсудите», «пусть каждый приносит»), not a claim about what a
  relationship requires.

The document also carries ``story``: the same seven bands retold in sentences built from aggregates
only — overall percent, each band's percent, weight, how many of its points landed under each
connection word. No axis label and no single answer reaches those lines, because a node label *is*
one person's reply, and the reading that leaves the phone must carry the shape of the pair instead
of either half of their questionnaire. It is composed here, from the layers this module already
assembled, so no second query and no second source of the pair's numbers appears behind it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.compatibility.engine import CompatibilityInput, CompatibilityResult, _clamp01, to_percent
from app.compatibility.traits import (
    ALL_CATEGORIES,
    COMPLEMENTARITY,
    DIFFERENCE_THRESHOLD,
    DISCUSSION,
    HARMONY,
    STRENGTH_THRESHOLD,
    TRAIT_CATEGORIES_BY_KEY,
    Trait,
    connection_for,
    describe_side,
    goal_compatibility,
)
from app.seed_data.questions_catalog import QUESTIONS

UNKNOWN = "unknown"

# Which questionnaire measures which axis. The catalogue is imported rather than queried: the map
# is opened on every pair screen, ``seed.py`` refuses a stored questionnaire that drifted from this
# module, and a second SELECT on `test_questions` would move the round-trip count that stage 76
# measured for `/universe` and published in `docs/SCALE_PLAN.md`.
_QUESTIONS_BY_AXIS: dict[tuple[str, str], tuple[str, ...]] = {}
for _category_key, _trait_key, _text, _options in QUESTIONS:
    _QUESTIONS_BY_AXIS.setdefault((_category_key, _trait_key), ())
    _QUESTIONS_BY_AXIS[(_category_key, _trait_key)] += (_text,)


def questions_for(category_key: str, trait_key: str) -> tuple[str, ...]:
    """The questionnaire items whose option values produced this axis' answer."""
    return _QUESTIONS_BY_AXIS.get((category_key, trait_key), ())


@dataclass(frozen=True)
class UniverseNode:
    key: str
    label: str
    a_value: float | None
    b_value: float | None
    has_data: bool
    connection: str
    evidence: str
    # How far the similarity that keyed the band sits from the band's own boundary, as a percent:
    # 0 is an answer that would change band by a hair, 100 is one that cannot be read otherwise.
    confidence: int
    suggestion: str
    questions: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class UniverseLayer:
    key: str
    label: str
    score: int
    weight: float
    has_data: bool
    coverage: float
    # Mean of the compared nodes' confidence, so a band never reports assurance over answers
    # nobody gave; a layer with nothing compared has nothing to be sure about and reads 0.
    confidence: int
    nodes: tuple[UniverseNode, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Universe:
    overall_percent: int
    version: int
    layers: tuple[UniverseLayer, ...]
    # The pair's own summary, in the order it reads as a story. Lines are built from layer
    # aggregates only — no axis label, no answer value — which is what lets the same document be
    # shared without carrying either person's questionnaire out of the app.
    story: tuple[str, ...] = field(default_factory=tuple)


def _band(sim: float) -> str:
    return connection_for(sim)


def _percent(value: float) -> str:
    """The number the mark under this node prints, not the engine's 0..1 scale value.

    Half always rounds away from zero because that is what the client does
    (``(value * 100f).roundToInt()``) — and now what the engine does too, through the one rule in
    ``engine.to_percent``. Keeping a second copy of the arithmetic here is how the sentence and
    the mark it sits under started disagreeing.
    """
    return str(to_percent(value))


def _confidence(sim: float, connection: str) -> int:
    """How far the answer sits from the edge that would have moved it into another band.

    Each band is measured against its own width, so the scale means the same thing in all three:
    0 is an answer one step from changing its band, 100 is an answer that cannot be read any other
    way. An ``unknown`` node has no similarity to place, so it has no assurance either — 0 is the
    only honest number for a comparison nobody took part in.
    """
    if connection == HARMONY:
        margin, width = sim - STRENGTH_THRESHOLD, 1.0 - STRENGTH_THRESHOLD
    elif connection == DISCUSSION:
        margin, width = DIFFERENCE_THRESHOLD - sim, DIFFERENCE_THRESHOLD
    elif connection == COMPLEMENTARITY:
        margin = min(sim - DIFFERENCE_THRESHOLD, STRENGTH_THRESHOLD - sim)
        width = (STRENGTH_THRESHOLD - DIFFERENCE_THRESHOLD) / 2
    else:
        return 0
    if width <= 0:
        return 0
    return int(math.floor(_clamp01(margin / width) * 100 + 0.5))


def _trait_suggestion(trait: Trait, va: float, vb: float, connection: str) -> str:
    """One line the pair can act on, built from the two answers this node carries.

    These are product suggestions, not conclusions about the relationship: the sentence invites a
    conversation or a shared choice, and it names the answers it was derived from, so a reader can
    disagree with the advice while still seeing the data behind it.
    """
    wa = describe_side(va, trait.low_label, trait.high_label)
    wb = describe_side(vb, trait.low_label, trait.high_label)
    if connection == HARMONY:
        return (
            f"{trait.label}: у обоих «{describe_side((va + vb) / 2, trait.low_label, trait.high_label)}». "
            "Отсюда удобно начинать выбор того, чем заняться вместе."
        )
    if connection == COMPLEMENTARITY:
        if wa == wb:
            return (
                f"{trait.label}: ответы разные, но оба читаются как «{wa}». "
                "Уточните друг у друга, что за этим стоит — за одинаковым словом обычно разное."
            )
        return (
            f"{trait.label}: «{wa}» и «{wb}». Пусть каждый приносит в пару свою сторону "
            "вместо того, чтобы подстраиваться под чужую."
        )
    return (
        f"{trait.label}: «{wa}» против «{wb}». Обсудите это на спокойном месте заранее "
        "и договоритесь об одном конкретном правиле, а не о том, кто прав."
    )


def _missing_trait_suggestion(trait: Trait, answered_by_a: bool, question: str | None) -> str:
    side = "первый" if answered_by_a else "второй"
    opener = f"{trait.label}: ответил только {side}, сравнивать не с чем — это пробел, а не расхождение."
    if question:
        return opener + f" Начните с вопроса из анкеты «{question}»."
    return opener + " Спросите друг друга об этом напрямую."


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
        questions = questions_for(category_key, trait.key)
        if va is not None and vb is not None:
            sim = 1.0 - abs(_clamp01(float(va)) - _clamp01(float(vb)))
            connection = _band(sim)
            nodes.append(
                UniverseNode(
                    key=trait.key,
                    label=trait.label,
                    a_value=_clamp01(float(va)),
                    b_value=_clamp01(float(vb)),
                    has_data=True,
                    connection=connection,
                    evidence=(
                        f"{trait.label}: {_percent(_clamp01(float(va)))} против "
                        f"{_percent(_clamp01(float(vb)))}, сходство ответов {_percent(sim)}"
                    ),
                    confidence=_confidence(sim, connection),
                    suggestion=_trait_suggestion(
                        trait, _clamp01(float(va)), _clamp01(float(vb)), connection
                    ),
                    questions=questions,
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
                    confidence=_confidence(0.0, UNKNOWN),
                    suggestion=_missing_trait_suggestion(
                        trait, va is not None, questions[0] if questions else None
                    ),
                    questions=questions,
                )
            )
    return nodes


def _interest_nodes(
    a: CompatibilityInput,
    b: CompatibilityInput,
    titles: dict[str, str],
) -> list[UniverseNode]:
    nodes: list[UniverseNode] = []
    for slug in sorted(a.interests | b.interests):
        both = slug in a.interests and slug in b.interests
        label = titles.get(slug, slug)
        nodes.append(
            UniverseNode(
                key=slug,
                label=label,
                a_value=1.0 if slug in a.interests else None,
                b_value=1.0 if slug in b.interests else None,
                has_data=both,
                connection=HARMONY if both else UNKNOWN,
                confidence=_confidence(1.0, HARMONY) if both else _confidence(0.0, UNKNOWN),
                evidence=(
                    "назвали оба" if both
                    else "назвал только " + ("первый" if slug in a.interests else "второй")
                ),
                suggestion=(
                    f"{label}: назвали оба — это готовая тема для первой совместной активности."
                    if both
                    else (
                        f"{label}: назвал только "
                        + ("первый" if slug in a.interests else "второй")
                        + ". Спросите друг друга, что именно в этом интересно: карта этого не знает."
                    )
                ),
                # An interest is a name from the questionnaire's chip list, not an axis the test
                # measures, so the map invents no related question for it.
                questions=(),
            )
        )
    return nodes


def _goal_nodes(a: CompatibilityInput, b: CompatibilityInput) -> list[UniverseNode]:
    if a.dating_goal and b.dating_goal:
        cell = goal_compatibility(a.dating_goal, b.dating_goal)
        connection = _band(cell)
        tail = {
            HARMONY: "Цели совпадают — можно планировать встречу, не выясняя заранее, чего хочет каждый.",
            COMPLEMENTARITY: (
                "Цели разные, но не противоположные — уточните друг у друга, что каждый "
                "вкладывает в своё слово."
            ),
            DISCUSSION: (
                "Цели из противоположных полос — это стоит проговорить раньше, чем строить "
                "совместные планы."
            ),
        }[connection]
        return [
            UniverseNode(
                key="goal",
                label="Цели знакомства",
                a_value=cell,
                b_value=cell,
                has_data=True,
                connection=connection,
                evidence=f"цели «{a.dating_goal}» и «{b.dating_goal}» дают {_percent(cell)}",
                confidence=_confidence(cell, connection),
                suggestion=tail,
                # The goal is an onboarding choice, not a trait the questionnaire scores.
                questions=(),
            )
        ]
    side = "первый" if a.dating_goal else "второй"
    return [
        UniverseNode(
            key="goal",
            label="Цели знакомства",
            a_value=1.0 if a.dating_goal else None,
            b_value=1.0 if b.dating_goal else None,
            has_data=False,
            connection=UNKNOWN,
            evidence="цель назвал только " + side,
            confidence=_confidence(0.0, UNKNOWN),
            suggestion=(
                f"Цель назвал только {side}. Спросите друг друга прямо: без этого ответа слой "
                "остаётся без сравнения."
            ),
            questions=(),
        )
    ]


def _count_word(count: int, one: str, few: str, many: str) -> str:
    """Russian pluralisation for the counts the story prints."""
    if count % 10 == 1 and count % 100 != 11:
        return one
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return few
    return many


def build_story(overall_percent: int, layers: tuple[UniverseLayer, ...]) -> tuple[str, ...]:
    """The map retold as a story the pair can send outside the app.

    Only aggregates reach these lines: the overall percent, each band's percent, its weight, and how
    many of its points fell into each connection word. No axis label and no single answer appears,
    because a node label is itself one person's reply — «куда смотрит ambition» tells the reader who
    answered what — while «три совпадения и один разговор» tells them nothing personal.

    A band with no data keeps its label (a band name is taxonomy, not an answer) and prints no
    percent: defect 72-1 is exactly the unscored category passing itself off as a measurement, and a
    shared story is where that misread would travel furthest.

    The order is by weight, then by the engine's own band order, so the story reads the same for
    both partners — the map is pair-global, and a story that opened differently depending on who
    tapped share would be a second, requester-first document.
    """
    ordered = sorted(enumerate(layers), key=lambda pair: (-pair[1].weight, pair[0]))
    lines = [f"Мы совпадаем на {overall_percent}% — и вот как это легло по областям."]
    for _, layer in ordered:
        if not layer.has_data:
            lines.append(f"{layer.label}: сравнивать было нечего, поэтому процентов тут нет.")
            continue
        compared = [node for node in layer.nodes if node.has_data]
        harmony = sum(1 for node in compared if node.connection == HARMONY)
        complement = sum(1 for node in compared if node.connection == COMPLEMENTARITY)
        discussion = sum(1 for node in compared if node.connection == DISCUSSION)
        parts = [
            f"{harmony} {_count_word(harmony, 'совпадение', 'совпадения', 'совпадений')}",
            f"{complement} {_count_word(complement, 'дополнение', 'дополнения', 'дополнений')}",
            f"{discussion} {_count_word(discussion, 'разговор', 'разговора', 'разговоров')}",
        ]
        lines.append(
            f"{layer.label} — {layer.score}% (вес {int(round(layer.weight * 100))}%), "
            f"сверено {len(compared)} из {len(layer.nodes)}: "
            + ", ".join(parts)
            + "."
        )
    return tuple(lines)


def build_universe(
    a: CompatibilityInput,
    b: CompatibilityInput,
    result: CompatibilityResult,
    titles: dict[str, str] | None = None,
) -> Universe:
    """Derive the two-world map from the answers the engine has already scored.

    ``result`` must come from ``compute_compatibility(a, b)`` — the layers copy their percent,
    weight and ``has_data`` out of it rather than recompute them, which is the guarantee that the
    map and the compatibility screen can never show the pair two different numbers.

    ``titles`` maps an interest slug to the catalogue name the pair reads on the chips. It is
    applied while the nodes are built, not after, so the suggestion sentence and the label above it
    name the interest the same way; a label swapped in afterwards would leave the slug inside the
    sentence.
    """
    names = titles or {}
    layers: list[UniverseLayer] = []
    for category in ALL_CATEGORIES:
        cat_score = result.category(category.key)
        if category.key in TRAIT_CATEGORIES_BY_KEY:
            nodes = _trait_nodes(category.key, a, b)
        elif category.key == "interests":
            nodes = _interest_nodes(a, b, names)
        else:
            nodes = _goal_nodes(a, b)
        compared = [n for n in nodes if n.has_data]
        layers.append(
            UniverseLayer(
                key=category.key,
                label=category.label,
                score=cat_score.percent,
                weight=cat_score.weight,
                has_data=cat_score.has_data,
                coverage=len(compared) / len(nodes) if nodes else 0.0,
                confidence=(
                    int(math.floor(sum(n.confidence for n in compared) / len(compared) + 0.5))
                    if compared
                    else 0
                ),
                nodes=tuple(nodes),
            )
        )
    return Universe(
        overall_percent=result.overall_percent,
        version=result.version,
        layers=tuple(layers),
        story=build_story(result.overall_percent, tuple(layers)),
    )
