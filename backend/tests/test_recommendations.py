from __future__ import annotations

import pytest
from httpx import AsyncClient

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth
from app.recommendations.engine import ActivitySignal, UserSignal, recommend, score_activity


def _act(aid: int, slug: str, interests: list[str], cities=None, energy=0.5, social=0.5) -> ActivitySignal:
    return ActivitySignal(
        activity_id=aid, slug=slug, title=slug, category="x",
        interests=interests, cities=cities or [], energy=energy, social=social,
    )


def test_shared_interests_boost_score():
    a = UserSignal(interests={"photography", "travel"}, city="Москва", dating_goal="relationship")
    b = UserSignal(interests={"photography", "travel"}, city="Москва", dating_goal="relationship")
    photo_walk = _act(1, "photo_walk", ["photography", "travel"])
    gym = _act(2, "gym", ["gym", "running"])
    s1 = score_activity(photo_walk, a, b)
    s2 = score_activity(gym, a, b)
    assert s1.score > s2.score
    assert any("фотограф" in r.lower() or "travel" in r.lower() or "интерес" in r.lower() for r in s1.reasons)


def test_interest_reasons_use_human_titles():
    a = UserSignal(
        interests={"photography"}, city="Москва", dating_goal="relationship",
        interest_titles={"photography": "Фотография"},
    )
    b = UserSignal(
        interests={"photography"}, city="Москва", dating_goal="relationship",
        interest_titles={"photography": "Фотография"},
    )
    scored = score_activity(_act(1, "photo_walk", ["photography"]), a, b)
    assert any("Фотография" in r for r in scored.reasons)
    assert not any("photography" in r for r in scored.reasons)


def test_interest_reasons_fall_back_to_slug_without_titles():
    a = UserSignal(interests={"photography"}, city="Москва", dating_goal="relationship")
    b = UserSignal(interests={"photography"}, city="Москва", dating_goal="relationship")
    scored = score_activity(_act(1, "photo_walk", ["photography"]), a, b)
    assert any("photography" in r for r in scored.reasons)


def test_city_specific_activity_scores_zero_when_no_overlap():
    a = UserSignal(interests={"coffee"}, city="Москва", dating_goal="relationship")
    b = UserSignal(interests={"coffee"}, city="Москва", dating_goal="relationship")
    far = _act(3, "ski", ["skiing"], cities=["Сочи"])
    local = _act(4, "cafe", ["coffee"], cities=["Москва"])
    assert score_activity(far, a, b).score < score_activity(local, a, b).score


def test_recommend_is_deterministic_and_sorted():
    a = UserSignal(interests={"photography", "coffee"}, city="Москва", dating_goal="relationship")
    b = UserSignal(interests={"photography", "coffee"}, city="Москва", dating_goal="relationship")
    acts = [
        _act(1, "photo_walk", ["photography", "travel"]),
        _act(2, "coffee_walk", ["coffee"]),
        _act(3, "gym", ["gym"]),
    ]
    r1 = recommend(acts, a, b, top_n=3)
    r2 = recommend(acts, a, b, top_n=3)
    assert [x.activity_id for x in r1] == [x.activity_id for x in r2]
    scores = [x.score for x in r1]
    assert scores == sorted(scores, reverse=True)


def test_scores_in_range():
    a = UserSignal(interests={"x"}, city="Казань", dating_goal="casual")
    b = UserSignal(interests={"y"}, city="Москва", dating_goal="marriage")
    acts = [_act(i, f"a{i}", ["x", "y", "z"], cities=["Москва"]) for i in range(5)]
    for s in recommend(acts, a, b, top_n=5):
        assert 0.0 <= s.score <= 1.0
        assert 0 <= s.percent <= 100


def test_top_n_limits_results():
    a = UserSignal(interests={"x"}, city="", dating_goal="relationship")
    b = UserSignal(interests={"x"}, city="", dating_goal="relationship")
    acts = [_act(i, f"a{i}", ["x"]) for i in range(10)]
    assert len(recommend(acts, a, b, top_n=3)) == 3


# ---------- against the API ----------


async def _ready(client: AsyncClient, email: str, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


@pytest.fixture
async def pair(client: AsyncClient):
    a = await _ready(client, "rec_a@befos.app", "Аня", "female")
    b = await _ready(client, "rec_b@befos.app", "Боря", "male")
    await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    assert mutual.status_code in (200, 201), mutual.text
    return a, b, mutual.json()["match_id"]


async def test_an_answer_of_0_to_100_is_promised_not_hoped_for(client: AsyncClient, pair):
    a, _, match_id = pair
    resp = await client.get(
        f"/api/v1/matches/{match_id}/recommendations", headers=auth_headers(a["token"])
    )
    assert resp.status_code == 200, resp.text
    cards = resp.json()["recommendations"]
    assert cards, "the catalogue should offer this pair something"
    for card in cards:
        assert 0 <= card["score"] <= 100


async def test_selecting_an_activity_that_is_not_in_the_catalogue_is_refused(
    client: AsyncClient, pair
):
    # The id comes from the request url. Before the check it reached a foreign key and
    # the database answered with an integrity error, so the client got a 500 for asking
    # about an activity that never existed.
    a, _, match_id = pair
    resp = await client.post(
        f"/api/v1/matches/{match_id}/recommendations/999999/select",
        headers=auth_headers(a["token"]),
    )
    assert resp.status_code == 404, f"{resp.status_code}: {resp.text[:200]}"


async def test_recommendations_follow_a_partner_who_changed_their_interests(
    client: AsyncClient, pair
):
    a, _, match_id = pair
    first = await client.get(
        f"/api/v1/matches/{match_id}/recommendations", headers=auth_headers(a["token"])
    )
    assert first.status_code == 200, first.text
    shared = [
        r
        for card in first.json()["recommendations"]
        for r in card["reasons"]
        if "нтерес" in r
    ]
    assert shared, "the fixture pair shares interests, so a card should say so"

    edited = await client.patch(
        "/api/v1/users/me", json={"interests": []}, headers=auth_headers(a["token"])
    )
    assert edited.status_code == 200, edited.text

    second = await client.get(
        f"/api/v1/matches/{match_id}/recommendations", headers=auth_headers(a["token"])
    )
    assert second.status_code == 200, second.text
    stale = [
        r
        for card in second.json()["recommendations"]
        for r in card["reasons"]
        if "нтерес" in r
    ]
    assert stale == [], f"nobody shares interests any more, but the page still says: {stale}"

