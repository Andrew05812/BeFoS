"""IDOR sweep: user C must not read or mutate A<->B resources by guessing IDs."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)


async def _ready(client: AsyncClient, email: str, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def _matched_pair(client: AsyncClient) -> tuple[dict, dict, str]:
    a = await _ready(client, "idor_a@befos.app", "Аня", "female")
    b = await _ready(client, "idor_b@befos.app", "Боря", "male")
    await client.post(f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"]))
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    return a, b, mutual.json()["match_id"]


@pytest.fixture
async def idor_setup(client: AsyncClient):
    a, b, match_id = await _matched_pair(client)
    c = await _ready(client, "idor_c@befos.app", "Вика", "female")
    await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": "Привет от Ани"},
        headers=auth_headers(a["token"]),
    )
    return a, b, c, match_id


async def test_outsider_cannot_read_match_chat_history(client: AsyncClient, idor_setup):
    _, _, c, match_id = idor_setup
    resp = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(c["token"])
    )
    assert resp.status_code in (403, 404)


async def test_outsider_cannot_send_into_match_chat(client: AsyncClient, idor_setup):
    _, _, c, match_id = idor_setup
    resp = await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": "вторжение"},
        headers=auth_headers(c["token"]),
    )
    assert resp.status_code in (403, 404)
    history = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(c["token"])
    )
    assert history.status_code in (403, 404)


async def test_outsider_cannot_mark_read_or_open_compatibility(client: AsyncClient, idor_setup):
    _, _, c, match_id = idor_setup
    read = await client.post(
        f"/api/v1/matches/{match_id}/read", headers=auth_headers(c["token"])
    )
    assert read.status_code in (403, 404)
    compat = await client.get(
        f"/api/v1/matches/{match_id}/compatibility", headers=auth_headers(c["token"])
    )
    assert compat.status_code in (403, 404)


async def test_outsider_cannot_read_match_detail_or_recommendations(client: AsyncClient, idor_setup):
    _, _, c, match_id = idor_setup
    detail = await client.get(f"/api/v1/matches/{match_id}", headers=auth_headers(c["token"]))
    assert detail.status_code == 404
    recs = await client.get(
        f"/api/v1/matches/{match_id}/recommendations", headers=auth_headers(c["token"])
    )
    assert recs.status_code in (403, 404)


async def test_outsider_cannot_select_recommendation_for_pair(client: AsyncClient, idor_setup):
    _, _, c, match_id = idor_setup
    resp = await client.post(
        f"/api/v1/matches/{match_id}/recommendations/1/select",
        headers=auth_headers(c["token"]),
    )
    assert resp.status_code in (403, 404)


async def test_partners_still_have_access(client: AsyncClient, idor_setup):
    a, _, _, match_id = idor_setup
    history = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(a["token"])
    )
    assert history.status_code == 200
    assert history.json()["messages"][0]["body"] == "Привет от Ани"
