"""The receipt used to be written in two round trips that asked one question.

``GET /api/v1/matches/{id}/messages`` and ``POST /api/v1/matches/{id}/read`` both end by recording
which messages the reader has now seen. ``ChatRepository.mark_read`` used to ask the database for
those message ids with a SELECT, carry the list into Python, and send the very same ids back as one
parameter group per message in the INSERT. Listening with ``before_cursor_execute`` counted eight
statements for a chat open that had something to mark, six for the explicit ``/read``, and the pair
of them was the work of naming the backlog and re-naming it.

Written as ``INSERT … SELECT`` the ids stay inside the database, so the receipt costs one statement
and its text no longer grows with the length of the conversation. The count that decides whether the
``прочитано`` broadcast goes out still comes from ``RETURNING``, which reports the rows this call
actually inserted — the constraint is what settles two devices marking the same message at once.

What must not move is the answer: the same number of messages marked, no duplicate receipt row for
one reader, and the peer's bubbles still shown as read once the reader's other device reloads.

The ceilings below were lowered by stage 50, which folded the receipt flag into the page read: an
open that has something to mark went from seven listener statements to six, because the collection
the page used to raise for its own `is_read` no longer travels as a query of its own.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Callable

from httpx import AsyncClient
from sqlalchemy import event, func, select

from app.core.database import engine
from app.models import Message, MessageRead

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth


def _listener(seen: list[str]) -> Callable[..., None]:
    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    return _record


async def _counted(client: AsyncClient, awaitable: Awaitable) -> tuple[object, list[str]]:
    seen: list[str] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        resp = await awaitable
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    return resp, seen


def _receipt_statements(seen: list[str]) -> list[str]:
    """The statements whose only job is the reader's receipt.

    The write itself, and — pre-fix — the SELECT that named the unread ids the write then re-sent.
    """
    named = [
        statement
        for statement in seen
        if statement.startswith("select messages.id from messages") and "not (exists" in statement
    ]
    written = [statement for statement in seen if "insert into message_reads" in statement]
    return named + written


async def _account(client: AsyncClient, email: str, *, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def _pair_with_backlog(client: AsyncClient, prefix: str) -> tuple[dict, dict, str]:
    """A match whose last three messages came from the partner and are still unread."""
    reader = await _account(client, f"{prefix}_reader@befos.app", name="Вера", gender="female")
    author = await _account(client, f"{prefix}_author@befos.app", name="Пётр", gender="male")
    await client.post(
        f"/api/v1/users/{author['user_id']}/like", headers=auth_headers(reader["token"])
    )
    back = await client.post(
        f"/api/v1/users/{reader['user_id']}/like", headers=auth_headers(author["token"])
    )
    assert back.status_code == 200, back.text
    match_id = back.json()["match_id"]
    assert match_id
    for i in range(3):
        sent = await client.post(
            f"/api/v1/matches/{match_id}/messages",
            headers=auth_headers(author["token"]),
            json={"body": f"message {i}"},
        )
        assert sent.status_code == 201, sent.text
    return reader, author, match_id


async def test_opening_a_chat_with_a_backlog_writes_the_receipt_in_one_statement(
    client: AsyncClient, session
) -> None:
    reader, _author, match_id = await _pair_with_backlog(client, "s32_open")

    resp, seen = await _counted(
        client,
        client.get(f"/api/v1/matches/{match_id}/messages", headers=auth_headers(reader["token"])),
    )
    assert resp.status_code == 200, resp.text

    receipt = _receipt_statements(seen)
    assert len(receipt) == 1, (
        f"the receipt took {len(receipt)} statements: the unread ids were named and then re-sent"
    )
    assert "insert into message_reads" in receipt[0], receipt[0]
    # Six, not the seven this file used to allow: stage 50 folded the receipt flag into the text of
    # the page read, so opening a chat no longer sends a query of its own to `message_reads`.
    assert len(seen) <= 6, f"{len(seen)} trips to open a chat and mark its backlog"

    # Same answer as the two-statement shape: every message the reader did not write is now read.
    unread = (
        await session.execute(
            select(func.count(Message.id))
            .where(
                Message.match_id == match_id,
                Message.sender_id != reader["user_id"],
                ~Message.id.in_(
                    select(MessageRead.message_id).where(
                        MessageRead.reader_id == reader["user_id"]
                    )
                ),
            )
        )
    ).scalar_one()
    assert unread == 0, f"{unread} of the partner's messages were left unmarked"


async def test_the_explicit_read_call_marks_with_one_statement(client: AsyncClient) -> None:
    reader, _author, match_id = await _pair_with_backlog(client, "s32_read")

    resp, seen = await _counted(
        client,
        client.post(f"/api/v1/matches/{match_id}/read", headers=auth_headers(reader["token"])),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"marked_read": 3}, resp.text

    receipt = _receipt_statements(seen)
    assert len(receipt) == 1, (
        f"the receipt took {len(receipt)} statements: {receipt}"
    )
    assert len(seen) <= 5, f"{len(seen)} trips to mark one chat read"


async def test_the_second_open_reports_nothing_marked_and_writes_no_second_receipt(
    client: AsyncClient, session
) -> None:
    """The count comes from the rows this call inserted, not from the rows it looked at."""
    reader, _author, match_id = await _pair_with_backlog(client, "s32_twice")

    first, _ = await _counted(
        client,
        client.get(f"/api/v1/matches/{match_id}/messages", headers=auth_headers(reader["token"])),
    )
    assert first.status_code == 200, first.text

    second, seen = await _counted(
        client,
        client.get(f"/api/v1/matches/{match_id}/messages", headers=auth_headers(reader["token"])),
    )
    assert second.status_code == 200, second.text
    messages = second.json()["messages"]
    assert messages, "the chat lost the backlog it reloads"
    assert all(m["is_read"] for m in messages if not m["is_own"]), (
        "the partner's messages are still shown unread after the reader opened them"
    )

    rows = (
        await session.execute(
            select(func.count(MessageRead.id)).where(
                MessageRead.reader_id == reader["user_id"],
                MessageRead.message_id.in_(
                    select(Message.id).where(Message.match_id == match_id)
                ),
            )
        )
    ).scalar_one()
    assert rows == 3, f"{rows} receipt rows for three messages and one reader"


async def test_the_second_read_of_the_same_backlog_marks_nothing(
    client: AsyncClient, session
) -> None:
    """The count is the rows this call inserted, not the rows it looked at.

    One reader tapping «прочитано» twice must not tell the sender twice, and must not leave a
    second receipt row per message: the constraint settles the duplicate and ``RETURNING`` keeps
    the second call at zero.
    """
    reader, _author, match_id = await _pair_with_backlog(client, "s32_second")

    first = await client.post(
        f"/api/v1/matches/{match_id}/read", headers=auth_headers(reader["token"])
    )
    assert first.status_code == 200, first.text
    assert first.json() == {"marked_read": 3}, first.text

    second = await client.post(
        f"/api/v1/matches/{match_id}/read", headers=auth_headers(reader["token"])
    )
    assert second.status_code == 200, second.text
    assert second.json() == {"marked_read": 0}, second.text

    rows = (
        await session.execute(
            select(func.count(MessageRead.id)).where(
                MessageRead.reader_id == reader["user_id"],
                MessageRead.message_id.in_(
                    select(Message.id).where(Message.match_id == match_id)
                ),
            )
        )
    ).scalar_one()
    assert rows == 3, f"{rows} receipt rows for three messages and one reader"
