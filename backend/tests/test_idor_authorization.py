"""IDOR sweep: user C must not read or mutate A<->B resources by guessing IDs."""

from __future__ import annotations

import base64
import uuid

import pytest
from fastapi import status
from httpx import AsyncClient

from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)
from .test_chat_idempotency import FakeSocket
from app.websocket.chat_ws import chat_socket


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


async def test_outsider_gets_no_room_with_a_valid_token_of_its_own(client, idor_setup):
    """The socket is the one door with a token in the URL, so it gets the same question.

    C holds a token for a real, active account of its own. That must not open A↔B's room:
    the handshake asks the rows, not the JWT.
    """
    _, _, c, match_id = idor_setup
    socket = FakeSocket()
    await chat_socket(socket, uuid.UUID(match_id), token=c["token"])
    assert socket.closed_code == status.WS_1008_POLICY_VIOLATION
    assert socket.accepted is False
    assert socket.sent == []


async def test_a_hidden_profile_is_not_reachable_by_a_known_user_id(client: AsyncClient, idor_setup):
    a, _, c, _ = idor_setup
    target = a["user_id"]
    assert (
        await client.get(f"/api/v1/users/{target}", headers=auth_headers(c["token"]))
    ).status_code == 200
    hidden = await client.post(
        "/api/v1/users/me/visibility", headers=auth_headers(a["token"]), json={"hidden": True}
    )
    assert hidden.status_code in (200, 204)
    # Hiding is a request to disappear, and an id learned earlier — a card already on
    # screen, a link sent in another messenger — must not keep working after it.
    gone = await client.get(f"/api/v1/users/{target}", headers=auth_headers(c["token"]))
    assert gone.status_code == 404
    # The owner still reads their own profile; hiding is not disabling.
    assert (
        await client.get(f"/api/v1/users/{target}", headers=auth_headers(a["token"]))
    ).status_code == 200


async def test_a_block_closes_the_profile_in_both_directions(client: AsyncClient, idor_setup):
    a, _, c, _ = idor_setup
    blocked = await client.post(
        f"/api/v1/users/{c['user_id']}/block", headers=auth_headers(a["token"])
    )
    assert blocked.status_code in (200, 201, 204)
    assert (
        await client.get(f"/api/v1/users/{a['user_id']}", headers=auth_headers(c["token"]))
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/users/{c['user_id']}", headers=auth_headers(a["token"]))
    ).status_code == 404


def _cursor(payload: str) -> str:
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


async def test_a_forged_discovery_cursor_is_refused_rather_than_interpreted(
    client: AsyncClient, idor_setup
):
    """A cursor the viewer did not receive must not be read as a rank.

    The deck is derived from the viewer's own answers, so the question is not whose cards
    come back — it is whether a hand-written cursor gets to pick rows the ranking never
    produced. The honest answer is "this link is broken".
    """
    a, _, _, _ = idor_setup
    headers = auth_headers(a["token"])
    forged = [
        "not-base64-at-all",
        _cursor("other:3"),
        _cursor("rank:-1"),
    ]
    for value in forged:
        resp = await client.get(f"/api/v1/discover?cursor={value}", headers=headers)
        assert resp.status_code == 422, f"{value} -> {resp.status_code} {resp.text}"

    # A well-formed rank past the end of the deck is not a security question: the deck is
    # the caller's own, so the answer is an empty page, not somebody else's cards and not
    # a 500 from arithmetic on a position that does not exist.
    far = await client.get(
        f"/api/v1/discover?cursor={_cursor('rank:999999999')}", headers=headers
    )
    assert far.status_code == 200, far.text
    assert far.json()["items"] == []


async def test_a_cursor_from_another_room_shows_nothing_of_that_room(client: AsyncClient):
    """`before_id` names a message in another chat, and paging stays inside one chat.

    The anchor is only used to look up a timestamp; if the filter ever slipped to that
    timestamp alone, a foreign message id would turn into a window onto its room.
    """
    a = await _ready(client, "idor_a@befos.app", "Аня", "female")
    b = await _ready(client, "idor_b@befos.app", "Боря", "male")
    d = await _ready(client, "idor_d@befos.app", "Даша", "female")

    # Only the like that completes the pair reports a match id, so it is taken from the
    # second tap in each pair, not the first.
    await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    ab = (
        await client.post(
            f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
        )
    ).json()["match_id"]
    await client.post(
        f"/api/v1/users/{d['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    ad = (
        await client.post(
            f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(d["token"])
        )
    ).json()["match_id"]
    assert ab and ad

    own = await client.post(
        f"/api/v1/matches/{ab}/messages",
        json={"body": "привет Боре"},
        headers=auth_headers(a["token"]),
    )
    assert own.status_code == 201, own.text
    # The anchor has to be newer than the row it should still show, otherwise the page is
    # empty for a reason that has nothing to do with authorization.
    foreign = await client.post(
        f"/api/v1/matches/{ad}/messages",
        json={"body": "секрет Даши"},
        headers=auth_headers(a["token"]),
    )
    assert foreign.status_code == 201, foreign.text
    foreign_id = foreign.json()["id"]

    history = await client.get(
        f"/api/v1/matches/{ab}/messages?before_id={foreign_id}",
        headers=auth_headers(a["token"]),
    )
    assert history.status_code == 200
    messages = history.json()["messages"]
    assert [m["body"] for m in messages] == ["привет Боре"]
    assert all(m["match_id"] == ab for m in messages)
