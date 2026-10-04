"""A send the client names is one message: on REST, on the socket, and on a retry of either.

The failure being prevented is the lost response: a POST that reached the server but whose
answer never arrived looks, to the client, exactly like a POST that was refused, so the
client retries and the peer reads the same sentence twice.
"""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import status, WebSocketDisconnect
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message
from app.websocket.chat_ws import chat_socket, client_msg_id_from
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
    a = await _ready(client, "idem_a@befos.app", "Аня", "female")
    b = await _ready(client, "idem_b@befos.app", "Боря", "male")
    await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    return a, b, mutual.json()["match_id"]


async def _send(client: AsyncClient, who: dict, match_id: str, body: str, **payload):
    return await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": body, **payload},
        headers=auth_headers(who["token"]),
    )


async def _bodies(session: AsyncSession, match_id: str) -> list[tuple[str, str | None]]:
    rows = (
        await session.execute(
            select(Message.body, Message.client_msg_id)
            .where(Message.match_id == uuid.UUID(match_id))
            .order_by(Message.created_at, Message.id)
        )
    ).all()
    return [(row[0], row[1]) for row in rows]


async def test_retry_of_a_send_with_the_same_id_stores_one_message(
    client: AsyncClient, session: AsyncSession
):
    a, _, match_id = await _matched_pair(client)
    first = await _send(client, a, match_id, "Одно и то же", client_msg_id="draft-1")
    assert first.status_code == 201, first.text
    retry = await _send(client, a, match_id, "Одно и то же", client_msg_id="draft-1")
    # The retry is not a new resource, so it must not answer as one.
    assert retry.status_code == 200, retry.text
    assert retry.json()["id"] == first.json()["id"]
    assert retry.json()["client_msg_id"] == "draft-1"
    assert await _bodies(session, match_id) == [("Одно и то же", "draft-1")]


async def test_two_partners_can_use_the_same_id_for_their_own_sends(
    client: AsyncClient, session: AsyncSession
):
    a, b, match_id = await _matched_pair(client)
    one = await _send(client, a, match_id, "Привет", client_msg_id="c1")
    two = await _send(client, b, match_id, "Привет", client_msg_id="c1")
    assert one.status_code == 201 and two.status_code == 201
    assert one.json()["id"] != two.json()["id"]
    assert len(await _bodies(session, match_id)) == 2


async def test_a_send_without_an_id_is_not_deduplicated(
    client: AsyncClient, session: AsyncSession
):
    """Naming the send is what makes a retry safe; without a name nothing may be assumed."""
    a, _, match_id = await _matched_pair(client)
    assert (await _send(client, a, match_id, "Два раза")).status_code == 201
    assert (await _send(client, a, match_id, "Два раза")).status_code == 201
    assert len(await _bodies(session, match_id)) == 2


async def test_an_over_long_id_is_refused_and_nothing_is_stored(
    client: AsyncClient, session: AsyncSession
):
    a, _, match_id = await _matched_pair(client)
    resp = await _send(client, a, match_id, "Слишком длинный id", client_msg_id="x" * 65)
    assert resp.status_code == 422, resp.text
    assert await _bodies(session, match_id) == []


def test_client_id_from_a_frame_is_bounded_the_same_way_as_the_column():
    assert client_msg_id_from({}) == (None, None)
    assert client_msg_id_from({"client_msg_id": ""}) == (None, None)
    assert client_msg_id_from({"client_msg_id": "  draft-7  "}) == ("draft-7", None)
    assert client_msg_id_from({"client_msg_id": "x" * 64}) == ("x" * 64, None)
    assert client_msg_id_from({"client_msg_id": "x" * 65})[1] is not None
    assert client_msg_id_from({"client_msg_id": 42})[1] is not None


class FakeSocket:
    """A WebSocket stand-in: records what the room sends and answers from a queue.

    The handler only uses accept, send_json, receive_text and close, and driving it
    through a real test client would put the app on a second event loop while the test
    data lives on this one. The code under test here is the room logic, not Starlette.
    """

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.accepted = False
        self.closed_code: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)

    async def receive_text(self) -> str:
        frame = await self.incoming.get()
        if frame is None:
            raise WebSocketDisconnect()
        return json.dumps(frame)

    async def close(self, code: int = 1000) -> None:
        self.closed_code = code

    def messages_to_me(self) -> list[dict]:
        return [f for f in self.sent if f.get("type") == "message"]


async def _wait_until(predicate, *, timeout: float = 5.0) -> bool:
    """A queued frame is not yet an answered one: the socket handler runs as its own task."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.02)
    return False


async def _open(socket: FakeSocket, match_id: str, token: str) -> asyncio.Task:
    task = asyncio.create_task(chat_socket(socket, uuid.UUID(match_id), token=token))
    assert await _wait_until(lambda: socket.accepted or socket.closed_code is not None)
    return task


async def _close(socket: FakeSocket, task: asyncio.Task) -> None:
    socket.incoming.put_nowait(None)
    await asyncio.wait_for(task, timeout=5.0)


async def test_a_replayed_socket_send_reaches_the_peer_once(
    client: AsyncClient, session: AsyncSession
):
    a, b, match_id = await _matched_pair(client)
    sock_a, sock_b = FakeSocket(), FakeSocket()
    task_a = await _open(sock_a, match_id, a["token"])
    task_b = await _open(sock_b, match_id, b["token"])
    try:
        frame = {"type": "message", "body": "Привет из сокета", "client_msg_id": "ws-1"}
        sock_a.incoming.put_nowait(frame)
        assert await _wait_until(lambda: len(sock_b.messages_to_me()) == 1)
        sock_a.incoming.put_nowait(frame)
        # The sender is answered twice; the second answer is the same stored message.
        assert await _wait_until(lambda: len(sock_a.messages_to_me()) == 2)
        assert await _wait_until(lambda: len(sock_b.messages_to_me()) == 1)

        stored = await _bodies(session, match_id)
        assert stored == [("Привет из сокета", "ws-1")]
        echoed = sock_a.messages_to_me()
        assert echoed[0]["id"] == echoed[1]["id"]
        assert echoed[1]["client_msg_id"] == "ws-1"
        assert len(sock_b.messages_to_me()) == 1
    finally:
        await _close(sock_a, task_a)
        await _close(sock_b, task_b)


async def test_a_socket_send_without_an_id_still_reaches_the_peer(
    client: AsyncClient, session: AsyncSession
):
    a, b, match_id = await _matched_pair(client)
    sock_a, sock_b = FakeSocket(), FakeSocket()
    task_a = await _open(sock_a, match_id, a["token"])
    task_b = await _open(sock_b, match_id, b["token"])
    try:
        sock_a.incoming.put_nowait({"type": "message", "body": "Без имени"})
        assert await _wait_until(lambda: len(sock_b.messages_to_me()) == 1)
        assert sock_b.messages_to_me()[0]["client_msg_id"] is None
        assert await _bodies(session, match_id) == [("Без имени", None)]
    finally:
        await _close(sock_a, task_a)
        await _close(sock_b, task_b)


async def test_a_bad_client_id_is_answered_without_killing_the_socket(
    client: AsyncClient, session: AsyncSession
):
    a, _, match_id = await _matched_pair(client)
    sock = FakeSocket()
    task = await _open(sock, match_id, a["token"])
    try:
        sock.incoming.put_nowait({"type": "message", "body": "Хочу ответить", "client_msg_id": "x" * 65})
        assert await _wait_until(lambda: any(f.get("type") == "error" for f in sock.sent))
        sock.incoming.put_nowait({"type": "message", "body": "Хочу ответить", "client_msg_id": "ok-1"})
        assert await _wait_until(lambda: len(sock.messages_to_me()) == 1)
        assert await _bodies(session, match_id) == [("Хочу ответить", "ok-1")]
        assert sock.closed_code is None
    finally:
        await _close(sock, task)


async def test_a_deleted_account_gets_no_room_with_its_still_valid_token(
    client: AsyncClient, session: AsyncSession
):
    """The access token outlives the account, so the socket asks the rows and not the JWT."""
    a, _, match_id = await _matched_pair(client)
    token = a["token"]
    deleted = await client.delete("/api/v1/users/me", headers=auth_headers(token))
    assert deleted.status_code == 200, deleted.text

    sock = FakeSocket()
    task = await _open(sock, match_id, token)
    assert sock.accepted is False
    assert sock.closed_code == status.WS_1008_POLICY_VIOLATION
    await asyncio.wait_for(task, timeout=5.0)
    assert await _bodies(session, match_id) == []
