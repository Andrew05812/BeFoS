"""End-to-end API integration tests against a real PostgreSQL test database.

Covers auth, onboarding/profile, the test engine, compatibility, discovery,
like -> match, chat, recommendations and safety.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)


async def _make_ready_user(client: AsyncClient, email: str, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


# ---------- Auth ----------
async def test_register_login_me_refresh_logout(client: AsyncClient):
    creds = await register_and_auth(client, "auth1@befos.app")

    me = await client.get("/api/v1/users/me", headers=auth_headers(creds["token"]))
    assert me.status_code == 200
    assert me.json()["user_id"] == creds["user_id"]

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "auth1@befos.app", "password": "Test12345"},
    )
    assert login.status_code == 200
    assert "access_token" in login.json()["tokens"]

    refresh = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": creds["refresh"]}
    )
    assert refresh.status_code == 200
    new_tokens = refresh.json()
    assert new_tokens["access_token"]

    logout = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": new_tokens["refresh_token"]},
        headers=auth_headers(new_tokens["access_token"]),
    )
    assert logout.status_code in (200, 204)


async def test_register_requires_password_confirm(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "bad@befos.app", "password": "Test12345"},
    )
    assert resp.status_code == 422


async def test_register_duplicate_email_conflicts(client: AsyncClient):
    await register_and_auth(client, "dup@befos.app")
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dup@befos.app",
            "password": "Test12345",
            "password_confirm": "Test12345",
        },
    )
    assert resp.status_code == 409


async def test_login_wrong_password_rejected(client: AsyncClient):
    await register_and_auth(client, "wrongpw@befos.app")
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpw@befos.app", "password": "NotThePassword"},
    )
    assert resp.status_code == 401


async def test_protected_route_requires_token(client: AsyncClient):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401


# ---------- Onboarding / Profile ----------
async def test_onboarding_sets_profile_and_age(client: AsyncClient):
    creds = await register_and_auth(client, "onb@befos.app")
    await complete_onboarding(client, creds["token"], name="Ольга", city="Казань")

    me = await client.get("/api/v1/users/me", headers=auth_headers(creds["token"]))
    assert me.status_code == 200
    body = me.json()
    assert body["name"] == "Ольга"
    assert body["city"] == "Казань"
    assert body["age"] == 30  # born 1996-05-10, current year 2026
    assert len(body["interests"]) == 6


async def test_profile_patch_updates_fields(client: AsyncClient):
    creds = await register_and_auth(client, "patch@befos.app")
    await complete_onboarding(client, creds["token"])

    resp = await client.patch(
        "/api/v1/users/me",
        json={"about": "Обновлённое описание", "city": "Санкт-Петербург"},
        headers=auth_headers(creds["token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["city"] == "Санкт-Петербург"
    assert resp.json()["about"] == "Обновлённое описание"


# ---------- Test engine ----------
async def test_test_flow_progress_and_completion(client: AsyncClient):
    creds = await register_and_auth(client, "tester@befos.app")
    await complete_onboarding(client, creds["token"])

    tests = await client.get("/api/v1/tests", headers=auth_headers(creds["token"]))
    assert tests.status_code == 200
    assert tests.json()["total"] == 21
    assert tests.json()["answered"] == 0

    await answer_all_questions(client, creds["token"])

    progress = await client.get(
        "/api/v1/tests/progress", headers=auth_headers(creds["token"])
    )
    body = progress.json()
    assert body["percent"] == 100
    assert body["completed"] is True


# ---------- Discovery ----------
async def test_discovery_excludes_self_and_returns_cards(client: AsyncClient):
    a = await _make_ready_user(client, "disc_a@befos.app", "Аня", "female")
    await _make_ready_user(client, "disc_b@befos.app", "Боря", "male")

    resp = await client.get(
        "/api/v1/discover?limit=10", headers=auth_headers(a["token"])
    )
    assert resp.status_code == 200
    cards = resp.json()
    cards = cards if isinstance(cards, list) else cards.get("items", [])
    assert len(cards) >= 1
    ids = {c.get("user_id") or c.get("id") for c in cards}
    assert a["user_id"] not in ids
    for card in cards:
        assert 0 <= card["compatibility"] <= 100


# ---------- Like -> Match ----------
async def test_mutual_like_creates_match(client: AsyncClient):
    a = await _make_ready_user(client, "m_a@befos.app", "Аня", "female")
    b = await _make_ready_user(client, "m_b@befos.app", "Боря", "male")

    first = await client.post(
        f"/api/v1/users/{b['user_id']}/like",
        json={},
        headers=auth_headers(a["token"]),
    )
    assert first.status_code == 200
    assert first.json()["match"] is False

    second = await client.post(
        f"/api/v1/users/{a['user_id']}/like",
        json={},
        headers=auth_headers(b["token"]),
    )
    assert second.status_code == 200
    assert second.json()["match"] is True
    match_id = second.json()["match_id"]
    assert match_id

    matches = await client.get("/api/v1/matches", headers=auth_headers(a["token"]))
    assert matches.status_code == 200
    listed = matches.json()["matches"]
    assert any(m["match_id"] == match_id for m in listed)


async def test_pass_does_not_create_match(client: AsyncClient):
    a = await _make_ready_user(client, "p_a@befos.app", "Аня", "female")
    b = await _make_ready_user(client, "p_b@befos.app", "Боря", "male")

    resp = await client.post(
        f"/api/v1/users/{b['user_id']}/pass", json={}, headers=auth_headers(a["token"])
    )
    assert resp.status_code == 200
    matches = await client.get("/api/v1/matches", headers=auth_headers(a["token"]))
    assert matches.json()["matches"] == []


# ---------- Compatibility ----------
async def test_match_compatibility_is_explained_and_ranged(client: AsyncClient):
    a = await _make_ready_user(client, "c_a@befos.app", "Аня", "female")
    b = await _make_ready_user(client, "c_b@befos.app", "Боря", "male")
    await client.post(f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"]))
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    match_id = mutual.json()["match_id"]

    resp = await client.get(
        f"/api/v1/matches/{match_id}/compatibility", headers=auth_headers(a["token"])
    )
    assert resp.status_code == 200
    body = resp.json()
    assert 0 <= body["overall"] <= 100
    weights = sum(c["weight"] for c in body["categories"])
    assert abs(weights - 1.0) < 1e-6
    assert isinstance(body["categories"], list) and len(body["categories"]) == 7


async def test_compatibility_is_deterministic(client: AsyncClient):
    a = await _make_ready_user(client, "d_a@befos.app", "Аня", "female")
    b = await _make_ready_user(client, "d_b@befos.app", "Боря", "male")
    await client.post(f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"]))
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    match_id = mutual.json()["match_id"]

    r1 = await client.get(
        f"/api/v1/matches/{match_id}/compatibility", headers=auth_headers(a["token"])
    )
    r2 = await client.get(
        f"/api/v1/matches/{match_id}/compatibility", headers=auth_headers(a["token"])
    )
    assert r1.json()["overall"] == r2.json()["overall"]
    assert r1.json()["categories"] == r2.json()["categories"]


# ---------- Chat ----------
async def test_chat_send_and_history(client: AsyncClient):
    a = await _make_ready_user(client, "ch_a@befos.app", "Аня", "female")
    b = await _make_ready_user(client, "ch_b@befos.app", "Боря", "male")
    await client.post(f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"]))
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    match_id = mutual.json()["match_id"]

    sent = await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": "Привет из интеграционного теста!"},
        headers=auth_headers(a["token"]),
    )
    assert sent.status_code == 201
    assert sent.json()["body"] == "Привет из интеграционного теста!"
    # A receipt the partner never sent would tell A "прочитано" before anyone opened
    # the chat — the send response must report the message as unread.
    assert sent.json()["is_read"] is False

    history = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(b["token"])
    )
    assert history.status_code == 200
    messages = history.json()["messages"]
    assert any(m["body"] == "Привет из интеграционного теста!" for m in messages)

    after_read = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(a["token"])
    )
    own = [m for m in after_read.json()["messages"] if m["is_own"]]
    assert own and all(m["is_read"] for m in own)


async def test_a_message_past_the_limit_is_refused_with_a_reason(client: AsyncClient):
    """The client shows this sentence verbatim to someone whose text was too long, so a
    generic payload error is the difference between advice and a dead end."""
    a = await _make_ready_user(client, "long_a@befos.app", "Лена", "female")
    b = await _make_ready_user(client, "long_b@befos.app", "Лёва", "male")
    await client.post(f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"]))
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    match_id = mutual.json()["match_id"]

    longest = await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": "а" * 4000},
        headers=auth_headers(a["token"]),
    )
    assert longest.status_code == 201, longest.text

    too_long = await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": "а" * 4001},
        headers=auth_headers(a["token"]),
    )
    assert too_long.status_code == 422
    assert too_long.json()["error"]["message"] == "Message is too long."

    history = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(b["token"])
    )
    bodies = [m["body"] for m in history.json()["messages"]]
    assert all(len(x) <= 4000 for x in bodies), "the refused message must not be stored"


async def test_chat_send_and_read_broadcast_to_match_socket(client: AsyncClient, monkeypatch):
    from app.api.v1 import chat as chat_api

    events: list[dict] = []
    options: list[dict] = []

    async def fake_broadcast(match_id: str, payload: dict, **send_options: object) -> None:
        events.append(payload)
        options.append(send_options)

    monkeypatch.setattr(chat_api.manager, "broadcast_to_match", fake_broadcast)

    a = await _make_ready_user(client, "ws_a@befos.app", "Аня", "female")
    b = await _make_ready_user(client, "ws_b@befos.app", "Боря", "male")
    await client.post(f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"]))
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    match_id = mutual.json()["match_id"]

    sent = await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": "Реалтайм без перезагрузки"},
        headers=auth_headers(a["token"]),
    )
    assert sent.status_code == 201
    message_events = [p for p in events if p["type"] == "message"]
    assert len(message_events) == 1
    assert message_events[0]["body"] == "Реалтайм без перезагрузки"
    assert message_events[0]["match_id"] == match_id
    assert message_events[0]["sender_id"] == a["user_id"]

    events.clear()
    read = await client.post(f"/api/v1/matches/{match_id}/read", headers=auth_headers(b["token"]))
    assert read.status_code == 200
    read_events = [p for p in events if p["type"] == "read"]
    assert len(read_events) == 1
    assert read_events[0]["user_id"] == b["user_id"]
    # The REST receipt must skip the actor's own sockets, otherwise B's client marks
    # B's messages read the moment B opens the chat.
    assert str(options[-1]["exclude_user"]) == b["user_id"]


async def test_chat_requires_membership(client: AsyncClient):
    a = await _make_ready_user(client, "mem_a@befos.app", "Аня", "female")
    b = await _make_ready_user(client, "mem_b@befos.app", "Боря", "male")
    outsider = await _make_ready_user(client, "mem_c@befos.app", "Вася", "male")
    await client.post(f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"]))
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    match_id = mutual.json()["match_id"]

    resp = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(outsider["token"])
    )
    assert resp.status_code in (403, 404)


# ---------- Recommendations ----------
async def test_recommendations_are_scored_and_explained(client: AsyncClient):
    a = await _make_ready_user(client, "r_a@befos.app", "Аня", "female")
    b = await _make_ready_user(client, "r_b@befos.app", "Боря", "male")
    await client.post(f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"]))
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    match_id = mutual.json()["match_id"]

    resp = await client.get(
        f"/api/v1/matches/{match_id}/recommendations", headers=auth_headers(a["token"])
    )
    assert resp.status_code == 200
    recs = resp.json()["recommendations"]
    assert len(recs) >= 1
    scores = [r["score"] for r in recs]
    assert scores == sorted(scores, reverse=True)
    assert recs[0]["reasons"]
    assert recs[0]["activity"]["title"]


# ---------- Safety ----------
async def test_block_hides_user_from_discovery(client: AsyncClient):
    a = await _make_ready_user(client, "s_a@befos.app", "Аня", "female")
    b = await _make_ready_user(client, "s_b@befos.app", "Боря", "male")

    block = await client.post(
        f"/api/v1/users/{b['user_id']}/block", json={}, headers=auth_headers(a["token"])
    )
    assert block.status_code == 200

    resp = await client.get(
        "/api/v1/discover?limit=50", headers=auth_headers(a["token"])
    )
    cards = resp.json()
    cards = cards if isinstance(cards, list) else cards.get("items", [])
    ids = {c.get("user_id") or c.get("id") for c in cards}
    assert b["user_id"] not in ids


async def test_report_is_accepted(client: AsyncClient):
    a = await _make_ready_user(client, "rep_a@befos.app", "Аня", "female")
    b = await _make_ready_user(client, "rep_b@befos.app", "Боря", "male")
    resp = await client.post(
        f"/api/v1/users/{b['user_id']}/report",
        json={"reason": "spam", "details": "Навязчивое поведение"},
        headers=auth_headers(a["token"]),
    )
    assert resp.status_code == 200


async def test_delete_account_revokes_access(client: AsyncClient):
    creds = await register_and_auth(client, "del@befos.app")
    await complete_onboarding(client, creds["token"])

    resp = await client.delete("/api/v1/users/me", headers=auth_headers(creds["token"]))
    assert resp.status_code in (200, 204)

    me = await client.get("/api/v1/users/me", headers=auth_headers(creds["token"]))
    assert me.status_code in (401, 403, 404)
