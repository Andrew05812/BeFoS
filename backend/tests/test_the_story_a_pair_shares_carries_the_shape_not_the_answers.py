"""A pair must be able to tell somebody else what the map found without handing them the answers.

Stage 79.3 gives the same document a third reading: «Our Story». It has to be shareable, which makes
it the one reading where a leak travels furthest — a node label is itself somebody's reply («семья в
приоритете» says which side of the pair answered what), and defect 72-1 is exactly the unscored band
passing itself off as a measurement, which a shared screenshot would carry into a conversation the
app never sees.

So the story is built from aggregates the map already shows and nothing else:

* the overall percent and each band's percent, copied out of the engine — no second arithmetic;
* each band's weight and how many of its points were actually compared;
* how many compared points fell under each connection word.

The order is by weight, so the story reads the same whichever partner taps «поделиться» — the map is
pair-global, and a story that opened differently depending on who asked for it would be a second,
requester-first document of the kind stage 70 named for the goal matrix.
"""

from __future__ import annotations

import re

from httpx import AsyncClient

from app.compatibility.engine import CompatibilityInput, compute_compatibility
from app.compatibility.universe import build_universe

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

_PERCENT = re.compile(r"(\d+)\s*%")
_DIGIT = re.compile(r"\d")


def _universe(a: CompatibilityInput, b: CompatibilityInput):
    return build_universe(a, b, compute_compatibility(a, b))


def _story(a: CompatibilityInput, b: CompatibilityInput) -> tuple[str, ...]:
    return _universe(a, b).story


_BOTH = dict(interests={"hiking"}, dating_goal="relationship")


def test_no_line_of_the_story_repeats_somebody_s_answer() -> None:
    """A band name is taxonomy; an axis label is one person's reply. Only the first may be shared."""
    a = CompatibilityInput(vector={"values": {"family": 1.0, "career": 0.2}}, **_BOTH)
    b = CompatibilityInput(vector={"values": {"family": 0.1, "career": 1.0}}, **_BOTH)
    universe = _universe(a, b)
    text = "\n".join(universe.story)
    offenders = [
        f"{layer.key}/{node.key}: label={node.label!r}"
        for layer in universe.layers
        for node in layer.nodes
        # The goals band has a single axis, so its band name and its node label are the same words;
        # naming the band is what the story is for, naming the answer is what it must not do.
        if node.label != layer.label and node.label.lower() in text.lower()
    ]
    assert not offenders, "the story carries an axis label: " + "; ".join(offenders)
    assert "hiking" not in text, "the story leaks an interest slug"


def test_a_band_without_a_single_comparison_shares_no_percent() -> None:
    """The whole point of defect 72-1: a neutral placeholder is not a measurement, and a shared
    story is where a reader would take it for one."""
    one_sided = CompatibilityInput(vector={"values": {"family": 1.0}}, interests=set(), dating_goal="")
    silent = CompatibilityInput(vector={}, interests=set(), dating_goal="")
    universe = _universe(one_sided, silent)
    empty = [layer for layer in universe.layers if not layer.has_data]
    assert empty, "the premise: this pair has a band with nothing compared"
    for layer in empty:
        line = next(l for l in universe.story if l.startswith(layer.label))
        assert not _DIGIT.search(line), f"{layer.label} shares {line!r} while having no comparison"
        assert layer.label in line


def test_the_story_prints_no_number_the_map_does_not_already_own() -> None:
    """Every percent in the shared reading has to be a percent the engine put on the wire."""
    a = CompatibilityInput(
        vector={"values": {"family": 1.0, "career": 0.5}, "personality": {"openness": 0.9}},
        interests={"hiking", "cooking"},
        dating_goal="relationship",
    )
    b = CompatibilityInput(
        vector={"values": {"family": 0.3, "career": 0.95}, "personality": {"openness": 0.2}},
        interests={"hiking", "travel"},
        dating_goal="marriage",
    )
    universe = _universe(a, b)
    allowed = {universe.overall_percent} | {layer.score for layer in universe.layers if layer.has_data}
    allowed |= {int(round(layer.weight * 100)) for layer in universe.layers}
    offenders = [
        line
        for line in universe.story
        for number in _PERCENT.findall(line)
        if int(number) not in allowed
    ]
    assert not offenders, f"the story invents percents: {offenders}"


def test_the_heaviest_band_is_told_first() -> None:
    universe = _universe(
        CompatibilityInput(vector={"values": {"family": 1.0}}, **_BOTH),
        CompatibilityInput(vector={"values": {"family": 0.8}}, **_BOTH),
    )
    bands = [layer.label for layer in sorted(universe.layers, key=lambda l: (-l.weight, 0)) if layer.has_data]
    told = [label for label in bands if any(line.startswith(label) for line in universe.story)]
    assert told, "no band line was found in the story at all"
    order = [
        next(i for i, line in enumerate(universe.story) if line.startswith(label)) for label in told
    ]
    assert order == sorted(order), f"bands are told out of weight order: {told}"


def test_the_story_is_the_same_whichever_partner_tells_it() -> None:
    """Pair-global, like the map: the share must not depend on who opened it."""
    a = CompatibilityInput(
        vector={"values": {"family": 1.0, "career": 0.4}}, interests={"hiking"}, dating_goal="marriage"
    )
    b = CompatibilityInput(
        vector={"values": {"family": 0.2, "career": 0.9}}, interests={"travel"}, dating_goal="relationship"
    )
    assert _story(a, b) == _story(b, a)


def test_the_story_sums_the_same_comparisons_the_canvas_drew() -> None:
    """Connection counts per band must be the node objects' own bands, not a recount."""
    a = CompatibilityInput(
        vector={"values": {"family": 1.0, "career": 1.0, "growth": 1.0}}, **_BOTH
    )
    b = CompatibilityInput(
        vector={"values": {"family": 1.0, "career": 0.575, "growth": 0.0}}, **_BOTH
    )
    universe = _universe(a, b)
    layer = next(l for l in universe.layers if l.key == "values")
    line = next(l for l in universe.story if l.startswith(layer.label))
    counts = {
        kind: sum(1 for node in layer.nodes if node.has_data and node.connection == kind)
        for kind in ("harmony", "complementarity", "discussion")
    }
    assert line.count(f"{counts['harmony']} ") >= 1
    assert f"сверено {sum(counts.values())} из {len(layer.nodes)}" in line, line
    assert counts == {"harmony": 1, "complementarity": 1, "discussion": 1}, counts


async def _story_pair(client: AsyncClient):
    anya = await register_and_auth(client, "story_a@befos.app")
    await complete_onboarding(
        client, anya["token"], name="Аня", gender="female", goal="relationship",
        interests=["hiking", "cooking"],
    )
    borya = await register_and_auth(client, "story_b@befos.app")
    await complete_onboarding(
        client, borya["token"], name="Боря", gender="male", goal="marriage",
        interests=["hiking", "travel"],
    )
    await answer_all_questions(client, anya["token"], option_index=0)
    await answer_all_questions(client, borya["token"], option_index=2)
    await client.post(
        f"/api/v1/users/{borya['user_id']}/like", json={}, headers=auth_headers(anya["token"])
    )
    back = await client.post(
        f"/api/v1/users/{anya['user_id']}/like", json={}, headers=auth_headers(borya["token"])
    )
    assert back.status_code == 200, back.text
    return anya["token"], back.json()["match_id"]


async def test_a_real_pair_opens_a_story_with_the_same_numbers_as_its_map(
    client: AsyncClient,
) -> None:
    token, match_id = await _story_pair(client)
    resp = await client.get(f"/api/v1/matches/{match_id}/universe", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    story = payload["story"]
    assert story, "the pair was offered an empty story"
    assert str(payload["overall"]) in story[0], story[0]

    layers = payload["layers"]
    told = [line for line in story[1:]]
    assert len(told) == len(layers), f"{len(told)} band lines for {len(layers)} bands"
    for line, layer in zip(told, [
        l for _, l in sorted(enumerate(layers), key=lambda p: (-p[1]["weight"], p[0]))
    ]):
        assert line.startswith(layer["label"]), f"{line!r} should tell {layer['label']!r}"
        if not layer["has_data"]:
            assert not _DIGIT.search(line), f"an unmeasured band shares a number: {line!r}"
            continue
        assert f"{layer['score']}%" in line, (line, layer["score"])

    names = {node["label"] for layer in layers for node in layer["nodes"] if node["label"] != ""}
    bands = {layer["label"] for layer in layers}
    leaked = [name for name in names - bands if name.lower() in " ".join(story).lower()]
    assert not leaked, f"the story shares axis answers: {leaked}"
    for name in ("Аня", "Боря"):
        assert name not in " ".join(story), f"the story names {name}"
