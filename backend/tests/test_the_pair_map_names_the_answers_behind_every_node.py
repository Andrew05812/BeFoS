"""The pair map must name the answers behind every node and never dress a missing answer as a meeting.

The compatibility screen answers one number per band. The map answers a different question: which
answer of which person produced that number. That makes a new transport surface, not a new engine —
every percent on the map must be the percent the pair already reads from ``/compatibility``, every
band of every node must follow from the two values the node itself shows, and every node whose
comparison nobody took part in must say so as ``unknown``. The rule that this file exists to hold:
«не показывать неизвестное как совпадение» — an unanswered trait, a one-sided interest and a goal
the other person never named are absences of data, and the map may not paint an absence as a
meeting, a difference, or a number a human landed on.

Red state on the tree before the route existed: every read of ``/api/v1/matches/{id}/universe``
answered 404, and the two compute-level checks raised ``ModuleNotFoundError`` for
``app.compatibility.universe``.
"""

from __future__ import annotations

from httpx import AsyncClient

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

_TRAIT_CATEGORIES = ("values", "personality", "communication", "lifestyle", "leisure")
_CONNECTIONS = {"harmony", "complementarity", "discussion", "unknown"}


async def _pair(
    client: AsyncClient,
    *,
    anya_test: bool,
    borya_test: bool,
    anya_interests: list[str] | None = None,
    borya_interests: list[str] | None = None,
    anya_goal: str = "relationship",
    borya_goal: str = "relationship",
):
    anya = await register_and_auth(client, "universe_a@befos.app")
    await complete_onboarding(
        client, anya["token"], name="Аня", gender="female",
        goal=anya_goal, interests=anya_interests,
    )
    borya = await register_and_auth(client, "universe_b@befos.app")
    await complete_onboarding(
        client, borya["token"], name="Боря", gender="male",
        goal=borya_goal, interests=borya_interests,
    )
    if anya_test:
        await answer_all_questions(client, anya["token"])
    if borya_test:
        await answer_all_questions(client, borya["token"])

    await client.post(
        f"/api/v1/users/{borya['user_id']}/like", json={}, headers=auth_headers(anya["token"])
    )
    back = await client.post(
        f"/api/v1/users/{anya['user_id']}/like", json={}, headers=auth_headers(borya["token"])
    )
    assert back.status_code == 200, back.text
    return anya, borya, back.json()["match_id"]


async def _universe(client: AsyncClient, token: str, match_id: str) -> dict:
    resp = await client.get(
        f"/api/v1/matches/{match_id}/universe", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _layers(body: dict) -> dict[str, dict]:
    return {layer["category"]: layer for layer in body["layers"]}


async def test_the_map_answers_both_owners_and_refuses_a_stranger(client: AsyncClient) -> None:
    anya, borya, match_id = await _pair(client, anya_test=True, borya_test=True)
    assert (await _universe(client, anya["token"], match_id))["overall"] is not None
    assert (await _universe(client, borya["token"], match_id))["overall"] is not None

    stranger = await register_and_auth(client, "universe_s@befos.app")
    await complete_onboarding(client, stranger["token"], name="Саша", gender="other")
    resp = await client.get(
        f"/api/v1/matches/{match_id}/universe", headers=auth_headers(stranger["token"])
    )
    assert resp.status_code == 404, (
        "a person outside the pair read the map of two other worlds"
    )


async def test_the_map_carries_the_same_bands_the_compatibility_screen_already_shows(
    client: AsyncClient,
) -> None:
    """No second engine: percent, weight and the data flag travel from the same result."""
    anya, _borya, match_id = await _pair(client, anya_test=True, borya_test=False)
    compat = await client.get(
        f"/api/v1/matches/{match_id}/compatibility", headers=auth_headers(anya["token"])
    )
    assert compat.status_code == 200, compat.text
    bands = {c["category"]: c for c in compat.json()["categories"]}
    layers = _layers(await _universe(client, anya["token"], match_id))

    assert sorted(layers) == sorted(bands), "the map invented or lost a layer"
    for key, band in bands.items():
        assert layers[key]["score"] == band["score"], f"{key}: the map moved the percent"
        assert layers[key]["weight"] == band["weight"], f"{key}: the map moved the weight"
        assert layers[key]["has_data"] == band["has_data"], f"{key}: the flag disagrees"
    assert (await _universe(client, anya["token"], match_id))["overall"] == compat.json()["overall"]


async def test_every_compared_trait_node_shows_both_values_and_its_band_follows_them(
    client: AsyncClient,
) -> None:
    anya, _borya, match_id = await _pair(client, anya_test=True, borya_test=True)
    layers = _layers(await _universe(client, anya["token"], match_id))
    seen_compared = 0
    for key in _TRAIT_CATEGORIES:
        for node in layers[key]["nodes"]:
            assert node["connection"] in _CONNECTIONS, f"{key}/{node['key']}: unknown band word"
            if not node["has_data"]:
                continue
            seen_compared += 1
            va, vb = node["a_value"], node["b_value"]
            assert va is not None and vb is not None, (
                f"{key}/{node['key']} compared without showing both sides"
            )
            assert 0.0 <= va <= 1.0 and 0.0 <= vb <= 1.0
            sim = 1.0 - abs(va - vb)
            expected = (
                "harmony" if sim >= 0.75
                else "discussion" if sim <= 0.40
                else "complementarity"
            )
            assert node["connection"] == expected, (
                f"{key}/{node['key']} shows {va} against {vb} (similarity {sim:.3f}) "
                f"and calls it {node['connection']}, not {expected}"
            )
    assert seen_compared > 0, "two people who took the questionnaire share no node at all"


async def test_a_trait_only_one_person_named_stays_unknown_not_a_meeting(
    client: AsyncClient,
) -> None:
    anya, _borya, match_id = await _pair(client, anya_test=True, borya_test=False)
    layers = _layers(await _universe(client, anya["token"], match_id))
    for key in _TRAIT_CATEGORIES:
        layer = layers[key]
        assert layer["has_data"] is False
        for node in layer["nodes"]:
            assert node["connection"] == "unknown", (
                f"{key}/{node['key']}: the map drew a meeting where only one world spoke"
            )
        named = [n for n in layer["nodes"] if n["a_value"] is not None or n["b_value"] is not None]
        assert named, f"{key}: the person who answered lost their own nodes"


async def test_shared_interests_meet_and_a_one_sided_interest_is_unknown(
    client: AsyncClient,
) -> None:
    anya, _borya, match_id = await _pair(
        client,
        anya_test=False,
        borya_test=False,
        anya_interests=["hiking", "cooking", "cinema"],
        borya_interests=["hiking", "cooking", "board_games"],
    )
    items = await client.get("/api/v1/users/interests", headers=auth_headers(anya["token"]))
    assert items.status_code == 200, items.text
    catalog = items.json()
    slugs = catalog if isinstance(catalog, list) else catalog.get("interests", [])
    names = {i["slug"]: i["name"] for i in slugs}
    layer = _layers(await _universe(client, anya["token"], match_id))["interests"]
    by_slug = {n["key"]: n for n in layer["nodes"]}

    assert set(by_slug) == {"hiking", "cooking", "cinema", "board_games"}, (
        "the interests layer lost a world: nobody named board games and it vanished"
    )
    for shared in ("hiking", "cooking"):
        assert by_slug[shared]["connection"] == "harmony"
        assert by_slug[shared]["label"] == names[shared], (
            "a node a person must read names the slug, not the catalogue title"
        )
    for one_sided in ("cinema", "board_games"):
        assert by_slug[one_sided]["connection"] == "unknown", (
            f"{one_sided}: one person named it, the map read it as a pair"
        )


async def test_the_goal_node_band_and_percent_come_from_the_one_matrix(
    client: AsyncClient,
) -> None:
    from app.compatibility.traits import goal_compatibility

    anya, _borya, match_id = await _pair(
        client, anya_test=False, borya_test=False, anya_goal="relationship", borya_goal="marriage"
    )
    layer = _layers(await _universe(client, anya["token"], match_id))["goals"]
    assert layer["has_data"] is True
    assert len(layer["nodes"]) == 1
    node = layer["nodes"][0]
    cell = goal_compatibility("relationship", "marriage")
    assert layer["score"] == round(cell * 100), "the layer number left the matrix cell"
    expected = (
        "harmony" if cell >= 0.75 else "discussion" if cell <= 0.40 else "complementarity"
    )
    assert node["connection"] == expected, (
        f"goal cell {cell} drawn as {node['connection']}, not {expected}"
    )


async def test_an_unanswered_goal_is_unknown_never_a_coincidence() -> None:
    from app.compatibility.engine import CompatibilityInput, compute_compatibility
    from app.compatibility.universe import build_universe

    named = CompatibilityInput(vector={}, interests={"hiking"}, dating_goal="marriage")
    silent = CompatibilityInput(vector={}, interests={"hiking"}, dating_goal="")
    result = compute_compatibility(named, silent)
    layer = next(l for l in build_universe(named, silent, result).layers if l.key == "goals")
    assert layer.has_data is False
    assert layer.nodes[0].connection == "unknown", (
        "a goal only one person named was drawn as a meeting"
    )


def _vec(**categories: dict[str, float]) -> dict:
    return dict(categories)


async def test_coverage_and_percent_stay_two_numbers_on_the_same_layer() -> None:
    from app.compatibility.engine import CompatibilityInput, compute_compatibility
    from app.compatibility.universe import build_universe

    a = CompatibilityInput(
        vector=_vec(values={"family": 0.8, "career": 0.6, "growth": 0.5, "stability": 0.5,
                            "adventure": 0.5}),
        interests={"hiking"}, dating_goal="relationship",
    )
    b = CompatibilityInput(
        vector=_vec(values={"family": 0.7, "career": 0.6}),
        interests={"hiking"}, dating_goal="relationship",
    )
    result = compute_compatibility(a, b)
    layer = next(l for l in build_universe(a, b, result).layers if l.key == "values")
    assert layer.has_data is True, "two shared traits are data"
    assert 0.0 < layer.coverage < 1.0, (
        f"three of five taxonomy traits were named by both, coverage says {layer.coverage}"
    )


async def test_both_owners_read_one_pair_as_the_same_document(client: AsyncClient) -> None:
    anya, borya, match_id = await _pair(client, anya_test=True, borya_test=True)
    hers = await _universe(client, anya["token"], match_id)
    his = await _universe(client, borya["token"], match_id)
    assert hers == his, "the two sides of one pair were fed requester-first: two worlds, two maps"
    again = await _universe(client, anya["token"], match_id)
    assert again == hers, "two reads of one pair moved the map"
    assert isinstance(hers["engine_version"], int) and hers["engine_version"] >= 1
