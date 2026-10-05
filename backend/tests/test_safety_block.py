"""A block is a wall, not a hide: neither side keeps a door into the other.

Blocking deletes the match row, and everything the pair could still reach has to be derived
from that row. The tests below walk each door that a stale screen, a stale socket or a
guessed id could still open — chat history, sending, the match list, the profile, a like —
and ask whether the database still answers to it.
"""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import status
from httpx import AsyncClient

from app.websocket.chat_ws import chat_socket
from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)
from .test_chat_idempotency import FakeSocket


async def _ready(client: AsyncClient, email: str, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def _matched_pair(client: AsyncClient) -> tuple[dict, dict, str]:
    a = await _ready(client, "blk_a@befos.app", "Аня", "female")
    b = await _ready(client, "blk_b@befos.app", "Боря", "male")
    await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    return a, b, mutual.json()["match_id"]


async def _wait_until(predicate, *, timeout: float = 5.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.02)
    return False


async def test_a_block_leaves_the_pair_no_way_back_into_the_chat(client: AsyncClient):
    a, b, match_id = await _matched_pair(client)
    sent = await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": "Привет до блокировки"},
        headers=auth_headers(a["token"]),
    )
    assert sent.status_code == 201, sent.text

    blocked = await client.post(
        f"/api/v1/users/{b['user_id']}/block", json={}, headers=auth_headers(a["token"])
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["blocked"] is True

    # Neither the blocker nor the blocked keeps a read path: a 200 here would mean the
    # conversation is still live for somebody, which is exactly what blocking promises.
    for who in (a, b):
        history = await client.get(
            f"/api/v1/matches/{match_id}/messages", headers=auth_headers(who["token"])
        )
        assert history.status_code == 404, history.text
        write = await client.post(
            f"/api/v1/matches/{match_id}/messages",
            json={"body": "ещё одно"},
            headers=auth_headers(who["token"]),
        )
        assert write.status_code in (403, 404), write.text

    for who in (a, b):
        listed = await client.get("/api/v1/matches", headers=auth_headers(who["token"]))
        assert listed.status_code == 200
        assert match_id not in [m["match_id"] for m in listed.json()["matches"]]

    # The profile and a fresh like both answer as if the person were not there, so a
    # blocked user cannot be re-liked into a new match.
    profile = await client.get(
        f"/api/v1/users/{b['user_id']}", headers=auth_headers(a["token"])
    )
    assert profile.status_code == 404
    reliked = await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    assert reliked.status_code == 404


async def test_a_socket_opened_before_the_block_is_closed_by_it(client: AsyncClient):
    """The block commits, then the room is closed: an open socket must not keep pretending."""
    a, b, match_id = await _matched_pair(client)
    sock_a, sock_b = FakeSocket(), FakeSocket()
    task_a = asyncio.create_task(chat_socket(sock_a, uuid.UUID(match_id), token=a["token"]))
    task_b = asyncio.create_task(chat_socket(sock_b, uuid.UUID(match_id), token=b["token"]))
    assert await _wait_until(lambda: sock_a.accepted and sock_b.accepted)
    try:
        blocked = await client.post(
            f"/api/v1/users/{b['user_id']}/block", json={}, headers=auth_headers(a["token"])
        )
        assert blocked.status_code == 200, blocked.text
        assert await _wait_until(
            lambda: sock_a.closed_code == status.WS_1008_POLICY_VIOLATION
            and sock_b.closed_code == status.WS_1008_POLICY_VIOLATION
        )

        # Closed as far as the room is concerned, and closed as far as a write goes: a
        # client that missed the close still gets no message stored.
        sock_b.incoming.put_nowait({"type": "message", "body": "через мёртвый сокет"})
        assert not await _wait_until(lambda: len(sock_b.messages_to_me()) > 0, timeout=0.5)
    finally:
        for sock, task in ((sock_a, task_a), (sock_b, task_b)):
            sock.incoming.put_nowait(None)
            await asyncio.wait_for(task, timeout=5.0)


async def test_blocking_yourself_is_refused_before_anything_dissolves(client: AsyncClient):
    a, _, match_id = await _matched_pair(client)
    self_block = await client.post(
        f"/api/v1/users/{a['user_id']}/block", json={}, headers=auth_headers(a["token"])
    )
    assert self_block.status_code == 422
    assert self_block.json()["error"]["message"] == "You cannot block yourself."

    history = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(a["token"])
    )
    assert history.status_code == 200, "a refused block must not dissolve anything"


async def test_a_report_is_stored_once_and_its_duplicate_is_advice(client: AsyncClient):
    """A report has no reader in the app yet, so its one honest duty is to be kept, once.

    The row is what an operator reads; a duplicate tap must not bury the first one.
    """
    a, b, _ = await _matched_pair(client)
    first = await client.post(
        f"/api/v1/users/{b['user_id']}/report",
        json={"reason": "harassment", "details": "Пишет оскорбления"},
        headers=auth_headers(a["token"]),
    )
    assert first.status_code == 200, first.text
    assert first.json()["reported"] is True

    duplicate = await client.post(
        f"/api/v1/users/{b['user_id']}/report",
        json={"reason": "harassment"},
        headers=auth_headers(a["token"]),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["message"] == (
        "You have already reported this user for the same reason."
    )

    other_reason = await client.post(
        f"/api/v1/users/{b['user_id']}/report",
        json={"reason": "fake"},
        headers=auth_headers(a["token"]),
    )
    assert other_reason.status_code == 200, json.dumps(other_reason.json())
