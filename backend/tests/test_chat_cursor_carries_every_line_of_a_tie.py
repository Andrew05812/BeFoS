"""A page boundary that falls inside a tie must hand the rest of the tie to the next page.

`ChatRepository.list_messages` ranks a page by `(created_at DESC, id DESC)` — the second key exists
precisely because two lines can carry the same timestamp — but it cut the next page with
`Message.created_at < anchor.created_at`, which knows only the first key. So when the oldest line of
a page sat inside a group of lines sharing one `created_at`, the lines of that group which rank
below it by `id` were on neither page: this page was already full, and the next one asks for a
strictly smaller timestamp. `ChatRepository.chat_summaries` ranks the same rows by `created_at`
alone, so the pair card could name a line the screen never shows as its newest.

Measured 2026-10-10 on a stand conversation of 20 000 lines whose timestamps tie in groups of 20
(1 000 distinct `created_at`, `s54_cursor_pre.json`), walking the cursor exactly as `docs/API.md`
documents it: at the page size the phone uses, 335 requests returned **16 670 of the 20 000 lines,
no line twice, 3 330 lines in no page at all**; at a page of 5 it was 1 001 requests, 5 000 lines
seen and **15 000 lost**. Over the same data the screen answered `line-19998` as its newest line
while `GET /matches` put `line-19999` on the card — the two lines share
`2026-10-10T03:41:45.602977+00:00`, which is the whole disagreement.

These checks hold the fix: a tie group split by the boundary continues on the next page, a walk over
a tied thread returns every line exactly once, and the card and the screen name the same line. The
last check is a control that was green before the fix and has to stay green: a page taken with a
cursor costs seven trips to the base — the answer changes, the bill does not, and receipts must not
go back to their own statement.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models import Message

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

PAGE = 5
TIE = 8


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


async def _write_tie(session: AsyncSession, match_id: str, author_id: str, bodies: list[str]) -> None:
    """Put `bodies` into the conversation as lines that carry one and the same `created_at`.

    Written the way the shipped seed writes its dialog lines: the timestamp belongs to the row, and
    the clock the app process reads is not what is being tested here.
    """
    stamp = datetime.now(timezone.utc)
    for body in bodies:
        session.add(
            Message(
                match_id=uuid.UUID(match_id),
                sender_id=uuid.UUID(author_id),
                body=body,
                created_at=stamp,
                updated_at=stamp,
            )
        )
    await session.commit()


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


async def _walk(client: AsyncClient, token: str, match_id: str, pages: int) -> list[str]:
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(pages):
        page = await _get_page(client, token, match_id, cursor)
        messages = page["messages"]
        if not messages:
            break
        seen.extend(line["id"] for line in messages)
        cursor = messages[0]["id"]
    return seen


async def test_a_tie_split_by_the_boundary_continues_on_the_next_page(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Eight lines of one timestamp, a page of five: the next page owes the reader the other three."""
    reader, author, match_id = await _pair(client, "s54_split")
    await _write_tie(session, match_id, author["user_id"], [f"ничья {i}" for i in range(TIE)])

    first = await _get_page(client, reader["token"], match_id)
    assert len(first["messages"]) == PAGE, f"the page came back short: {first}"
    shown = {line["id"] for line in first["messages"]}
    second = await _get_page(client, reader["token"], match_id, first["messages"][0]["id"])

    missing = [i for i in range(TIE) if f"ничья {i}" not in
               {line["body"] for line in first["messages"]} | {line["body"] for line in second["messages"]}]
    assert len(second["messages"]) == TIE - PAGE, (
        f"the page after a boundary inside a tie returned {len(second['messages'])} of the "
        f"{TIE - PAGE} lines the tie still owed — {missing} of the tied lines are on no page"
    )
    assert not ({line["id"] for line in second["messages"]} & shown), (
        "the next page repeated a line the reader had already been given"
    )


async def test_walking_a_tied_thread_returns_every_line_exactly_once(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The scroll of the documented contract over three tied groups."""
    reader, author, match_id = await _pair(client, "s54_walk")
    bodies = [f"ничья {group}-{i}" for group in range(3) for i in range(TIE)]
    for group in range(3):
        await _write_tie(session, match_id, author["user_id"],
                         [f"ничья {group}-{i}" for i in range(TIE)])

    written = await _walk(client, reader["token"], match_id, pages=len(bodies))
    ids = {str(line_id) for line_id in await session.scalars(
        select(Message.id).where(Message.match_id == uuid.UUID(match_id))
    )}
    assert len(written) == len(set(written)), (
        f"a line arrived twice while scrolling a tied thread: {len(written)} answers for "
        f"{len(set(written))} lines"
    )
    assert set(written) == ids, (
        f"{len(ids - set(written))} of {len(ids)} lines of the tied thread never appear in any page"
    )


async def _write_tied_pair(session: AsyncSession, match_id: str, author_id: str) -> None:
    """Two lines on one timestamp, the smaller id written first: which one is «the latest» is decided
    by the tiebreaker, and both reads have to decide it the same way."""
    stamp = datetime.now(timezone.utc)
    for line_id, body in ((uuid.UUID(int=0x1111), "ничья с меньшим id, записана первой"),
                          (uuid.UUID(int=0xFFFF), "ничья с большим id, записана второй")):
        session.add(
            Message(
                id=line_id,
                match_id=uuid.UUID(match_id),
                sender_id=uuid.UUID(author_id),
                body=body,
                created_at=stamp,
                updated_at=stamp,
            )
        )
    await session.commit()


async def test_the_pair_card_names_the_line_the_page_calls_newest(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Card and screen read one conversation and must answer with one line, ties included."""
    reader, author, match_id = await _pair(client, "s54_card")
    await _write_tied_pair(session, match_id, author["user_id"])

    page = await _get_page(client, reader["token"], match_id)
    listed = await client.get("/api/v1/matches", headers=auth_headers(reader["token"]))
    assert listed.status_code == 200, listed.text
    card = next(m for m in listed.json()["matches"] if m["match_id"] == match_id)
    newest = page["messages"][-1]

    assert card["last_message"] == newest["body"], (
        f"the pair card ends with {card['last_message']!r} while the screen's newest line is "
        f"{newest['body']!r} — both lines are tied at {newest['created_at']}, and only one of the "
        f"two reads ranks the tie at all"
    )


async def test_the_wider_cut_costs_no_extra_trip(client: AsyncClient) -> None:
    """Control, green before the fix and required to stay green: the cut widens, the conversation does not.

    Read over a thread whose lines do not tie, so what is counted here is the price of the page and
    nothing else — the tied thread is the subject of the three checks above.
    """
    reader, author, match_id = await _pair(client, "s54_control")
    for i in range(2 * PAGE):
        sent = await client.post(
            f"/api/v1/matches/{match_id}/messages",
            headers=auth_headers(author["token"]),
            json={"body": f"строка {i}"},
        )
        assert sent.status_code == 201, sent.text

    first = await _get_page(client, reader["token"], match_id)
    assert len(first["messages"]) == PAGE, f"the first page came back short: {first}"
    cursor = first["messages"][0]["id"]

    seen: list[str] = []

    def record(conn, cur, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        second = await _get_page(client, reader["token"], match_id, cursor)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)

    assert second["messages"], "the controlled page lost its content"
    receipts = [s for s in seen if s.startswith("select message_reads")]
    assert not receipts, f"receipts went back to their own round trip: {receipts}"
    assert len(seen) <= 7, f"{len(seen)} trips for one page taken with a cursor: {seen}"
