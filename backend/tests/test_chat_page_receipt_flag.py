"""The receipt flag rides inside the page read instead of making its own round trip.

``GET /api/v1/matches/{id}/messages`` answers eight fields per line and one of them, `is_read`,
means «somebody other than the author has seen this line». The code used to answer it by raising
the `Message.reads` collection as a second query (`selectinload`) and reducing it in Python to one
boolean per line: measured 2026-10-10 on the stage-50 stand (a 500-line thread, a 50-line page,
40 500 receipts in the table) that second trip carried 51 parameters and brought back 76 rows and
as many ORM objects, to answer fifty booleans.

Stage 50 asks the same question inside the read that already picks the page: a correlated
``EXISTS (… reader_id <> sender_id)``. The base does not work less — the two old plans sum to
1.22 ms, the new one to 1.19 ms — what goes away is the conversation and the objects.

What must not move is the answer again. The semantics live in the difference between «read by
anybody» and «read by somebody who is not the author»: `_note_read_by_sender` writes the author's
own receipt for every line they send, so a naive `EXISTS` without `reader_id <> sender_id` would
show the author their own line as read before the partner ever opened the chat.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Callable

from httpx import AsyncClient
from sqlalchemy import event

from app.core.database import engine

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


def _receipt_reads(seen: list[str]) -> list[str]:
    """Reads whose only job is to bring receipts for a page that has already been picked."""
    return [s for s in seen if s.startswith("select message_reads")]


async def _account(client: AsyncClient, email: str, *, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def _pair(client: AsyncClient, prefix: str) -> tuple[dict, dict, str]:
    """A pair where the partner has written three lines and the reader has written none."""
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
            json={"body": f"строка {i}"},
        )
        assert sent.status_code == 201, sent.text
    return reader, author, match_id


async def test_the_page_read_carries_the_flag_without_a_second_read(client: AsyncClient) -> None:
    """Not one read of `message_reads` outside the read that already picks the page."""
    reader, _author, match_id = await _pair(client, "s50_flag")
    first = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(reader["token"])
    )
    assert first.status_code == 200, first.text

    resp, seen = await _counted(
        client,
        client.get(f"/api/v1/matches/{match_id}/messages", headers=auth_headers(reader["token"])),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["messages"], "the reload lost the page it is measured on"
    reads = _receipt_reads(seen)
    assert not reads, (
        "the page answers one boolean per line, and the receipts came back as their own round "
        f"trip: {len(reads)} read(s) of message_reads besides the page read — {reads}"
    )


async def test_reopening_a_chat_stays_within_six_trips(client: AsyncClient) -> None:
    """The round-trip ceiling on a second open: receipts no longer travel as their own query."""
    reader, _author, match_id = await _pair(client, "s50_ceiling")
    first = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(reader["token"])
    )
    assert first.status_code == 200, first.text

    resp, seen = await _counted(
        client,
        client.get(f"/api/v1/matches/{match_id}/messages", headers=auth_headers(reader["token"])),
    )
    assert resp.status_code == 200, resp.text
    assert len(seen) <= 6, (
        f"{len(seen)} trips to open a chat the reader has already read: {seen}"
    )


async def test_a_line_the_reader_has_not_seen_is_answered_unread(client: AsyncClient) -> None:
    """This same read writes the receipt, and still answers the page as it looked before it."""
    reader, _author, match_id = await _pair(client, "s50_unread")

    resp, _seen = await _counted(
        client,
        client.get(f"/api/v1/matches/{match_id}/messages", headers=auth_headers(reader["token"])),
    )
    assert resp.status_code == 200, resp.text
    lines = resp.json()["messages"]
    assert len(lines) == 3, resp.text
    assert not any(line["is_read"] for line in lines if not line["is_own"]), (
        "a line the reader never saw is answered as read: the flag was taken after the mark this "
        f"same call wrote — {[(l['body'], l['is_read']) for l in lines]}"
    )


async def test_a_reopened_page_answers_the_partner_lines_read(client: AsyncClient) -> None:
    """What the loaded collection used to answer, the flag answers: read means read."""
    reader, _author, match_id = await _pair(client, "s50_read")
    first = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(reader["token"])
    )
    assert first.status_code == 200, first.text

    second = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(reader["token"])
    )
    assert second.status_code == 200, second.text
    lines = second.json()["messages"]
    assert all(line["is_read"] for line in lines if not line["is_own"]), (
        f"the partner's lines are still shown unread after the reader opened them: {lines}"
    )


async def test_the_author_sees_their_own_line_read_only_after_the_partner_opens(
    client: AsyncClient,
) -> None:
    """The author's own receipt does not read their own line — that is `reader_id <> sender_id`."""
    reader, author, match_id = await _pair(client, "s50_author")

    sent = await client.post(
        f"/api/v1/matches/{match_id}/messages",
        headers=auth_headers(author["token"]),
        json={"body": "строка автора"},
    )
    assert sent.status_code == 201, sent.text
    own_id = sent.json()["id"]
    assert sent.json()["is_read"] is False, sent.text

    page = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(author["token"])
    )
    assert page.status_code == 200, page.text
    mine = [line for line in page.json()["messages"] if line["id"] == own_id]
    assert mine, "the author's new line is missing from the author's own page"
    assert mine[0]["is_read"] is False, (
        "the author's own receipt marked their own line read before the partner opened the chat: "
        f"{mine[0]}"
    )

    opened = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(reader["token"])
    )
    assert opened.status_code == 200, opened.text

    after = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(author["token"])
    )
    assert after.status_code == 200, after.text
    mine = [line for line in after.json()["messages"] if line["id"] == own_id]
    assert mine[0]["is_read"] is True, (
        f"the partner opened the chat and the author's line still answers unread: {mine[0]}"
    )
