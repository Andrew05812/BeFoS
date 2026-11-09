"""The pair list is read whole, and the order it answers in is decided after the reading (stage 126).

`MatchesService.list_matches` selects every pair of the account (`app/services/matches_service.py:30`),
builds a card for each of them, and only then sorts the finished list in Python by the newest line,
falling back to the moment the pair was made (`app/services/matches_service.py:71`). Nothing in the
answer names a page: `MatchListResponse` carries one field, `matches` (`app/schemas/schemas.py:535`),
and the route takes no parameter (`app/api/v1/matches.py:42`). So an account with a hundred pairs pays
for a hundred questionnaires, a hundred photographs and a hundred pair summaries on every opening of the
screen, and a person holding more pairs than the screen paints has no way to ask for the rest.

`docs/SCALE_PLAN.md` already priced the whole read: `matches_list` carries 4 statements at every scale
and its median moves with the account rather than with the page, because the rows behind those
statements grow with the pairs.

Two things have to move together, and the order matters. The sort key has to stop being a Python value:
a page resuming below a boundary must state that boundary in the terms the database orders by, so
`COALESCE(newest_message_at, match.created_at)` belongs in the query and the row's own id decides a tie
the timestamp cannot — the rule stage 54 wrote for the pair's history and stage 123 followed for the
tap list. And the reads that build the cards must follow the page, because asking for every partner's
profile is the part of the price that grows with the account.

What must not move, and is checked here so it cannot drift: one pass over `messages` per answer (the
bargain stage 33 struck and `test_matches_list_messages_read.py` guards), newest activity first with the
pair's own moment as the fallback, the `unread` counter and the leading line a card carries, the
visibility rule that drops a partner who hid or was deleted, and the account export — that document is a
person's own data and names its own ceiling (`ROWS_PER_SECTION`), so it goes on reading every pair
however short the screen's page is.
"""

from __future__ import annotations

import base64
import uuid
from collections import Counter
from datetime import date, timedelta
from typing import NamedTuple

import pytest
from httpx import AsyncClient
from sqlalchemy import event, insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models import Match, Message, Profile, User
from app.models.base import utcnow
from app.services.discovery_service import BAD_CURSOR

from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)

BIRTH = date(1996, 5, 10)
PAIRS = "/api/v1/matches"
INBOX = "/api/v1/discover/liked-me"
LIKED = "/api/v1/discover/liked"
PAGE = 50


class Pair(NamedTuple):
    """One row of `matches` and the partner it points at, as the seed knows them."""

    pair_id: uuid.UUID
    peer_id: uuid.UUID

    @property
    def match_id(self) -> str:
        return str(self.pair_id)


async def _account(client: AsyncClient, email: str, *, name: str = "Вера") -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name)
    await answer_all_questions(client, creds["token"])
    return creds


async def _pair_rows(
    session: AsyncSession,
    reader_id: str,
    count: int,
    *,
    tag: str,
    minutes_apart: int = 5,
) -> list[Pair]:
    """Pairs written straight into `matches`, newest first in the order the door reads them.

    Each partner arrives with the profile a card reads, and each pair carries the score the like stored,
    so a card answers with its number without the engine being asked again.
    """
    peers = [uuid.uuid4() for _ in range(count)]
    await session.execute(
        insert(User),
        [
            {
                "id": uid,
                "email": f"s126_{tag}_p{i}@befos.app",
                "password_hash": "not-a-real-hash",
                "is_active": True,
                "is_deleted": False,
                "is_verified": True,
            }
            for i, uid in enumerate(peers)
        ],
    )
    await session.execute(
        insert(Profile),
        [
            {
                "id": uuid.uuid4(),
                "user_id": uid,
                "name": f"Пара {i}",
                "birth_date": BIRTH,
                "gender": "male",
                "city": "Казань",
                "dating_goal": "relationship",
                "lifestyle": {},
                "is_hidden": False,
                "onboarding_completed_at": utcnow(),
            }
            for i, uid in enumerate(peers)
        ],
    )
    newest = utcnow()
    rows = [
        {
            "id": uuid.uuid4(),
            "user_a_id": uuid.UUID(reader_id),
            "user_b_id": peer,
            "compatibility_score": 0.64,
            "created_at": newest - timedelta(minutes=minutes_apart * i),
        }
        for i, peer in enumerate(peers)
    ]
    await session.execute(insert(Match), rows)
    await session.commit()
    return [Pair(row["id"], row["user_b_id"]) for row in rows]


async def _say(
    session: AsyncSession, pair: Pair, *, body: str, at, read_by: str | None = None
) -> None:
    """One line from the partner, and optionally the reader's receipt of it."""
    from app.models import MessageRead

    message_id = uuid.uuid4()
    await session.execute(
        insert(Message),
        {
            "id": message_id,
            "match_id": pair.pair_id,
            "sender_id": pair.peer_id,
            "body": body,
            "client_msg_id": f"s126-{uuid.uuid4().hex[:12]}",
            "created_at": at,
        },
    )
    if read_by is not None:
        await session.execute(
            insert(MessageRead),
            {
                "id": uuid.uuid4(),
                "message_id": message_id,
                "reader_id": uuid.UUID(read_by),
                "read_at": at,
            },
        )
    await session.commit()


async def _page(client: AsyncClient, token: str, **params) -> dict:
    resp = await client.get(PAIRS, headers=auth_headers(token), params=params)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "next_cursor" in body, (
        f"the pair list answered {sorted(body)}: a screen that can hold more pairs than it paints has "
        "to be handed the key that reaches the rest"
    )
    return body


async def _raw(client: AsyncClient, token: str, **params) -> tuple[int, str]:
    resp = await client.get(PAIRS, headers=auth_headers(token), params=params)
    return resp.status_code, resp.text


def _ids(body: dict) -> list[str]:
    return [row["match_id"] for row in body["matches"]]


_MARKERS = {
    "pairs": "from matches",
    "messages": "from messages",
    "cards": "from profiles",
    "photos": "from photos",
}


def _counts(seen: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for statement in seen:
        for name, marker in _MARKERS.items():
            if marker in statement:
                counts[name] += 1
    return counts


def _widest_id_list(seen: list[str], marker: str) -> int:
    """How many ids the widest read over `marker` asked for — a page or the whole account.

    Counted from the statement the database actually received (`IN ($1, $2, …$n)`) rather than from what
    the service was told to do, because the defect this stage closes is a read that grows with the
    account while the answer stays the size of a page.
    """
    widths = [s.split(marker, 1)[1].count("$") for s in seen if marker in s]
    return max(widths, default=0)


async def _counted_page(client: AsyncClient, token: str, **params) -> tuple[dict, list[str]]:
    seen: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    try:
        body = await _page(client, token, **params)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)
    return body, seen


async def _walk(client: AsyncClient, token: str, *, limit: int) -> list[str]:
    ids: list[str] = []
    cursor: str | None = None
    for _ in range(200):
        params: dict = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        body = await _page(client, token, **params)
        ids.extend(_ids(body))
        if not body["has_more"]:
            assert body["next_cursor"] is None, (
                "the last page of pairs says nothing stands behind it and still hands a way forward"
            )
            return ids
        cursor = body["next_cursor"]
        assert cursor, "a page of pairs that promises more answers no cursor to reach them"
    raise AssertionError("the walk over pairs never ended")


async def test_a_page_of_pairs_hands_over_the_way_forward(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The screen paints a page; the answer has to name the rest."""
    reader = await _account(client, "s126_pairs_fwd@befos.app")
    rows = await _pair_rows(session, reader["user_id"], PAGE + 3, tag="fwd")

    body = await _page(client, reader["token"])

    assert len(body["matches"]) == PAGE, "the default page of pairs changed size with this stage"
    assert body["has_more"] is True
    assert isinstance(body["next_cursor"], str) and body["next_cursor"], (
        "the answer admits more pairs exist and gives no cursor to reach them"
    )
    assert _ids(body) == [row.match_id for row in rows[:PAGE]], "the newest pairs are not the first page"


async def test_the_cursor_opens_the_pairs_that_stood_behind_the_first_page(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Page two is the rest of the list, not a second copy of the first page."""
    reader = await _account(client, "s126_pairs_second@befos.app")
    rows = await _pair_rows(session, reader["user_id"], PAGE + 3, tag="second")
    first = await _page(client, reader["token"])

    second = await _page(client, reader["token"], cursor=first["next_cursor"])

    assert _ids(second) == [row.match_id for row in rows[PAGE:]], (
        "the cursor reopened pairs the first page had already named"
    )
    assert second["has_more"] is False
    assert second["next_cursor"] is None


async def test_a_walk_over_every_page_names_each_pair_exactly_once(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Pages are a partition of the list: no pair between them lost, no pair twice."""
    reader = await _account(client, "s126_pairs_walk@befos.app")
    rows = await _pair_rows(session, reader["user_id"], 23, tag="walk", minutes_apart=3)

    assert Counter(await _walk(client, reader["token"], limit=7)) == Counter(
        [row.match_id for row in rows]
    )


async def test_the_page_is_ordered_by_the_newest_line_and_falls_back_to_the_pair(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The rule the screen paints by moves into the query unchanged.

    Three pairs, made in the order backlog, read, silent: the empty pair is the newest of the three by
    its own row, the two spoken pairs stand by their last line. This is the bargain
    `test_matches_list_messages_read.py` strikes about the whole list, asked of a page — a page cannot be
    drawn from a key the query does not know.
    """
    reader = await _account(client, "s126_pairs_order@befos.app")
    backlog = (await _pair_rows(session, reader["user_id"], 1, tag="order_backlog"))[0]
    read = (await _pair_rows(session, reader["user_id"], 1, tag="order_read"))[0]
    silent = (await _pair_rows(session, reader["user_id"], 1, tag="order_silent"))[0]
    base = utcnow()
    await _say(session, backlog, body="backlog line", at=base - timedelta(hours=3))
    await _say(
        session, read, body="read line", at=base - timedelta(hours=1), read_by=reader["user_id"]
    )

    body = await _page(client, reader["token"])

    assert _ids(body) == [silent.match_id, read.match_id, backlog.match_id], (
        "a page ordered by anything but «the newest line, else the pair's own moment» is a different list"
    )
    card = body["matches"][1]
    assert card["last_message"] == "read line", card
    assert card["unread"] == 0, f"the reader opened this pair, and the card still counts {card['unread']}"
    waiting = body["matches"][2]
    assert waiting["unread"] == 1 and waiting["last_message"] == "backlog line", waiting


async def test_pairs_whose_newest_lines_share_a_moment_are_split_by_the_row_id(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The tie belongs to the key, because a boundary cannot be drawn through a coin flip.

    A page that resumes strictly below a moment has to know which of two pairs standing on that moment it
    already showed. Python's stable sort decided that once, in memory, for one answer; the same question
    asked across two answers needs a value the row carries. `uuid` compares bytewise in both PostgreSQL
    and Python, so the expected order is computed here rather than remembered.
    """
    reader = await _account(client, "s126_pairs_tie@befos.app")
    rows = await _pair_rows(session, reader["user_id"], 6, tag="tie", minutes_apart=0)
    at = utcnow()
    for row in rows:
        await _say(session, row, body="one moment", at=at)

    seen = await _walk(client, reader["token"], limit=2)

    expected = [row.match_id for row in sorted(rows, key=lambda r: r.pair_id, reverse=True)]
    assert seen == expected, (
        f"6 pairs sharing one newest-line moment walked as {seen}; the tie is not decided by the row id"
    )


async def test_a_page_costs_one_pass_over_messages_and_names_only_its_own_partners(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The card reads follow the page; the message pass stays one statement.

    Stage 33 paid for a single walk over `messages` no matter how many pairs the list carried, and this
    stage must not buy its page by reading that table twice. The half that changes is the shape of the
    other reads: a page of twenty pairs asking for a hundred partner profiles is the growth this door is
    accused of, so the widest id list a page sends has to be the page, not the account.
    """
    reader = await _account(client, "s126_pairs_price@befos.app")
    await _pair_rows(session, reader["user_id"], 60, tag="price")

    body, seen = await _counted_page(client, reader["token"], limit=20)

    assert len(body["matches"]) == 20
    counts = _counts(seen)
    assert counts["messages"] == 1, (
        f"the page read messages {counts['messages']} times: the newest line and the counter walked the "
        "same rows in two statements again"
    )
    for name in ("pairs", "cards", "photos"):
        assert counts[name] == 1, f"the page read {name} {counts[name]} times"
    for marker in ("from profiles", "from photos"):
        width = _widest_id_list(seen, marker)
        assert 0 < width <= 20, (
            f"the page read {marker} over {width} ids — a page of 20 pairs must not ask for the "
            "account's whole list"
        )


async def test_a_page_behind_the_first_costs_what_the_first_costs(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The boundary travels in the link, so turning a page adds no lookup of where the reader stood.

    A cursor that carried a position and needed its anchor row read would put a fifth statement on every
    page after the first, and the row published for `matches_list` would stop being the price of the door.
    """
    reader = await _account(client, "s126_pairs_deep@befos.app")
    await _pair_rows(session, reader["user_id"], 45, tag="deep", minutes_apart=2)
    first, first_seen = await _counted_page(client, reader["token"], limit=20)
    assert first["next_cursor"]

    second, second_seen = await _counted_page(
        client, reader["token"], cursor=first["next_cursor"], limit=20
    )

    assert len(second["matches"]) == 20
    assert len(second_seen) == len(first_seen), (
        f"page one cost {len(first_seen)} statements and page two cost {len(second_seen)}: the cursor "
        "is being looked up rather than carried"
    )


async def test_the_page_size_keeps_its_bounds(client: AsyncClient) -> None:
    """Zero asks the database for no rows and one past the cap asks for a page nobody can paint."""
    reader = await _account(client, "s126_pairs_bounds@befos.app")

    for bad in (0, PAGE + 1, -3):
        code, text = await _raw(client, reader["token"], limit=bad)
        assert code == 422, f"limit={bad} answered {code}: {text[:120]}"

    code, text = await _raw(client, reader["token"], limit=PAGE)
    assert code == 200, text


async def test_a_link_nobody_handed_out_is_refused_as_input(client: AsyncClient) -> None:
    """A broken link is a bad link, not an empty page."""
    reader = await _account(client, "s126_pairs_tampered@befos.app")

    for bad in ("not-a-cursor", "%%%", "dGVwADE6MDow.Zm9v", base64.urlsafe_b64encode(b"rank:3").decode()):
        code, text = await _raw(client, reader["token"], cursor=bad)
        assert code == 422, f"cursor={bad!r} answered {code}: {text[:160]}"
        assert BAD_CURSOR in text, f"cursor={bad!r} refused with another sentence: {text[:160]}"

    code, text = await _raw(client, reader["token"], cursor="")
    assert code == 200, f"an empty cursor was refused rather than read as the top of the list: {text}"


async def test_a_link_carried_from_another_door_or_another_account_is_refused(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A link belongs to one list of one reader, and both halves of that claim are checked.

    The tap list's link and the pair list's link are opaque strings of the same shape, and a stranger's
    link is an opaque string too. Read across a door or across an account, a moment and a row id name a
    place that does not exist for the reader asking — so the answer is the refusal the other doors give,
    with the same sentence and nothing about the mechanism behind it.
    """
    reader = await _account(client, "s126_pairs_borrow@befos.app")
    stranger = await _account(client, "s126_pairs_borrow_s@befos.app", name="Пётр")
    await _pair_rows(session, reader["user_id"], 12, tag="borrow", minutes_apart=2)
    await _pair_rows(session, stranger["user_id"], 12, tag="borrow_s", minutes_apart=2)
    theirs = (await _page(client, stranger["token"], limit=5))["next_cursor"]

    code, text = await _raw(client, reader["token"], cursor=theirs)
    assert code == 422, f"a stranger's pair link turned the reader's list with {code}: {text[:160]}"
    assert BAD_CURSOR in text

    mine = (await _page(client, reader["token"], limit=5))["next_cursor"]
    for other in (INBOX, LIKED):
        resp = await client.get(other, headers=auth_headers(reader["token"]), params={"cursor": mine})
        assert resp.status_code == 422, (
            f"a pair link turned {other} with {resp.status_code}: {resp.text[:160]}"
        )


async def test_a_partner_whose_account_is_gone_is_named_by_no_page(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The rule that hides a partner belongs to the list, not to its first page.

    What this door drops is a partner whose own row no longer answers: a card has nowhere to take a
    name, an age and a photograph from. `test_matches_list_column_read.py` pins that for the whole
    list, and a page boundary must not be a second door through the same rule — a person who deleted
    their account is not named by the tail of somebody's pair list.
    """
    reader = await _account(client, "s126_pairs_gone@befos.app")
    rows = await _pair_rows(session, reader["user_id"], PAGE + 3, tag="gone")
    gone = rows[PAGE + 1]
    await session.execute(
        update(User).where(User.id == gone.peer_id).values(is_deleted=True, is_active=False)
    )
    await session.commit()

    first = await _page(client, reader["token"])
    second = await _page(client, reader["token"], cursor=first["next_cursor"])

    listed = _ids(first) + _ids(second)
    assert gone.match_id not in listed, "a partner whose account is gone is named past the boundary"
    assert len(listed) == PAGE + 2, (
        f"the walk of 53 pairs with one partner gone answered {len(listed)} cards"
    )


async def test_a_pair_dissolved_while_the_reader_stands_on_page_one_leaves_the_walk_whole(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The row that leaves between two pages must not swallow the page behind it.

    `DELETE /matches/{id}` is the reader's own door out of a pair, and it removes the very row a boundary
    can be drawn on. A cursor that looked its anchor row up would answer the dissolution with a missing
    row and stop the walk; a keyset link carries the values, so the tail keeps coming.
    """
    reader = await _account(client, "s126_pairs_dissolve@befos.app")
    rows = await _pair_rows(session, reader["user_id"], 14, tag="dissolve", minutes_apart=2)
    first = await _page(client, reader["token"], limit=5)
    assert _ids(first) == [row.match_id for row in rows[:5]]

    dropped = rows[2]
    resp = await client.delete(
        f"/api/v1/matches/{dropped.pair_id}", headers=auth_headers(reader["token"])
    )
    # The door answers with nothing at all: a pair that is gone has no page left to describe, and
    # stage 105 chose the empty 204 over a body naming which pair used to be here.
    assert resp.status_code == 204, resp.text

    tail: list[str] = []
    cursor: str | None = first["next_cursor"]
    while cursor is not None:
        body = await _page(client, reader["token"], cursor=cursor, limit=5)
        tail.extend(_ids(body))
        cursor = body["next_cursor"]

    assert tail == [row.match_id for row in rows[5:]], (
        f"the pages after a dissolution answered {tail} instead of the pairs still standing"
    )


async def test_an_account_without_pairs_answers_the_same_shape(client: AsyncClient) -> None:
    """Empty, full and paged are one shape: the screen does not branch on which one it got."""
    reader = await _account(client, "s126_pairs_empty@befos.app")

    body = await _page(client, reader["token"])

    assert body["matches"] == []
    assert body["has_more"] is False
    assert body["next_cursor"] is None


async def test_a_link_turned_twice_answers_the_same_page(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A link is a place in the list, so asking for it twice gets the same page twice."""
    reader = await _account(client, "s126_pairs_replay@befos.app")
    rows = await _pair_rows(session, reader["user_id"], 12, tag="replay", minutes_apart=3)
    first = await _page(client, reader["token"], limit=4)
    assert _ids(first) == [row.match_id for row in rows[:4]]
    held = first["next_cursor"]

    again = await _page(client, reader["token"], cursor=held, limit=4)
    once = await _page(client, reader["token"], cursor=held, limit=4)

    assert _ids(again) == [row.match_id for row in rows[4:8]]
    assert again == once, "the same link answered differently the second time it was turned"
