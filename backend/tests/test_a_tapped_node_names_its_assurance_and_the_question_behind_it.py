"""A tapped node has to say how firmly it sits in its band, what the pair can do about it, and which
question of the questionnaire measures the axis at all.

The map already answered «which answer of which person produced this percent». Opening a node left
three of the brief's questions unanswered: насколько этому верить, что с этим делать, и чем это
измерено. A detail panel that stays silent there pushes the user back to the one number the
compatibility screen prints — which is exactly the product outcome this map exists to remove.

Every field added here is derived from the two values the node already carries, and nothing else:

* ``confidence`` is the distance from the similarity that keyed the band to that band's own
  boundary, scaled by the width of the band, so 0 means «one step and this node reads as another
  connection» and 100 means «this answer cannot be placed anywhere else». An ``unknown`` node has no
  similarity to place, so it is not allowed to be sure of anything: 0.
* ``questions`` comes from the shipped questionnaire catalogue, whose (category, trait) axes are the
  same taxonomy the engine scores. An interest or a dating goal is an onboarding choice, not a
  measured axis, so those nodes carry no question rather than an invented one.
* ``suggestion`` is composed from the taxonomy's own low/high labels for these two answers. It is
  product guidance («обсудите», «пусть каждый приносит свою сторону»), never a claim about what a
  relationship requires, and it prints no number at all: the marks above it already own the numbers.

The catalogue is imported rather than queried on purpose. ``seed.py`` refuses a stored
questionnaire that drifted from it, and a ``SELECT test_questions`` inside the route would change
the round-trip count stage 76 measured and published for ``/universe`` — so one check below proves
the map's own reads still do not touch that table.
"""

from __future__ import annotations

import math
import re

from httpx import AsyncClient
from sqlalchemy import event

from app.compatibility.explanation import DIFFERENCE_THRESHOLD, STRENGTH_THRESHOLD
from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

_DECIMAL = re.compile(r"\d+[.,]\d+")
_DIGIT = re.compile(r"\d")


def _pair(a_values: dict[str, float], b_values: dict[str, float]):
    from app.compatibility.engine import CompatibilityInput, compute_compatibility
    from app.compatibility.universe import build_universe

    a = CompatibilityInput(vector={"values": a_values}, interests={"hiking"}, dating_goal="relationship")
    b = CompatibilityInput(vector={"values": b_values}, interests={"hiking"}, dating_goal="relationship")
    result = compute_compatibility(a, b)
    return {layer.key: layer for layer in build_universe(a, b, result).layers}


def _node(layers: dict, category: str, key: str):
    return next(n for n in layers[category].nodes if n.key == key)


def _sim(va: float, vb: float) -> float:
    return 1.0 - abs(va - vb)


def test_a_node_on_the_edge_of_its_band_is_not_confident_in_it() -> None:
    """A similarity that sits exactly on a threshold is one hundredth away from another band."""
    layers = _pair({"family": 1.0, "career": 1.0}, {"family": 0.75, "career": 0.4})
    harmony = _node(layers, "values", "family")
    discussion = _node(layers, "values", "career")
    assert _sim(1.0, 0.75) == STRENGTH_THRESHOLD == 0.75, "the premise: this pair sits on the strength edge"
    assert _sim(1.0, 0.4) == DIFFERENCE_THRESHOLD == 0.40, "and this one on the difference edge"
    assert (harmony.connection, discussion.connection) == ("harmony", "discussion")
    assert harmony.confidence == 0, (
        f"a node one step from changing its band reported {harmony.confidence} % assurance"
    )
    assert discussion.confidence == 0, (
        f"a node one step from changing its band reported {discussion.confidence} % assurance"
    )


def test_assurance_grows_as_the_answer_moves_off_the_boundary() -> None:
    edge = _node(_pair({"family": 1.0}, {"family": 0.75}), "values", "family")
    nearer = _node(_pair({"family": 1.0}, {"family": 0.85}), "values", "family")
    assert edge.connection == nearer.connection == "harmony", (edge.connection, nearer.connection)
    assert edge.confidence == 0
    assert 0 < nearer.confidence < 100, (
        f"sходство 85 читается увереннее границы и всё ещё не до конца, но узел отвечает "
        f"{nearer.confidence}"
    )


def test_each_band_reaches_certainty_at_its_own_far_side() -> None:
    """100 means «as far from the boundary that decides this band as this band allows», in all three."""
    # similarity 1.0 for family, the exact middle of the complementarity band for career (0.575),
    # and the bottom of the difference band for growth (0.0)
    layers = _pair(
        {"family": 1.0, "career": 1.0, "growth": 1.0},
        {"family": 1.0, "career": 0.575, "growth": 0.0},
    )
    harmony = _node(layers, "values", "family")
    complements = _node(layers, "values", "career")
    discussion = _node(layers, "values", "growth")
    assert (harmony.connection, complements.connection, discussion.connection) == (
        "harmony", "complementarity", "discussion",
    )
    assert (harmony.confidence, complements.confidence, discussion.confidence) == (100, 100, 100), (
        f"{harmony.confidence} / {complements.confidence} / {discussion.confidence}"
    )


def test_a_comparison_nobody_took_part_in_says_so_instead_of_being_sure() -> None:
    from app.compatibility.engine import CompatibilityInput, compute_compatibility
    from app.compatibility.universe import build_universe

    a = CompatibilityInput(vector={"values": {"family": 0.9}}, interests=set(), dating_goal="")
    b = CompatibilityInput(vector={}, interests=set(), dating_goal="")
    layer = next(l for l in build_universe(a, b, compute_compatibility(a, b)).layers if l.key == "values")
    node = layer.nodes[0]
    assert node.connection == "unknown"
    assert node.confidence == 0, "an absence of data cannot carry assurance"
    assert "анкеты" in node.suggestion, (
        f"the gap should name the question that fills it, it says {node.suggestion!r}"
    )


def test_a_band_is_never_more_confident_than_the_answers_it_compared() -> None:
    from app.compatibility.engine import CompatibilityInput, compute_compatibility
    from app.compatibility.universe import build_universe

    a = CompatibilityInput(
        vector={"values": {"family": 1.0, "career": 0.5}}, interests=set(), dating_goal="relationship"
    )
    b = CompatibilityInput(vector={"values": {"family": 1.0}}, interests=set(), dating_goal="relationship")
    result = compute_compatibility(a, b)
    layer = next(l for l in build_universe(a, b, result).layers if l.key == "values")
    compared = [n for n in layer.nodes if n.has_data]
    assert len(compared) == 1, "the premise: one answer was compared, one was not"
    expected = int(math.floor(sum(n.confidence for n in compared) / len(compared) + 0.5))
    assert layer.confidence == expected, (
        f"the band reports {layer.confidence} while its compared nodes average {expected}"
    )

    one_sided = CompatibilityInput(
        vector={"values": {"family": 1.0}}, interests=set(), dating_goal=""
    )
    silent = CompatibilityInput(vector={}, interests=set(), dating_goal="")
    layer = next(
        l for l in build_universe(one_sided, silent, compute_compatibility(one_sided, silent)).layers
        if l.key == "values"
    )
    assert not any(n.has_data for n in layer.nodes)
    assert layer.confidence == 0, "a band with nothing compared has nothing to be sure about"


def test_every_axis_the_engine_scores_is_measured_by_a_question() -> None:
    """The map now points at a question per axis; an axis with none would print an empty promise."""
    from app.compatibility.traits import TRAIT_CATEGORIES
    from app.compatibility.universe import questions_for

    empty = [
        f"{category.key}/{trait.key}"
        for category in TRAIT_CATEGORIES
        for trait in category.traits
        if not questions_for(category.key, trait.key)
    ]
    assert not empty, f"these scored axes have no questionnaire item behind them: {empty}"


def test_a_related_question_belongs_to_the_axis_it_is_shown_under() -> None:
    from app.compatibility.universe import questions_for
    from app.seed_data.questions_catalog import QUESTIONS

    declared = {text: (category, trait) for category, trait, text, _ in QUESTIONS}
    assert len(declared) == len(QUESTIONS), "two catalogue items share one text"

    layers = _pair({"family": 1.0, "career": 0.5}, {"family": 0.25})
    for node in layers["values"].nodes:
        assert node.questions == questions_for("values", node.key)
        for text in node.questions:
            assert declared[text] == ("values", node.key), (
                f"{text!r} measures {declared[text]}, not the axis it is shown under"
            )
    assert layers["values"].nodes[0].questions, "a scored axis was drawn without its question"


def test_an_interest_or_a_goal_invents_no_question_behind_itself() -> None:
    """Both are onboarding choices; the map may name them, not claim a test measured them."""
    layers = _pair({"family": 1.0}, {"family": 0.9})
    for category in ("interests", "goals"):
        for node in layers[category].nodes:
            assert node.questions == (), (
                f"{category}/{node.key} carries {node.questions}, and no questionnaire item "
                "asks about it"
            )


def test_a_suggestion_is_written_from_the_two_answers_not_from_the_band_name() -> None:
    """Two pairs in the same band with different answers must not read the same advice."""
    first = _node(_pair({"family": 1.0}, {"family": 0.0}), "values", "family")
    second = _node(_pair({"career": 1.0}, {"career": 0.0}), "values", "career")
    assert first.connection == second.connection == "discussion"
    assert first.suggestion != second.suggestion, (
        "the advice line is a per-band constant, so it says nothing about this pair"
    )
    assert "семья в приоритете" in first.suggestion and "карьера важнее семьи" in first.suggestion, (
        first.suggestion
    )
    assert "амбиции и карьера" in second.suggestion and "работа без фанатизма" in second.suggestion, (
        second.suggestion
    )


def test_an_advice_line_invents_no_number() -> None:
    """The marks above the node own the numbers; a second rendering inside the advice is the defect
    stage 75 removed from the explanation line."""
    layers = _pair(
        {"family": 1.0, "career": 0.5, "growth": 0.9, "stability": 0.2, "adventure": 1.0},
        {"family": 0.0, "career": 0.9, "growth": 0.85, "stability": 0.75, "adventure": 0.1},
    )
    offenders = [
        f"{node.key}: {node.suggestion!r}"
        for node in layers["values"].nodes
        if _DIGIT.search(node.suggestion) or _DECIMAL.search(node.suggestion)
    ]
    assert not offenders, "; ".join(offenders)
    for node in layers["values"].nodes:
        assert node.suggestion.strip(), f"{node.key} was drawn with an empty advice line"


async def _live_pair(client: AsyncClient, *, anya_index: int, borya_index: int, borya_answers: bool):
    anya = await register_and_auth(client, "insight_a@befos.app")
    await complete_onboarding(
        client, anya["token"], name="Аня", gender="female", goal="relationship",
        interests=["hiking", "cooking"],
    )
    borya = await register_and_auth(client, "insight_b@befos.app")
    await complete_onboarding(
        client, borya["token"], name="Боря", gender="male", goal="marriage",
        interests=["hiking", "travel"],
    )
    await answer_all_questions(client, anya["token"], option_index=anya_index)
    if borya_answers:
        await answer_all_questions(client, borya["token"], option_index=borya_index)
    await client.post(
        f"/api/v1/users/{borya['user_id']}/like", json={}, headers=auth_headers(anya["token"])
    )
    back = await client.post(
        f"/api/v1/users/{anya['user_id']}/like", json={}, headers=auth_headers(borya["token"])
    )
    assert back.status_code == 200, back.text
    return anya["token"], back.json()["match_id"]


async def test_the_map_a_real_pair_opens_answers_all_three_questions(client: AsyncClient) -> None:
    token, match_id = await _live_pair(client, anya_index=0, borya_index=2, borya_answers=True)
    resp = await client.get(f"/api/v1/matches/{match_id}/universe", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    layers = resp.json()["layers"]
    nodes = [(layer, node) for layer in layers for node in layer["nodes"]]
    assert nodes, "the pair opened an empty map"

    for layer, node in nodes:
        assert 0 <= node["confidence"] <= 100, f"{node['key']} reads {node['confidence']}"
        assert node["suggestion"].strip(), f"{layer['category']}/{node['key']} advises nothing"
        assert not _DIGIT.search(node["suggestion"]), node["suggestion"]
        if node["connection"] == "unknown":
            assert node["confidence"] == 0, (
                f"{node['key']} has no comparison and still reports {node['confidence']} %"
            )
        if layer["category"] in ("interests", "goals"):
            assert node["questions"] == [], f"{node['key']} claims a question nobody asks"
        else:
            assert node["questions"], f"{node['key']} is a scored axis with no question named"

    for layer in layers:
        compared = [n for n in layer["nodes"] if n["has_data"]]
        expected = (
            int(math.floor(sum(n["confidence"] for n in compared) / len(compared) + 0.5))
            if compared
            else 0
        )
        assert layer["confidence"] == expected, (
            f"{layer['category']} reports {layer['confidence']} over nodes averaging {expected}"
        )


async def test_an_interest_is_named_in_its_advice_line_as_it_is_named_on_the_map(
    client: AsyncClient,
) -> None:
    """The title used to be pasted onto the label after the sentence was written, which left the
    slug inside the advice the pair reads."""
    token, match_id = await _live_pair(client, anya_index=0, borya_index=2, borya_answers=True)
    resp = await client.get(f"/api/v1/matches/{match_id}/universe", headers=auth_headers(token))
    layer = next(l for l in resp.json()["layers"] if l["category"] == "interests")
    offenders = [
        f"{node['key']}: label={node['label']!r} advice={node['suggestion']!r}"
        for node in layer["nodes"]
        if node["label"] not in node["suggestion"]
    ]
    assert not offenders, "the advice line names the slug, not the interest: " + "; ".join(offenders)


async def test_the_map_still_does_not_read_the_questionnaire_table(client: AsyncClient) -> None:
    """The related questions come from the shipped catalogue, so the round-trip count published for
    ``/universe`` in ``docs/SCALE_PLAN.md`` is still the one the screen pays."""
    from app.core.database import engine

    token, match_id = await _live_pair(client, anya_index=0, borya_index=2, borya_answers=True)
    seen: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        seen.append(" ".join(statement.lower().split()))

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    try:
        resp = await client.get(
            f"/api/v1/matches/{match_id}/universe", headers=auth_headers(token)
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)
    assert resp.status_code == 200, resp.text
    assert resp.json()["layers"], "the measured call answered with an empty map"
    reads = "\n".join(seen)
    assert "test_questions" not in reads, (
        "the map now pays a read of the questionnaire, so the published row for `universe_map` "
        f"prices one call fewer than the screen takes.\nReads:\n{reads}"
    )
