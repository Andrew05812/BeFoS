"""A chat open that races the block dissolving its match must not answer 500.

``ChatService.history`` and ``ChatService.mark_read`` authorise membership with ``get_match`` and
then write read receipts: ``ChatRepository.mark_read`` selects the unread message ids and INSERTs a
``message_reads`` row per id. ``message_reads.message_id`` and ``messages.match_id`` are both
``ON DELETE CASCADE``, and a block deletes the match — which cascades its messages away. A block
committed between the select and the insert leaves the receipt pointing at a message that no longer
exists, so the insert raises ``ForeignKeyViolationError`` and the app turns it into an HTTP 500.
Opening a chat — a GET — was the one that crashed, and it is the hottest path in the product.

The fix is the same discipline the send repair (stage 11) uses: the receipt writes take the pair
advisory lock the block takes, so the two transactions take turns. Under the lock the select and the
insert see the same live messages, so the receipt lands and the later block cascades it away behind
us; if the block lands first, the membership re-check under the lock finds no match and answers 404 —
the reply an absent chat already gives. The WebSocket ``read`` frame is routed through the same
service method for the same reason the ``message`` frame was routed through ``send``.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.repositories.chat_repo import ChatRepository
from .conftest import auth_headers, complete_onboarding, register_and_auth


async def _matched_pair(client: AsyncClient) -> tuple[dict, dict, str]:
    a = await register_and_auth(client, "readreceipt-a@befos.app")
    b = await register_and_auth(client, "readreceipt-b@befos.app")
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


async def test_opening_a_chat_racing_the_block_that_dissolves_it_is_not_a_500(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b, match_id = await _matched_pair(client)

    # a writes so b has something to mark read when they open the chat.
    sent = await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": "привет"},
        headers=auth_headers(a["token"]),
    )
    assert sent.status_code == 201, sent.text

    open_reached_insert = asyncio.Event()
    block_committed = asyncio.Event()
    original = ChatRepository._pending_unread_ids
    state = {"fired": False}

    async def gated(self, mid, reader_id):  # type: ignore[no-untyped-def]
        # This is the read that feeds the receipt insert: it names the live messages the open is
        # about to mark. Hold the open here until the block has committed its dissolve, so the very
        # next statement — the INSERT — runs against messages that are really gone. Pre-fix that
        # insert is a foreign-key violation and a 500 on a GET. Post-fix the open never reaches this
        # point with the block waiting: it holds the pair lock, so the block cannot commit here and
        # the wait simply times out, the receipt lands on still-live rows, and the block dissolves
        # the pair afterwards.
        pending = await original(self, mid, reader_id)
        if not state["fired"]:
            state["fired"] = True
            open_reached_insert.set()
            try:
                await asyncio.wait_for(block_committed.wait(), timeout=6.0)
            except asyncio.TimeoutError:
                pass
        return pending

    monkeypatch.setattr(ChatRepository, "_pending_unread_ids", gated)

    responses: dict[str, object] = {}

    async def do_open() -> None:
        responses["open"] = await client.get(
            f"/api/v1/matches/{match_id}/messages", headers=auth_headers(b["token"])
        )

    async def do_block() -> None:
        await asyncio.wait_for(open_reached_insert.wait(), timeout=6.0)
        responses["block"] = await client.post(
            f"/api/v1/users/{b['user_id']}/block", json={}, headers=auth_headers(a["token"])
        )
        block_committed.set()

    await asyncio.wait_for(asyncio.gather(do_open(), do_block()), timeout=30.0)

    block = responses["block"]
    assert block.status_code == 200, block.text
    assert block.json()["blocked"] is True

    opened = responses["open"]
    # The reader whose chat was dissolved mid-open is told it is gone (404) or is served the backlog
    # (200), but never a 500. A 500 here is the receipt insert's foreign-key violation surfacing.
    assert opened.status_code != 500, opened.text
    assert opened.status_code in (200, 404), opened.text

    # And the dissolved match keeps no orphan: the follow-up read answers the same thing every read
    # of an absent chat does, and no receipt outlives the messages it pointed at.
    listed = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(b["token"])
    )
    assert listed.status_code == 404, listed.text
