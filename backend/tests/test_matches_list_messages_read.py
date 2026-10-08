"""The matches list read the ``messages`` table twice for the same match ids.

``GET /api/v1/matches`` shows, per pair, the newest line and the unread counter. Two statements
carried that: one ``SELECT DISTINCT ON (messages.match_id)`` picked the newest message of every
pair, a second ``SELECT messages.match_id, count(messages.id) … GROUP BY`` counted the unread ones —
and both walked the same rows of the same table for the same list of match ids. Listening with
``before_cursor_execute`` counted six statements on a reader with three pairs, two of them on
``messages``.

One statement can carry both: the unread count is a window aggregate over the pair's partition, so
the row that ``DISTINCT ON`` keeps as the newest also brings the counter with it.

What must not move is the answer. A reader's own messages are never unread for them, a receipt
written by the *other* reader must not remove the message from this reader's counter, a message the
pair deleted is neither the newest line nor a waiting one, and a pair without messages still shows
no line and a zero.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import event, update

from app.core.database import engine
from app.models import Message

from .conftest import auth_headers
from .test_chat_receipt_roundtrips import _account, _counted


def _messages_statements(seen: list[str]) -> list[str]:
    return [
        statement
        for statement in seen
        if statement.startswith("select") and "from messages" in statement
    ]


async def _pair(
    client: AsyncClient, reader: dict, slug: str, messages: int, *, open_chat: bool
) -> str:
    """A fresh match whose partner sent ``messages`` messages, newest last."""
    peer = await _account(client, f"{slug}@befos.app", name=f"Пётр {slug}", gender="male")
    await client.post(
        f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(reader["token"])
    )
    back = await client.post(
        f"/api/v1/users/{reader['user_id']}/like", headers=auth_headers(peer["token"])
    )
    assert back.status_code == 200, back.text
    match_id = back.json()["match_id"]
    assert match_id
    for i in range(messages):
        sent = await client.post(
            f"/api/v1/matches/{match_id}/messages",
            headers=auth_headers(peer["token"]),
            json={"body": f"{slug} line {i}"},
        )
        assert sent.status_code == 201, sent.text
    if open_chat:
        opened = await client.get(
            f"/api/v1/matches/{match_id}/messages", headers=auth_headers(reader["token"])
        )
        assert opened.status_code == 200, opened.text
    return match_id


async def _three_pairs(client: AsyncClient, prefix: str) -> tuple[dict, dict[str, str]]:
    reader = await _account(client, f"{prefix}_reader@befos.app", name="Вера", gender="female")
    ids = {
        "backlog": await _pair(client, reader, f"{prefix}_backlog", 3, open_chat=False),
        "read": await _pair(client, reader, f"{prefix}_read", 2, open_chat=True),
        "silent": await _pair(client, reader, f"{prefix}_silent", 0, open_chat=False),
    }
    return reader, ids


def _row(rows: list[dict], match_id: str) -> dict:
    found = [row for row in rows if row["match_id"] == match_id]
    assert found, f"the list lost the pair {match_id}: {[r['match_id'] for r in rows]}"
    return found[0]


async def test_the_matches_list_reads_the_messages_table_once(client: AsyncClient) -> None:
    """Both cards come from one pass over ``messages``."""
    reader, ids = await _three_pairs(client, "s33_once")

    resp, seen = await _counted(
        client, client.get("/api/v1/matches", headers=auth_headers(reader["token"]))
    )
    assert resp.status_code == 200, resp.text

    read = _messages_statements(seen)
    assert len(read) == 1, (
        f"the pair list read messages {len(read)} times: the newest line and the unread counter "
        "walked the same rows of the same matches in two statements"
    )
    assert len(seen) <= 5, f"{len(seen)} trips to list three pairs"


async def test_the_list_carries_the_counter_and_the_newest_line(client: AsyncClient) -> None:
    """The answer the two statements produced is the answer one statement has to produce."""
    reader, ids = await _three_pairs(client, "s33_answer")

    resp = await client.get("/api/v1/matches", headers=auth_headers(reader["token"]))
    assert resp.status_code == 200, resp.text
    rows = resp.json()["matches"]

    backlog = _row(rows, ids["backlog"])
    assert backlog["unread"] == 3, f"the waiting pair shows {backlog['unread']} unread"
    assert backlog["last_message"] == "s33_answer_backlog line 2", backlog["last_message"]

    read = _row(rows, ids["read"])
    assert read["unread"] == 0, f"the opened pair still counts {read['unread']} unread"
    assert read["last_message"] == "s33_answer_read line 1", read["last_message"]

    silent = _row(rows, ids["silent"])
    assert silent["last_message"] is None and silent["unread"] == 0, silent

    # Newest activity first, and the empty pair is the newest of the three because its match was
    # created last: the screen sorts by the last line, falling back to the date of the pair.
    assert [row["match_id"] for row in rows] == [ids["silent"], ids["read"], ids["backlog"]], rows


async def test_a_receipt_of_the_partner_does_not_mark_the_message_for_me(
    client: AsyncClient, session
) -> None:
    """Every sent message carries its author's own receipt.

    Joining ``message_reads`` without the reader would let those rows match, drop the message out of
    the counter — and, if the join fanned out, count one message twice.
    """
    reader, ids = await _three_pairs(client, "s33_partner_receipt")

    resp = await client.get("/api/v1/matches", headers=auth_headers(reader["token"]))
    assert resp.status_code == 200, resp.text
    backlog = _row(resp.json()["matches"], ids["backlog"])
    assert backlog["unread"] == 3, (
        f"the partner's own receipts moved the counter to {backlog['unread']}"
    )


async def test_a_deleted_message_is_neither_the_line_nor_a_waiting_one(
    client: AsyncClient, session
) -> None:
    reader, ids = await _three_pairs(client, "s33_deleted")

    await session.execute(
        update(Message)
        .where(
            Message.match_id == ids["backlog"],
            Message.body == "s33_deleted_backlog line 2",
        )
        .values(is_deleted=True)
    )
    await session.commit()

    resp = await client.get("/api/v1/matches", headers=auth_headers(reader["token"]))
    assert resp.status_code == 200, resp.text
    backlog = _row(resp.json()["matches"], ids["backlog"])
    assert backlog["last_message"] == "s33_deleted_backlog line 1", backlog["last_message"]
    assert backlog["unread"] == 2, f"the deleted line is still counted: {backlog['unread']}"
