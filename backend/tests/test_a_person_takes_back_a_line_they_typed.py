"""A person takes back the line they typed: one door, one row, no sentence left behind.

`messages.is_deleted` was read by four repositories from the day the table was made — the chat page,
the pair preview and its unread count, the newest plan event of an idea, the plan's own history — and
was written by nobody. `docs/DATABASE.md` called the column a soft delete and the product never gave
it a door, so a sentence sent into a pair's chat stayed there until one of them left the app entirely.
The stage-110 stand measures it: 68 rows, 0 of them marked deleted, and every candidate spelling of
the door answering 404.

This file pins the door that closes it — `DELETE /api/v1/matches/{match_id}/messages/{message_id}` —
and what it promises:

* the line leaves both halves of the conversation, and the row that carried it keeps its place with
  its words erased and its dedup key cleared, so what is hidden is also empty;
* the only line this tap can end is the sender's own typed one: a partner's line, a page of the pair's
  plan, a line already taken back, a line of a chat this account is not in, and an id that was never a
  line all answer the same 404, and none of them is edited;
* a retry of a send whose response was lost cannot resurrect a recalled line, because the key that
  matched it went with the words;
* the recall travels on the pair's socket as its own frame, to both ends and with no exclusion, so an
  open screen drops the line instead of waiting for a reload;
* a pair that no longer exists answers the same 404 rather than a 500 — the recall takes the pair lock
  every other write into a chat takes.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message
from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth


async def _ready(client: AsyncClient, email: str, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def _pair(client: AsyncClient) -> tuple[dict, dict, str]:
    a = await _ready(client, "recall_a@befos.app", "Аня", "female")
    b = await _ready(client, "recall_b@befos.app", "Боря", "male")
    await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    return a, b, mutual.json()["match_id"]


async def _say(client: AsyncClient, who: dict, match_id: str, body: str, **payload) -> dict:
    response = await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": body, **payload},
        headers=auth_headers(who["token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _recall(client: AsyncClient, who: dict, match_id: str, message_id: str):
    return await client.delete(
        f"/api/v1/matches/{match_id}/messages/{message_id}",
        headers=auth_headers(who["token"]),
    )


async def _bodies(client: AsyncClient, who: dict, match_id: str) -> list[str]:
    page = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(who["token"])
    )
    assert page.status_code == 200, page.text
    return [line["body"] for line in page.json()["messages"]]


async def _row(session: AsyncSession, message_id: str) -> Message:
    return (
        await session.execute(select(Message).where(Message.id == uuid.UUID(message_id)))
    ).scalar_one()


async def test_own_line_leaves_both_halves_of_the_conversation(client: AsyncClient):
    a, b, match_id = await _pair(client)
    mine = await _say(client, a, match_id, "Написал и передумал")
    theirs = await _say(client, b, match_id, "А это строка собеседника")

    gone = await _recall(client, a, match_id, mine["id"])
    assert gone.status_code == 204, gone.text
    assert gone.content == b"", "a 204 that carries a body is a malformed answer"

    assert await _bodies(client, a, match_id) == [theirs["body"]]
    assert await _bodies(client, b, match_id) == [theirs["body"]]


async def test_the_words_go_with_the_line_and_the_row_keeps_its_place(
    client: AsyncClient, session: AsyncSession
):
    """The soft delete is honest about what it hides: the text is erased, not merely unshown."""
    a, _, match_id = await _pair(client)
    mine = await _say(client, a, match_id, "Слово, которое человек забирает обратно", client_msg_id="d-1")

    assert (await _recall(client, a, match_id, mine["id"])).status_code == 204
    row = await _row(session, mine["id"])
    assert row.is_deleted is True
    assert row.body == "", "a hidden sentence is still a sentence somebody could read"
    assert row.client_msg_id is None
    assert row.match_id == uuid.UUID(match_id) and row.sender_id == uuid.UUID(a["user_id"])


async def test_a_partners_line_is_not_mine_to_take_back(client: AsyncClient, session: AsyncSession):
    a, b, match_id = await _pair(client)
    theirs = await _say(client, b, match_id, "Эту строку писал не я")

    refused = await _recall(client, a, match_id, theirs["id"])
    assert refused.status_code == 404, refused.text
    assert refused.json()["error"]["code"] == "not_found"

    row = await _row(session, theirs["id"])
    assert row.is_deleted is False and row.body == "Эту строку писал не я"
    assert await _bodies(client, b, match_id) == [theirs["body"]]


async def test_an_absent_id_a_taken_line_and_a_foreign_chat_answer_the_same(
    client: AsyncClient
):
    a, _, match_id = await _pair(client)
    mine = await _say(client, a, match_id, "Одна и та же причина для четырёх отказов")
    await _recall(client, a, match_id, mine["id"])

    stranger = await _ready(client, "recall_c@befos.app", "Вера", "other")
    answers = [
        await _recall(client, a, match_id, str(uuid.uuid4())),
        await _recall(client, a, match_id, mine["id"]),
        await _recall(client, stranger, match_id, mine["id"]),
    ]
    for response in answers:
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "not_found"
    # The two sentences the door uses — «Match not found.» for the chat this account is not in,
    # «Message not found.» for a line of a chat it is — are the ones every other chat route
    # already answers with; what this stage added is that no third answer exists.
    assert {response.json()["error"]["message"] for response in answers} == {
        "Match not found.",
        "Message not found.",
    }


async def test_a_page_of_the_pairs_plan_is_not_a_line_somebody_typed(
    client: AsyncClient, session: AsyncSession
):
    """A journal line belongs to the arrangement, not to the tap that wrote it — so this door misses it."""
    a, b, match_id = await _pair(client)
    ideas = await client.get(
        f"/api/v1/matches/{match_id}/recommendations?force=true", headers=auth_headers(a["token"])
    )
    activity_id = ideas.json()["recommendations"][0]["activity"]["id"]
    proposed = await client.post(
        f"/api/v1/matches/{match_id}/recommendations/{activity_id}/select",
        headers=auth_headers(a["token"]),
    )
    assert proposed.status_code == 204, proposed.text

    page = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(b["token"])
    )
    journal = [line for line in page.json()["messages"] if line["kind"] != "text"]
    assert journal, "selecting an idea is supposed to put its line in the chat"

    refused = await _recall(client, a, match_id, journal[0]["id"])
    assert refused.status_code == 404, refused.text
    assert (await _row(session, journal[0]["id"])).is_deleted is False
    assert [line["id"] for line in (await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(b["token"])
    )).json()["messages"]] == [line["id"] for line in page.json()["messages"]]


async def test_a_retry_of_a_send_that_was_taken_back_writes_a_new_line(
    client: AsyncClient, session: AsyncSession
):
    """The dedup key guards a live line, not a decision: after the recall the retry is a new sentence."""
    a, _, match_id = await _pair(client)
    first = await _say(client, a, match_id, "Один и тот же текст", client_msg_id="d-2")
    await _recall(client, a, match_id, first["id"])

    again = await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": "Один и тот же текст", "client_msg_id": "d-2"},
        headers=auth_headers(a["token"]),
    )
    assert again.status_code == 201, again.text
    assert again.json()["id"] != first["id"]
    assert await _bodies(client, a, match_id) == ["Один и тот же текст"]


async def test_the_recall_reaches_the_screen_that_is_already_open(
    client: AsyncClient, monkeypatch
):
    from app.api.v1 import chat as chat_api

    events: list[dict] = []
    options: list[dict] = []

    async def fake_broadcast(match_id: str, payload: dict, **send_options: object) -> None:
        events.append(payload)
        options.append(send_options)

    monkeypatch.setattr(chat_api.manager, "broadcast_to_match", fake_broadcast)

    a, b, match_id = await _pair(client)
    mine = await _say(client, a, match_id, "Строка, которая уйдёт с открытого экрана")
    events.clear()
    options.clear()

    assert (await _recall(client, a, match_id, mine["id"])).status_code == 204
    assert events == [
        {"type": "message_recalled", "match_id": match_id, "message_id": mine["id"]}
    ]
    # No exclusion: the other half has to drop the line, and a second device of the person who
    # tapped has to find the same empty place it just made.
    assert options == [{}]


async def test_a_refused_recall_says_nothing_on_the_socket(client: AsyncClient, monkeypatch):
    from app.api.v1 import chat as chat_api

    events: list[dict] = []

    async def fake_broadcast(match_id: str, payload: dict, **send_options: object) -> None:
        events.append(payload)

    monkeypatch.setattr(chat_api.manager, "broadcast_to_match", fake_broadcast)

    a, b, match_id = await _pair(client)
    theirs = await _say(client, b, match_id, "Чужая строка")
    events.clear()

    assert (await _recall(client, a, match_id, theirs["id"])).status_code == 404
    assert events == [], "an answer that changed no row must not tell anybody a row changed"


async def test_a_recalled_line_stops_counting_as_the_newest_one(client: AsyncClient):
    a, b, match_id = await _pair(client)
    old = await _say(client, a, match_id, "Прежняя строка")
    newest = await _say(client, a, match_id, "Самая свежая, пока её не забрали")
    assert newest["created_at"] >= old["created_at"]

    await _recall(client, a, match_id, newest["id"])

    page = await client.get("/api/v1/matches", headers=auth_headers(b["token"]))
    row = next(m for m in page.json()["matches"] if m["match_id"] == match_id)
    assert row["last_message"] == "Прежняя строка"
    # The recalled line was one of the two the partner had not read, so the badge counts one.
    assert row["unread"] == 1


async def test_an_unread_line_that_is_taken_back_stops_being_unread(client: AsyncClient):
    a, b, match_id = await _pair(client)
    await _say(client, a, match_id, "Прочти меня, если успеешь")
    mine = await _say(client, a, match_id, "Эту я заберу до того, как её прочтут")

    before = await client.get("/api/v1/matches", headers=auth_headers(b["token"]))
    row = next(m for m in before.json()["matches"] if m["match_id"] == match_id)
    assert row["unread"] == 2

    await _recall(client, a, match_id, mine["id"])
    after = await client.get("/api/v1/matches", headers=auth_headers(b["token"]))
    row = next(m for m in after.json()["matches"] if m["match_id"] == match_id)
    assert row["unread"] == 1


async def test_a_dissolved_pair_answers_as_absent_not_as_an_error(client: AsyncClient):
    a, _, match_id = await _pair(client)
    mine = await _say(client, a, match_id, "Строка пары, которой больше нет")

    dissolved = await client.delete(f"/api/v1/matches/{match_id}", headers=auth_headers(a["token"]))
    assert dissolved.status_code == 204, dissolved.text

    refused = await _recall(client, a, match_id, mine["id"])
    assert refused.status_code == 404, refused.text
    assert refused.json()["error"]["code"] == "not_found"


async def test_an_anonymous_tap_is_refused_before_any_row_is_named(client: AsyncClient):
    a, _, match_id = await _pair(client)
    mine = await _say(client, a, match_id, "Эту строку никто не отзовет без токена")

    anonymous = await client.delete(f"/api/v1/matches/{match_id}/messages/{mine['id']}")
    assert anonymous.status_code == 401, anonymous.text
    assert await _bodies(client, a, match_id) == [mine["body"]]
