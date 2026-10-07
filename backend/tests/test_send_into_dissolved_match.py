"""A send that races the block dissolving its match must answer 404, not crash.

``ChatService.send`` reads the match to authorise the sender and then inserts a message whose
foreign key points at that match. A block taken between the two — it deletes the parent row — made
the child insert raise ``ForeignKeyViolationError``, which the app turns into an HTTP 500. The
person who lost the race was the one being blocked, and the app's answer to their message was a
crash rather than "this chat is gone." The WebSocket write had the same window and it dropped the
socket instead.

The fix borrows the pair advisory lock from the block repair (``SafetyService.block`` takes it, and
``MatchService.like`` re-reads under it): the send takes that same lock and re-checks membership
after it holds it. Whichever transaction commits last wins cleanly — the send writes under the lock
and the later block cascades its rows away, or the block lands first and the send's re-check finds
no match and returns the same 404 a send into an absent match gives. The test forces the second
schedule, which is the one that used to throw.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.repositories.chat_repo import ChatRepository
from .conftest import auth_headers, complete_onboarding, register_and_auth


async def _matched_pair(client: AsyncClient) -> tuple[dict, dict, str]:
    a = await register_and_auth(client, "senddissolve-a@befos.app")
    b = await register_and_auth(client, "senddissolve-b@befos.app")
    await complete_onboarding(client, a["token"], name="Аня", gender="female")
    await complete_onboarding(client, b["token"], name="Боря", gender="male")
    await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    second = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    assert second.status_code == 200, second.text
    assert second.json()["match"] is True
    return a, b, second.json()["match_id"]


async def test_a_send_racing_the_block_that_dissolves_its_match_is_refused_not_crashed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b, match_id = await _matched_pair(client)

    send_read = asyncio.Event()
    block_committed = asyncio.Event()
    original = ChatRepository.get_match
    state = {"fired": False}

    async def gated(self, mid):  # type: ignore[no-untyped-def]
        # The first read is the authorisation the send is built on: it sees the match while the
        # block has not run yet. Hold the send there until the block has committed its dissolve,
        # so whatever the send does next happens against a match that is really gone. Pre-fix that
        # next step is the bare child insert — a foreign-key violation and a 500. Post-fix it is a
        # second membership read, taken under the pair lock, which finds nothing and answers 404.
        result = await original(self, mid)
        if not state["fired"]:
            state["fired"] = True
            send_read.set()
            try:
                await asyncio.wait_for(block_committed.wait(), timeout=6.0)
            except asyncio.TimeoutError:
                pass
        return result

    monkeypatch.setattr(ChatRepository, "get_match", gated)

    responses: dict[str, object] = {}

    async def do_send() -> None:
        responses["send"] = await client.post(
            f"/api/v1/matches/{match_id}/messages",
            json={"body": "привет"},
            headers=auth_headers(b["token"]),
        )

    async def do_block() -> None:
        await asyncio.wait_for(send_read.wait(), timeout=6.0)
        responses["block"] = await client.post(
            f"/api/v1/users/{b['user_id']}/block", json={}, headers=auth_headers(a["token"])
        )
        block_committed.set()

    await asyncio.wait_for(asyncio.gather(do_send(), do_block()), timeout=30.0)

    block = responses["block"]
    assert block.status_code == 200, block.text
    assert block.json()["blocked"] is True

    send = responses["send"]
    # The lost sender is told the chat is gone (the answer an absent match already gives), not
    # that the server broke. A 500 here is the foreign-key violation surfacing to the client.
    assert send.status_code == 404, send.text

    # And nothing was written into the dissolved match, so no orphan outlives the block.
    listed = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(b["token"])
    )
    assert listed.status_code == 404, listed.text
