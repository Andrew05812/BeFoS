"""An answer nobody gave cannot be a difference between two people.

The engine states its own rule for a category with nothing to compare on (``NEUTRAL_SCORE`` in
``app/compatibility/engine.py``): an incomplete profile is neither rewarded nor punished. The
trait path honours it, the goals path honours it, and the interests path did not — one silent
person put the category at ``0.0`` with ``has_data=True``, while two silent people put it at the
neutral 0.5.

Measured on the engine before the fix, with the vectors below and one goal for both people, so
that only the two interest sets vary:

    both name the same interests    overall 100   interests 100
    one of them names none          overall  85   interests   0   «Мало общих интересов»
    both name none                  overall  92   interests  50
    both speak, nothing in common   overall  85   interests   0   «Мало общих интересов»

The middle pair of rows is the defect: skipping the interest step cost the *other* person seven
points, and the pair page described somebody's silence as a disagreement. The last row is the
part that must stay: two spoken sets with nothing in common are information, and information is
allowed to cost.
"""

from __future__ import annotations

from httpx import AsyncClient

from app.compatibility.engine import CompatibilityInput, compute_compatibility
from app.compatibility.explanation import build_explanation

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

_VEC = {
    "values": {"honesty": 0.8, "family": 0.6},
    "personality": {"warm": 0.7, "open": 0.5},
    "communication": {"direct": 0.6, "listen": 0.6},
    "lifestyle": {"sleep": 0.4, "sport": 0.5},
    "leisure": {"outdoors": 0.5, "culture": 0.5},
    "goals_trait": {"ambition": 0.6},
}


def _person(interests: set[str]) -> CompatibilityInput:
    return CompatibilityInput(vector=dict(_VEC), interests=interests, dating_goal="relationship")


def _interests_of(a: CompatibilityInput, b: CompatibilityInput):
    return compute_compatibility(a, b).category("interests")


def test_silence_on_one_side_neutralises_the_category() -> None:
    """One silent person has to read like both silent, not like a disagreement."""
    one_silent = compute_compatibility(_person({"hiking", "cooking"}), _person(set()))
    both_silent = compute_compatibility(_person(set()), _person(set()))

    assert one_silent.category("interests").score == 0.5, (
        "a person who named no interests is being scored on a subject nobody spoke about: "
        f"interests read {one_silent.category('interests').score:.2f}"
    )
    assert not one_silent.category("interests").has_data, (
        "the category reports data it does not have, so its weight keeps applying to nothing"
    )
    assert one_silent.overall == both_silent.overall, (
        "skipping the interest step costs the partner points: "
        f"one silent {one_silent.overall_percent} against both silent {both_silent.overall_percent}"
    )


def test_two_spoken_sets_with_nothing_in_common_still_cost() -> None:
    """Neutrality belongs to absence of information, not to absence of agreement."""
    result = compute_compatibility(_person({"hiking", "cooking"}), _person({"chess", "opera"}))
    category = result.category("interests")
    assert category.score == 0.0, f"two disjoint answers stopped being a difference: {category.score}"
    assert category.has_data


def test_the_explanation_says_nothing_about_interests_nobody_named() -> None:
    a, silent = _person({"hiking", "cooking"}), _person(set())
    result = compute_compatibility(a, silent)
    explanation = build_explanation(a, silent, result)
    claims = [i.text for i in explanation.differences if i.category == "interests"]
    assert claims == [], f"the page claims a difference on an unanswered subject: {claims}"
    assert explanation.shared_interests == []

    spoken = _person({"chess", "opera"})
    other = build_explanation(_person({"hiking", "cooking"}), spoken, compute_compatibility(_person({"hiking", "cooking"}), spoken))
    assert [i.text for i in other.differences if i.category == "interests"] == [
        "Мало общих интересов"
    ], "the difference two people did answer is no longer explained"


async def _account(client: AsyncClient, email: str, *, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def _clear_interests(client: AsyncClient, token: str) -> None:
    resp = await client.patch("/api/v1/users/me", json={"interests": []}, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text


async def _percentages(client: AsyncClient, token: str, match_id: str) -> tuple[int, int]:
    """The pair's overall percent and its interests percent, from one read of the screen."""
    resp = await client.get(
        f"/api/v1/matches/{match_id}/compatibility", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    category = next(c for c in body["categories"] if c["category"] == "interests")
    return int(body["overall"]), int(category["score"])


async def test_a_silent_partner_is_not_shown_as_a_disagreement_on_the_pair_page(
    client: AsyncClient,
) -> None:
    """The screen a person actually reads, over the two accounts the app can build."""
    anya = await _account(client, "silent_a@befos.app", name="Аня", gender="female")
    borya = await _account(client, "silent_b@befos.app", name="Боря", gender="male")
    await client.post(
        f"/api/v1/users/{borya['user_id']}/like", json={}, headers=auth_headers(anya["token"])
    )
    back = await client.post(
        f"/api/v1/users/{anya['user_id']}/like", json={}, headers=auth_headers(borya["token"])
    )
    assert back.status_code == 200, back.text
    match_id = back.json()["match_id"]

    both_named = await _percentages(client, anya["token"], match_id)
    assert both_named[1] == 100, f"the fixture pair answered the step identically: {both_named}"

    await _clear_interests(client, anya["token"])
    one_silent = await _percentages(client, anya["token"], match_id)
    assert one_silent[1] == 50, (
        f"Аня named nothing, so the screen reads her interests as {one_silent[1]}% shared "
        "with nobody"
    )

    await _clear_interests(client, borya["token"])
    both_silent = await _percentages(client, anya["token"], match_id)
    assert one_silent == both_silent, (
        "Боря clearing his own interests changed what Аня is scored on: "
        f"one silent {one_silent} against both silent {both_silent}"
    )

    # And the number the match list stores moved with the screen, not against it.
    listing = await client.get("/api/v1/matches", headers=auth_headers(anya["token"]))
    assert listing.status_code == 200, listing.text
    row = next(m for m in listing.json()["matches"] if m["match_id"] == match_id)
    assert row["compatibility"] == both_silent[0], (
        f"the list promises {row['compatibility']}, the pair page says {both_silent[0]}"
    )

    catalog = await client.get("/api/v1/users/interests", headers=auth_headers(anya["token"]))
    assert catalog.status_code == 200, catalog.text
    items = catalog.json()
    slugs = [i["slug"] for i in (items if isinstance(items, list) else items["interests"])]
    await client.patch(
        "/api/v1/users/me", json={"interests": slugs[:3]}, headers=auth_headers(anya["token"])
    )
    await client.patch(
        "/api/v1/users/me", json={"interests": slugs[3:6]}, headers=auth_headers(borya["token"])
    )
    disagree = await _percentages(client, anya["token"], match_id)
    assert disagree[1] == 0, (
        "two people who named different interests are no longer a difference: "
        f"{disagree}"
    )
