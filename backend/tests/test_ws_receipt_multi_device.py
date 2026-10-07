"""A socket receipt is per-user, not per-connection.

A person can hold two sockets on one match — phone and tablet. When the phone reports a
read or a keystroke, the tablet belongs to the same person, not to the peer, so neither
frame may reach it: the tablet must not mark the owner's own messages «прочитано» that the
peer never read, nor show «печатает…» for text the owner is typing on the other device.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from .test_chat_idempotency import (
    FakeSocket,
    _close,
    _matched_pair,
    _open,
    _send,
    _wait_until,
)


def _typed(sock: FakeSocket, kind: str) -> list[dict]:
    return [f for f in sock.sent if f.get("type") == kind]


async def test_socket_read_reaches_the_peer_but_not_the_readers_other_device(
    client: AsyncClient, session: AsyncSession
):
    a, b, match_id = await _matched_pair(client)
    sock_a = FakeSocket()
    sock_b1 = FakeSocket()
    sock_b2 = FakeSocket()
    task_a = await _open(sock_a, match_id, a["token"])
    task_b1 = await _open(sock_b1, match_id, b["token"])
    task_b2 = await _open(sock_b2, match_id, b["token"])
    try:
        sent = await _send(client, a, match_id, "Прочти меня")
        assert sent.status_code == 201

        sock_b1.incoming.put_nowait({"type": "read"})
        assert await _wait_until(lambda: len(_typed(sock_a, "read")) == 1)
        assert _typed(sock_a, "read")[0]["user_id"] == b["user_id"]
        # Neither of B's own sockets is told about the read B just performed.
        assert _typed(sock_b1, "read") == []
        assert _typed(sock_b2, "read") == []

        # A second read frame with nothing left to mark stays silent: the receipt fires only
        # for messages the call actually changed, exactly as the REST endpoint does.
        sock_b1.incoming.put_nowait({"type": "read"})
        await _settle()
        assert len(_typed(sock_a, "read")) == 1
    finally:
        await _close(sock_a, task_a)
        await _close(sock_b1, task_b1)
        await _close(sock_b2, task_b2)


async def test_socket_typing_does_not_echo_to_the_typers_other_device(
    client: AsyncClient, session: AsyncSession
):
    a, b, match_id = await _matched_pair(client)
    sock_a = FakeSocket()
    sock_b1 = FakeSocket()
    sock_b2 = FakeSocket()
    task_a = await _open(sock_a, match_id, a["token"])
    task_b1 = await _open(sock_b1, match_id, b["token"])
    task_b2 = await _open(sock_b2, match_id, b["token"])
    try:
        sock_b1.incoming.put_nowait({"type": "typing", "typing": True})
        assert await _wait_until(lambda: len(_typed(sock_a, "typing")) == 1)
        assert _typed(sock_a, "typing")[0]["user_id"] == b["user_id"]
        assert _typed(sock_b1, "typing") == []
        assert _typed(sock_b2, "typing") == []
    finally:
        await _close(sock_a, task_a)
        await _close(sock_b1, task_b1)
        await _close(sock_b2, task_b2)


async def _settle(*, seconds: float = 0.2) -> None:
    import asyncio

    await asyncio.sleep(seconds)
