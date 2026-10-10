"""A page of the conversation must contain its own newest line.

`ChatRepository.list_messages` takes the newest `limit + 1` rows of the window and hands them back
**ascending** (`rows.reverse()`), and `ChatService.history` then kept `lines[:limit]` — the first
`limit` of an ascending list, which is the *oldest* part of the page. The row it dropped was the
newest one it had just fetched, and the next page starts strictly below the oldest line shown, so
the dropped row fell between two pages and came back never.

Measured 2026-10-10 over a socket against one uvicorn worker on a 70-line thread
(`s53_page_pre.json`), walking the cursor exactly as `docs/API.md` documents it (page, oldest line
of the page, `before_id`): 13 requests returned **59 of the 70 lines**, no line twice, **11 lost**,
and the newest line of the thread was not on the first page. At the page size the phone uses the
same thread answers 50 lines whose last is `sequential-8` while the table's last is `sequential-9`,
and `GET /matches` puts `sequential-9` on the pair card — the list names a line the screen does not
show. The smallest gap between two writes on that stand was 22.35 ms (median 67.07 ms, 0 of 69 gaps
zero) with all 70 `created_at` values distinct, so none of this is a timestamp tie: the page was
cutting its own top row off.

What these checks hold: a thread longer than the page still shows its newest line; walking the
cursor to exhaustion returns every line exactly once; `has_more` promises only what the next page
can deliver; and the card and the screen name the same line. The last check in the file is a control
that was green before the fix and has to stay green: keeping the tail of the page must not cost the
conversation another round trip.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import event

from app.core.database import engine

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

PAGE = 5


async def _pair(client: AsyncClient, prefix: str) -> tuple[dict, dict, str]:
    reader = await register_and_auth(client, f"{prefix}_reader@befos.app")
    author = await register_and_auth(client, f"{prefix}_author@befos.app")
    await complete_onboarding(client, reader["token"], name="Вера", gender="female")
    await complete_onboarding(client, author["token"], name="Пётр", gender="male")
    await answer_all_questions(client, reader["token"])
    await answer_all_questions(client, author["token"])
    await client.post(
        f"/api/v1/users/{author['user_id']}/like", headers=auth_headers(reader["token"])
    )
    back = await client.post(
        f"/api/v1/users/{reader['user_id']}/like", headers=auth_headers(author["token"])
    )
    assert back.status_code == 200, back.text
    match_id = back.json()["match_id"]
    assert match_id
    return reader, author, match_id


async def _thread(client: AsyncClient, token: str, match_id: str, lines: int) -> list[str]:
    """Write `lines` messages, oldest first, and return their ids in that order."""
    ids = []
    for i in range(lines):
        sent = await client.post(
            f"/api/v1/matches/{match_id}/messages",
            headers=auth_headers(token),
            json={"body": f"строка {i}"},
        )
        assert sent.status_code == 201, sent.text
        ids.append(sent.json()["id"])
    return ids


async def _get_page(client: AsyncClient, token: str, match_id: str,
                    before_id: str | None = None) -> dict:
    params: dict[str, object] = {"limit": PAGE}
    if before_id is not None:
        params["before_id"] = before_id
    resp = await client.get(
        f"/api/v1/matches/{match_id}/messages", params=params, headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_a_thread_longer_than_the_page_shows_its_newest_line(client: AsyncClient) -> None:
    """Six lines, page of five: the sixth is the one a reader came for."""
    reader, author, match_id = await _pair(client, "s53_newest")
    await _thread(client, author["token"], match_id, PAGE + 1)

    page = await _get_page(client, reader["token"], match_id)
    bodies = [line["body"] for line in page["messages"]]
    assert bodies, "the first page came back empty"
    assert bodies[-1] == f"строка {PAGE}", (
        f"the page ends at {bodies[-1]!r} while the thread's newest line is "
        f"'строка {PAGE}': the newest row the read fetched was cut off the answer — {bodies}"
    )


async def test_walking_the_cursor_returns_every_line_exactly_once(client: AsyncClient) -> None:
    """The documented scroll: page, oldest line of the page, `before_id`, until nothing comes."""
    reader, author, match_id = await _pair(client, "s53_walk")
    lines = PAGE * 2 + 2
    written = await _thread(client, author["token"], match_id, lines)

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(lines):
        page = await _get_page(client, reader["token"], match_id, cursor)
        messages = page["messages"]
        if not messages:
            break
        seen.extend(line["id"] for line in messages)
        cursor = messages[0]["id"]

    assert len(seen) == len(set(seen)), (
        f"a line arrived twice while scrolling: {len(seen)} answers for {len(set(seen))} lines"
    )
    bodies = {line_id: f"строка {i}" for i, line_id in enumerate(written)}
    missing = [bodies[line_id] for line_id in written if line_id not in set(seen)]
    assert set(seen) == set(written), (
        f"{len(missing)} of {len(written)} lines never appear in any page: missing {missing}"
    )


async def test_has_more_promises_only_what_the_next_page_can_deliver(client: AsyncClient) -> None:
    """A page that says «there is more» must be followed by a page full of lines nobody has seen."""
    reader, author, match_id = await _pair(client, "s53_more")
    written = await _thread(client, author["token"], match_id, PAGE + 1)

    first = await _get_page(client, reader["token"], match_id)
    assert first["has_more"] is True, (
        f"{len(written)} lines with a page of {PAGE} must leave an older line queued: {first}"
    )
    shown = {line["id"] for line in first["messages"]}
    second = await _get_page(client, reader["token"], match_id, first["messages"][0]["id"])
    assert second["messages"], "has_more promised another page and the next page came back empty"
    repeats = {line["id"] for line in second["messages"]} & shown
    assert not repeats, f"the page after has_more returned lines the reader had already been given"


async def test_the_pair_card_names_a_line_the_screen_shows(client: AsyncClient) -> None:
    """`GET /matches` and `GET /messages` read the same thread and have to agree on its last line."""
    reader, author, match_id = await _pair(client, "s53_card")
    await _thread(client, author["token"], match_id, PAGE + 2)

    page = await _get_page(client, reader["token"], match_id)
    listed = await client.get("/api/v1/matches", headers=auth_headers(reader["token"]))
    assert listed.status_code == 200, listed.text
    card = next(m for m in listed.json()["matches"] if m["match_id"] == match_id)

    bodies = {line["body"] for line in page["messages"]}
    assert card["last_message"] in bodies, (
        f"the pair card ends with {card['last_message']!r}, which the chat page does not show at "
        f"all — the screen stops at {max(bodies, key=lambda b: int(b.split()[-1]))!r}"
    )


async def test_keeping_the_newest_line_costs_no_extra_trip(client: AsyncClient) -> None:
    """Control, green before the fix and required to stay green: the answer changes, the conversation does not."""
    reader, author, match_id = await _pair(client, "s53_control")
    await _thread(client, author["token"], match_id, PAGE + 1)
    await _get_page(client, reader["token"], match_id)

    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        page_resp = await _get_page(client, reader["token"], match_id)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)

    assert page_resp["messages"], "the controlled page lost its content"
    message_reads = [s for s in seen if s.startswith("select message_reads")]
    assert not message_reads, f"receipts went back to their own round trip: {message_reads}"
    assert len(seen) <= 6, f"{len(seen)} trips to open a chat the reader has already read: {seen}"
