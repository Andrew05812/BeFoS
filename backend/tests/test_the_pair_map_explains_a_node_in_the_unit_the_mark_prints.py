"""A node's explanation has to name its numbers in the unit the mark on the canvas already prints.

The map shows a pair two numbers for the same answer: the mark carries a percent, and the line the
tap opens carries the engine's own scale value. On the live pair the canvas drew «Семья — 100» while
its explanation said «Семья: 1.00 против 0.00, похожие ответы дают 0.00» — the same fact in two units
inside one gesture, with a phrase that never names what the third number measures. The brief rule
this file holds is «нельзя возвращать объяснения, которые не связаны с данными»: an explanation that
contradicts the number printed above it is not connected to the data either.

Rounding is part of the unit. The client prints ``(value * 100f).roundToInt()``, which rounds half
away from zero, so 0.125 becomes 13; Python's ``round`` sends the same value to 12, so the percent
here is computed by a helper that mirrors the client instead of trusting the language default.

The change is confined to the text. No percent, no band and no coverage moved: the checks re-run
against the stage-73 file, which holds those numbers, stay green.

``docs/API.md`` shows the pair's document, and the sentence it prints as a sample is now a published
number too, so the last check reproduces that sample from the module instead of trusting the prose:
a document that drifts from the route it documents is the same defect one layer further out.
"""

from __future__ import annotations

import math
import pathlib
import re

from httpx import AsyncClient

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

_SCALE_DECIMAL = re.compile(r"\d+[.,]\d+")
# A whole number the sentence prints: not a digit inside «0.80», and not a digit run the next
# character turns back into a decimal. A comma or a period that ends prose, not a number, is fine —
# «60, сходство ответов 80» has to yield 60, or the check below would read an empty list and pass
# by not looking.
_INTEGER = re.compile(r"(?<![\d.,])\d+(?!(?:\d|[.,]\d))")


def _percent(value: float | None) -> int | None:
    """The number the client prints for this value: half always rounds away from zero."""
    if value is None:
        return None
    return int(math.floor(value * 100 + 0.5))


def _vec(**categories: dict[str, float]) -> dict:
    return dict(categories)


def _values_pair(a_values: dict[str, float], b_values: dict[str, float]):
    from app.compatibility.engine import CompatibilityInput, compute_compatibility
    from app.compatibility.universe import build_universe

    a = CompatibilityInput(vector={"values": a_values}, interests={"hiking"}, dating_goal="relationship")
    b = CompatibilityInput(vector={"values": b_values}, interests={"hiking"}, dating_goal="relationship")
    result = compute_compatibility(a, b)
    universe = build_universe(a, b, result)
    return {layer.key: layer for layer in universe.layers}


def _node(layers: dict, category: str, key: str):
    return next(n for n in layers[category].nodes if n.key == key)


def test_a_trait_explanation_names_both_marks_in_percents() -> None:
    layers = _values_pair({"family": 1.0}, {"family": 0.0})
    node = _node(layers, "values", "family")
    assert _SCALE_DECIMAL.search(node.evidence) is None, (
        f"the explanation still carries an engine scale value: {node.evidence!r}"
    )
    assert "100 против 0" in node.evidence, (
        f"the two marks read 100 and 0, the explanation says {node.evidence!r}"
    )


def test_the_similarity_the_band_is_keyed_on_is_named_in_the_same_unit() -> None:
    layers = _values_pair({"family": 0.8}, {"family": 0.6})
    node = _node(layers, "values", "family")
    numbers = [int(token) for token in _INTEGER.findall(node.evidence)]
    assert _percent(0.8) in numbers and _percent(0.6) in numbers, (
        f"the explanation does not name the answers its own marks show: {node.evidence!r}"
    )
    similarity = 1.0 - abs(0.8 - 0.6)
    assert _percent(similarity) in numbers, (
        f"the number that keyed the band ({node.connection}) is not in {node.evidence!r}"
    )


def test_a_half_percent_rounds_the_way_the_client_rounds_it() -> None:
    layers = _values_pair({"family": 0.125}, {"family": 0.125})
    node = _node(layers, "values", "family")
    assert _percent(0.125) == 13, "the client's roundToInt gives 13 for 0.125"
    assert 13 in [int(token) for token in _INTEGER.findall(node.evidence)], (
        f"the explanation rounds 0.125 to something the mark does not print: {node.evidence!r}"
    )


def test_the_goal_node_explains_itself_in_the_percent_its_two_marks_carry() -> None:
    from app.compatibility.engine import CompatibilityInput, compute_compatibility
    from app.compatibility.universe import build_universe

    a = CompatibilityInput(vector={}, interests=set(), dating_goal="relationship")
    b = CompatibilityInput(vector={}, interests=set(), dating_goal="relationship")
    result = compute_compatibility(a, b)
    layer = next(l for l in build_universe(a, b, result).layers if l.key == "goals")
    node = layer.nodes[0]
    assert _SCALE_DECIMAL.search(node.evidence) is None, (
        f"the goal explanation names a matrix cell, not the percent both marks show: {node.evidence!r}"
    )
    assert _percent(node.a_value) in [int(t) for t in _INTEGER.findall(node.evidence)], (
        f"the goal marks read {_percent(node.a_value)}, the line says {node.evidence!r}"
    )


def test_no_node_explains_a_number_that_is_not_one_of_its_own_answers() -> None:
    layers = _values_pair(
        {"family": 0.9, "career": 0.2, "growth": 0.5},
        {"family": 0.3, "career": 0.2},
    )
    for node in layers["values"].nodes:
        allowed = {
            _percent(node.a_value),
            _percent(node.b_value),
        }
        if node.a_value is not None and node.b_value is not None:
            allowed.add(_percent(1.0 - abs(node.a_value - node.b_value)))
        body = node.evidence.replace(node.label, "")
        shown = {int(token) for token in _INTEGER.findall(body)}
        assert shown <= {a for a in allowed if a is not None}, (
            f"{node.key} explains itself with {sorted(shown)}, which are not its own numbers "
            f"{sorted(a for a in allowed if a is not None)}: {node.evidence!r}"
        )


def test_an_absence_still_explains_itself_without_a_number() -> None:
    from app.compatibility.engine import CompatibilityInput, compute_compatibility
    from app.compatibility.universe import build_universe

    a = CompatibilityInput(vector={"values": {"family": 0.7}}, interests={"hiking"},
                           dating_goal="relationship")
    b = CompatibilityInput(vector={}, interests={"hiking"}, dating_goal="relationship")
    result = compute_compatibility(a, b)
    layer = next(l for l in build_universe(a, b, result).layers if l.key == "values")
    node = layer.nodes[0]
    assert node.connection == "unknown"
    assert _INTEGER.search(node.evidence) is None, (
        f"a comparison nobody took part in was given a number anyway: {node.evidence!r}"
    )


_ROOT = pathlib.Path(__file__).resolve().parents[2]
_API_DOC = _ROOT / "docs" / "API.md"
_SAMPLE_EVIDENCE = re.compile(r'"evidence":\s*"([^"]+)"')
_SAMPLE_VALUES = re.compile(r'"a_value":\s*([\d.]+),\s*"b_value":\s*([\d.]+)')


def test_the_api_document_prints_an_evidence_line_the_module_produces() -> None:
    """The sample in docs/API.md is a claim about this module, so this module has to answer with it."""
    doc = _API_DOC.read_text(encoding="utf-8")
    shown = _SAMPLE_EVIDENCE.findall(doc)
    assert shown, "docs/API.md no longer samples a universe node with its evidence line"
    values = _SAMPLE_VALUES.search(doc)
    assert values, "docs/API.md no longer samples a node with the two answers its line explains"
    a_value, b_value = float(values.group(1)), float(values.group(2))
    layers = _values_pair({"family": a_value}, {"family": b_value})
    assert [_node(layers, "values", "family").evidence] == shown, (
        f"the document shows answers {a_value} and {b_value} explaining themselves as {shown}, "
        f"while the route answers {_node(layers, 'values', 'family').evidence!r}"
    )


async def _pair(client: AsyncClient):
    anya = await register_and_auth(client, "unit_a@befos.app")
    await complete_onboarding(client, anya["token"], name="Аня", gender="female",
                              goal="relationship", interests=None)
    borya = await register_and_auth(client, "unit_b@befos.app")
    await complete_onboarding(client, borya["token"], name="Боря", gender="male",
                              goal="relationship", interests=None)
    await answer_all_questions(client, anya["token"])
    await answer_all_questions(client, borya["token"])
    await client.post(f"/api/v1/users/{borya['user_id']}/like", json={},
                      headers=auth_headers(anya["token"]))
    back = await client.post(f"/api/v1/users/{anya['user_id']}/like", json={},
                             headers=auth_headers(borya["token"]))
    assert back.status_code == 200, back.text
    return anya["token"], back.json()["match_id"]


async def test_the_map_a_real_pair_reads_explains_every_node_in_percents(client: AsyncClient) -> None:
    token, match_id = await _pair(client)
    resp = await client.get(f"/api/v1/matches/{match_id}/universe", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    offenders = [
        f"{layer['category']}/{node['key']}: {node['evidence']!r}"
        for layer in resp.json()["layers"]
        for node in layer["nodes"]
        if _SCALE_DECIMAL.search(node["evidence"])
    ]
    assert not offenders, "the live document explains nodes in engine units: " + "; ".join(offenders[:4])
