"""The inbox and the pass list stop at fifty, and the answer gives no way past the stop (stage 126).

`docs/RELEASE.md` §11 names these two doors by their constants: `LIKED_ME_SHOWN = 50` and
`PASSED_SHOWN = 50` (`app/services/discovery_service.py:39,43`) cut a newest-first read, and
`has_more` admits the rest exists. The admission is the problem: `GET /discover/liked-me` and
`GET /discover/passed` take no `cursor` at all (`app/api/v1/discover.py:41,82`), so the person who was
tapped two hundred times is walked to their fiftieth card and stopped, and the screen that says
«за ними ждут другие» has no verb for the rest.

Stage 123 already built the mechanism for the third door of the same family — the account's own taps —
and priced it: a keyset over `(created_at, id)`, an opaque link, the refusal of a link nobody handed
out. This file asks for the same at the two doors that never got it, because the rows are read the same
way: both are newest-first gestures, both order by `(created_at, id)` in `social_repo` already, and the
id is in the key for the reason stage 54 wrote down — two swipes inside one microsecond are the normal
case once a deck is walked fast, and a boundary drawn through the timestamp alone loses the rows that
share it.

The link is not a client's claim here. Stage 126 also signs it, so a hand-built payload is refused
rather than read, and one door's link does not turn another's page. What deliberately does not change:
the default page still carries fifty rows, the cards keep the fields they carry today, and the rows
behind the link are the same rows the visibility rules already decided about — a hidden, deleted or
blocked person does not slip in through page two.
"""

from __future__ import annotations

import base64
import importlib.util
import inspect
import uuid
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import event, insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models import Like, Pass, Profile, User
from app.models.base import utcnow
from app.services.discovery_service import BAD_CURSOR, LIKED_ME_SHOWN, PASSED_SHOWN

from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)

BIRTH = date(1996, 5, 10)
INBOX = "/api/v1/discover/liked-me"
PASSED = "/api/v1/discover/passed"

_PROBE_PATH = Path(__file__).resolve().parents[1] / "ops" / "scale_probe.py"


async def _account(client: AsyncClient, tag: str, *, name: str = "Вера") -> dict:
    creds = await register_and_auth(client, f"s126_{tag}@befos.app")
    await complete_onboarding(client, creds["token"], name=name)
    await answer_all_questions(client, creds["token"])
    return creds


def _rows(body: dict) -> list[str]:
    """The people a page named, in the order it named them — whichever of the two doors answered."""
    key = "likes" if "likes" in body else "passed"
    return [card["user_id"] for card in body[key]]


async def _page(client: AsyncClient, token: str, url: str, **params) -> dict:
    resp = await client.get(url, headers=auth_headers(token), params=params)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "next_cursor" in body, (
        f"{url} answered {sorted(body)}: a door that says more rows stand behind what it named has to "
        "hand over the key that reaches them"
    )
    return body


async def _raw(client: AsyncClient, token: str, url: str, **params) -> tuple[int, str]:
    resp = await client.get(url, headers=auth_headers(token), params=params)
    return resp.status_code, resp.text


async def _people(
    session: AsyncSession, count: int, *, tag: str, name_prefix: str = "Сосед"
) -> list[uuid.UUID]:
    """Showable accounts, written straight into the tables: this is about reading a page of rows.

    The rows carry a profile with the fields a card reads, so a page that dropped the join would fail
    on names rather than on a mystery, and every account is visible — the visibility rules have their
    own test below, where one of them is deliberately broken.
    """
    ids = [uuid.uuid4() for _ in range(count)]
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
            for i, uid in enumerate(ids)
        ],
    )
    await session.execute(
        insert(Profile),
        [
            {
                "id": uuid.uuid4(),
                "user_id": uid,
                "name": f"{name_prefix} {i}",
                "birth_date": BIRTH,
                "gender": "male",
                "city": "Казань",
                "dating_goal": "relationship",
                "lifestyle": {},
                "is_hidden": False,
                "onboarding_completed_at": utcnow(),
            }
            for i, uid in enumerate(ids)
        ],
    )
    await session.commit()
    return ids


async def _seed_inbox(
    session: AsyncSession, viewer_id: str, count: int, *, tag: str, minutes_apart: int = 5
) -> list[str]:
    """Taps pointing *at* the viewer, newest first in the order the door reads them."""
    ids = await _people(session, count, tag=tag)
    newest = utcnow()
    await session.execute(
        insert(Like),
        [
            {
                "id": uuid.uuid4(),
                "from_user_id": uid,
                "to_user_id": uuid.UUID(viewer_id),
                "compatibility_score": 0.7,
                "created_at": newest - timedelta(minutes=minutes_apart * i),
            }
            for i, uid in enumerate(ids)
        ],
    )
    await session.commit()
    return [str(uid) for uid in ids]


async def _seed_passes(
    session: AsyncSession, viewer_id: str, count: int, *, tag: str, minutes_apart: int = 5
) -> list[str]:
    """The viewer's own dismissals, written as rows: a pass is a swipe, and a swipe is a row."""
    ids = await _people(session, count, tag=tag)
    newest = utcnow()
    await session.execute(
        insert(Pass),
        [
            {
                "id": uuid.uuid4(),
                "from_user_id": uuid.UUID(viewer_id),
                "to_user_id": uid,
                "created_at": newest - timedelta(minutes=minutes_apart * i),
            }
            for i, uid in enumerate(ids)
        ],
    )
    await session.commit()
    return [str(uid) for uid in ids]


_MARKERS = {"rows": "from likes", "cards": "from profiles", "photos": "from photos"}
_PASS_MARKERS = {"rows": "from passes", "cards": "from profiles", "photos": "from photos"}


def _listener(seen: list[str]) -> Callable[..., None]:
    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    return _record


def _counts(seen: list[str], markers: dict[str, str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for statement in seen:
        for name, marker in markers.items():
            if marker in statement:
                counts[name] += 1
    return counts


async def _counted_page(
    client: AsyncClient, token: str, url: str, markers: dict[str, str], **params
) -> tuple[dict, Counter[str], int]:
    """One call, its answer, and what the database was asked to do for it."""
    seen: list[str] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        body = await _page(client, token, url, **params)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    return body, _counts(seen, markers), len(seen)


async def _walk(
    client: AsyncClient, token: str, url: str, *, limit: int, field: str
) -> list[str]:
    """Every page in order, following nothing but the links the server handed out."""
    ids: list[str] = []
    cursor: str | None = None
    for _ in range(200):  # a guard against a link that points at where it already was
        params: dict = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        body = await _page(client, token, url, **params)
        ids.extend(card["user_id"] for card in body[field])
        if not body["has_more"]:
            assert body["next_cursor"] is None, (
                f"{url} says nothing stands behind its last page and still hands over a way forward"
            )
            return ids
        cursor = body["next_cursor"]
        assert cursor, f"{url} promised more rows and answered no cursor to reach them"
    raise AssertionError("the walk never ended")


_DOORS = [
    pytest.param(INBOX, "likes", LIKED_ME_SHOWN, id="inbox"),
    pytest.param(PASSED, "passed", PASSED_SHOWN, id="pass-list"),
]


@pytest.mark.parametrize(("url", "field", "cap"), _DOORS)
async def test_a_page_that_stopped_at_fifty_hands_over_the_way_forward(
    client: AsyncClient, session: AsyncSession, url: str, field: str, cap: int
) -> None:
    """`has_more` has to come with something a reader can act on, at both doors."""
    viewer = await _account(client, f"fwd_{field}")
    if field == "likes":
        ids = await _seed_inbox(session, viewer["user_id"], cap + 5, tag=f"fwd_{field}")
    else:
        ids = await _seed_passes(session, viewer["user_id"], cap + 5, tag=f"fwd_{field}")

    body = await _page(client, viewer["token"], url)

    assert len(body[field]) == cap, "the default page changed size with this stage"
    assert body["has_more"] is True
    assert isinstance(body["next_cursor"], str) and body["next_cursor"], (
        f"{url} admits more rows exist and gives no cursor to reach them"
    )
    assert _rows(body) == ids[:cap]


@pytest.mark.parametrize(("url", "field", "cap"), _DOORS)
async def test_the_cursor_opens_the_rows_that_stood_behind_the_first_page(
    client: AsyncClient, session: AsyncSession, url: str, field: str, cap: int
) -> None:
    """Page two is the rest of the list, not a second copy of the first page."""
    viewer = await _account(client, f"second_{field}")
    if field == "likes":
        ids = await _seed_inbox(session, viewer["user_id"], cap + 5, tag=f"second_{field}")
    else:
        ids = await _seed_passes(session, viewer["user_id"], cap + 5, tag=f"second_{field}")
    first = await _page(client, viewer["token"], url)

    second = await _page(client, viewer["token"], url, cursor=first["next_cursor"])

    assert _rows(second) == ids[cap:], "the cursor reopened rows the first page had already named"
    assert second["has_more"] is False
    assert second["next_cursor"] is None


@pytest.mark.parametrize(("url", "field", "cap"), _DOORS)
async def test_a_walk_over_every_page_names_each_row_exactly_once(
    client: AsyncClient, session: AsyncSession, url: str, field: str, cap: int
) -> None:
    """Pages are a partition of the list: no row between them lost, no row twice."""
    viewer = await _account(client, f"walk_{field}")
    if field == "likes":
        ids = await _seed_inbox(session, viewer["user_id"], 23, tag=f"walk_{field}", minutes_apart=1)
    else:
        ids = await _seed_passes(session, viewer["user_id"], 23, tag=f"walk_{field}", minutes_apart=1)

    seen = await _walk(client, viewer["token"], url, limit=7, field=field)

    assert Counter(seen) == Counter(ids), (
        f"23 rows walked as {len(seen)} cards, {len(set(seen))} of them distinct at {url}"
    )


@pytest.mark.parametrize(("url", "field", "cap"), _DOORS)
async def test_rows_written_at_the_same_moment_do_not_fall_between_two_pages(
    client: AsyncClient, session: AsyncSession, url: str, field: str, cap: int
) -> None:
    """The boundary is the pair `(created_at, id)`, because the timestamp alone is not a total order.

    Stage 54 proved the loss for the pair's history and stage 123 for the tap list: rows sharing a
    microsecond sit on both sides of a boundary drawn through `created_at`, so the page that resumes
    strictly older never reads them. Both of these reads order by the same pair, so both inherit the
    same requirement.
    """
    viewer = await _account(client, f"tie_{field}")
    if field == "likes":
        ids = await _seed_inbox(session, viewer["user_id"], 12, tag=f"tie_{field}", minutes_apart=0)
    else:
        ids = await _seed_passes(session, viewer["user_id"], 12, tag=f"tie_{field}", minutes_apart=0)

    seen = await _walk(client, viewer["token"], url, limit=5, field=field)

    assert Counter(seen) == Counter(ids), (
        f"12 rows at one microsecond walked as {len(seen)} cards, {len(set(seen))} distinct at {url}"
    )


@pytest.mark.parametrize(("url", "field", "cap"), _DOORS)
async def test_the_page_size_keeps_its_bounds(
    client: AsyncClient, session: AsyncSession, url: str, field: str, cap: int
) -> None:
    """Zero asks the database for no rows and one past the cap asks for a page nobody can paint."""
    viewer = await _account(client, f"bounds_{field}")

    for bad in (0, cap + 1, -3):
        code, text = await _raw(client, viewer["token"], url, limit=bad)
        assert code == 422, f"{url} limit={bad} answered {code}: {text[:120]}"

    code, text = await _raw(client, viewer["token"], url, limit=cap)
    assert code == 200, text


@pytest.mark.parametrize(("url", "field", "cap"), _DOORS)
async def test_a_smaller_page_can_be_asked_for_and_the_walk_still_covers_the_list(
    client: AsyncClient, session: AsyncSession, url: str, field: str, cap: int
) -> None:
    """The cap is the default, not the only page size the door answers with."""
    viewer = await _account(client, f"small_{field}")
    if field == "likes":
        ids = await _seed_inbox(session, viewer["user_id"], 12, tag=f"small_{field}", minutes_apart=1)
    else:
        ids = await _seed_passes(
            session, viewer["user_id"], 12, tag=f"small_{field}", minutes_apart=1
        )

    body = await _page(client, viewer["token"], url, limit=4)

    assert len(body[field]) == 4
    assert body["has_more"] is True
    assert _rows(body) == ids[:4]
    assert await _walk(client, viewer["token"], url, limit=4, field=field) == ids


@pytest.mark.parametrize(("url", "field", "cap"), _DOORS)
async def test_a_link_nobody_handed_out_is_refused_as_input(
    client: AsyncClient, session: AsyncSession, url: str, field: str, cap: int
) -> None:
    """A broken link is a bad link, not an empty page.

    Answering an empty list would let a mistyped or a hand-built cursor look like the end of the list,
    and the screen would stop loading and say the account has nothing more. Both doors answer with the
    deck's sentence, because «the link to the next page is broken» is one fact about three lists.
    """
    viewer = await _account(client, f"tampered_{field}")

    for bad in (
        "not-a-cursor",
        "%%%",
        base64.urlsafe_b64encode(b"tap:1730000000000000:" + b"0" * 32).decode().rstrip("="),
        base64.urlsafe_b64encode(b"rank:3").decode().rstrip("="),
    ):
        code, text = await _raw(client, viewer["token"], url, cursor=bad)
        assert code == 422, f"{url} cursor={bad!r} answered {code}: {text[:160]}"
        assert BAD_CURSOR in text, f"{url} cursor={bad!r} refused with another sentence: {text[:160]}"

    # An absent cursor and an empty one are the same question: start from the newest row.
    code, text = await _raw(client, viewer["token"], url, cursor="")
    assert code == 200, f"an empty cursor was refused rather than read as the top of the list: {text}"


@pytest.mark.parametrize(("url", "field", "cap"), _DOORS)
async def test_a_link_carried_from_the_other_door_is_refused(
    client: AsyncClient, session: AsyncSession, url: str, field: str, cap: int
) -> None:
    """Two doors, two kinds of link: the other door's place is not a place in this list.

    Both cursors are opaque base64url strings of the same shape, so nothing but the kind the server
    signed decides whether one opens the other's page. Read across, the moment and the id would name a
    row of a different table, and the page would answer with rows the reader never asked about rather
    than refuse.
    """
    other = PASSED if url == INBOX else INBOX
    other_field = "passed" if field == "likes" else "likes"
    viewer = await _account(client, f"cross_{field}")
    # Two different tags, because both seeds write the same people rows and an email is unique: the
    # point is a link issued by one door, and it must not be paid for with a constraint violation.
    if field == "likes":
        await _seed_inbox(session, viewer["user_id"], 12, tag=f"cross_{field}", minutes_apart=1)
        await _seed_passes(session, viewer["user_id"], 12, tag=f"cross_{field}_p", minutes_apart=1)
    else:
        await _seed_passes(session, viewer["user_id"], 12, tag=f"cross_{field}", minutes_apart=1)
        await _seed_inbox(session, viewer["user_id"], 12, tag=f"cross_{field}_i", minutes_apart=1)
    borrowed = (await _page(client, viewer["token"], other, limit=5))["next_cursor"]

    code, text = await _raw(client, viewer["token"], url, cursor=borrowed, limit=5)

    assert code == 422, f"a link from {other} turned {url} with {code}: {text[:160]}"


@pytest.mark.parametrize(("url", "field", "cap"), _DOORS)
async def test_a_link_carried_from_another_account_is_refused(
    client: AsyncClient, session: AsyncSession, url: str, field: str, cap: int
) -> None:
    """A place in somebody's list belongs to that person, and the server knows whose it was.

    Stage 123 could only promise that a borrowed link reads the reader's own rows: the cursor carried a
    moment and a row id, and the read filtered by its own `from_user_id`. That is safe but not honest —
    the link was still somebody's claim, and the reader of a shared device could turn another person's
    link at their own door and get a page whose boundary was chosen by a stranger. A signed link names
    the account it was issued to, so the refusal here is the requirement, not a side effect.
    """
    viewer = await _account(client, f"stolen_{field}_v", name="Вера")
    stranger = await _account(client, f"stolen_{field}_s", name="Пётр")
    mine = (
        await _seed_inbox(session, viewer["user_id"], 12, tag=f"stolen_{field}", minutes_apart=7)
        if field == "likes"
        else await _seed_passes(session, viewer["user_id"], 12, tag=f"stolen_{field}", minutes_apart=7)
    )
    theirs = (
        await _seed_inbox(session, stranger["user_id"], 12, tag=f"stolen_{field}_b", minutes_apart=1)
        if field == "likes"
        else await _seed_passes(
            session, stranger["user_id"], 12, tag=f"stolen_{field}_b", minutes_apart=1
        )
    )
    borrowed = (await _page(client, stranger["token"], url, limit=5))["next_cursor"]
    assert borrowed, "the stranger's door answered no link to steal"

    code, text = await _raw(client, viewer["token"], url, cursor=borrowed, limit=5)

    assert code == 422, f"a stranger's link turned {url} with {code}: {text[:160]}"
    assert BAD_CURSOR in text, "a borrowed link was refused with a sentence naming its mechanism"
    # The refusal leaves the reader's own walk untouched: nothing about the borrowed link was read, and
    # the door still opens the rows the account itself stands on.
    fresh = await _page(client, viewer["token"], url, limit=5)
    assert _rows(fresh) == mine[:5]
    assert not set(_rows(fresh)) & set(theirs), "the door named a stranger's rows after the refusal"


@pytest.mark.parametrize(("url", "field", "cap"), _DOORS)
async def test_the_refusal_does_not_explain_the_signature(
    client: AsyncClient, session: AsyncSession, url: str, field: str, cap: int
) -> None:
    """What the server checks is not something a person at the URL gets to read.

    The envelope carries one sentence about the link. A refusal that said which half failed — the key,
    the version, the expiry, the account — would hand an attacker a probe for the signing rule, and a
    refusal that echoed the payload would put a token in a log line.
    """
    viewer = await _account(client, f"leak_{field}")

    _, text = await _raw(client, viewer["token"], url, cursor="dGVwADE6MDow.Zm9v")

    lowered = text.lower()
    for word in ("hmac", "signature", "signing", "key", "kid", "expir", "secret", "cursor"):
        assert word not in lowered, f"the refusal of {url} names {word!r}: {text[:200]}"
    assert BAD_CURSOR in text


@pytest.mark.parametrize(("url", "field", "cap"), _DOORS)
async def test_a_deeper_page_costs_what_a_first_page_costs(
    client: AsyncClient, session: AsyncSession, url: str, field: str, cap: int
) -> None:
    """The link is read from what the page already holds, so paging adds no round trip.

    Three statements paint a page — the rows, the profiles, the leading photos. A cursor that made the
    door look its own anchor row up would put a fourth read on every page after the first, and the row
    published in `docs/SCALE_PLAN.md` would no longer be the price of the door.
    """
    viewer = await _account(client, f"price_{field}")
    markers = _MARKERS if field == "likes" else _PASS_MARKERS
    if field == "likes":
        await _seed_inbox(session, viewer["user_id"], cap + 8, tag=f"price_{field}")
    else:
        await _seed_passes(session, viewer["user_id"], cap + 8, tag=f"price_{field}")

    first, first_counts, first_total = await _counted_page(client, viewer["token"], url, markers)
    second, second_counts, second_total = await _counted_page(
        client, viewer["token"], url, markers, cursor=first["next_cursor"], limit=8
    )

    for name, marker in markers.items():
        assert first_counts[name] == 1, f"the first page read {marker} {first_counts[name]} times"
        assert second_counts[name] == 1, (
            f"the second page read {marker} {second_counts[name]} times at {url}, and the price moved"
        )
    assert second_total == first_total, (
        f"page one cost {first_total} statements and page two cost {second_total} at {url}: the "
        "cursor is being looked up rather than carried"
    )


@pytest.mark.parametrize(("url", "field", "cap"), _DOORS)
async def test_the_deeper_pages_hold_the_same_visibility_rule_as_the_first(
    client: AsyncClient, session: AsyncSession, url: str, field: str, cap: int
) -> None:
    """Hiding a profile behind the page boundary must not slip it in through page two."""
    viewer = await _account(client, f"hidden_{field}")
    if field == "likes":
        ids = await _seed_inbox(session, viewer["user_id"], cap + 5, tag=f"hidden_{field}")
    else:
        ids = await _seed_passes(session, viewer["user_id"], cap + 5, tag=f"hidden_{field}")
    hidden_id = ids[cap + 2]
    await session.execute(
        update(Profile).where(Profile.user_id == uuid.UUID(hidden_id)).values(is_hidden=True)
    )
    await session.commit()

    body = await _page(client, viewer["token"], url)
    second = await _page(client, viewer["token"], url, cursor=body["next_cursor"])

    listed = _rows(body) + _rows(second)
    assert hidden_id not in listed, (
        f"a profile that stopped being showable is named past {url}'s boundary"
    )
    assert len(listed) == cap + 4, (
        f"the walk of 55 rows with one hidden at {url} answered {len(listed)} cards"
    )


@pytest.mark.parametrize(("url", "field", "cap"), _DOORS)
async def test_a_row_that_left_while_the_reader_stood_on_page_one_leaves_the_walk_whole(
    client: AsyncClient, session: AsyncSession, url: str, field: str, cap: int
) -> None:
    """A boundary drawn through values the reader holds survives the write that removes a row.

    Both doors lose a row while the reader is looking: the inbox loses the tap the reader answered back
    (a pair lives in the match list, not here), the pass list loses the pass the reader took back. A
    cursor carrying a position would shift the tail up and hand out cards the reader has already seen;
    a keyset link names the last row it showed — moment and id — so the rows below the boundary keep
    coming whole and nothing from above it returns.
    """
    viewer = await _account(client, f"undo_{field}")
    if field == "likes":
        ids = await _seed_inbox(session, viewer["user_id"], 14, tag=f"undo_{field}", minutes_apart=2)
    else:
        ids = await _seed_passes(session, viewer["user_id"], 14, tag=f"undo_{field}", minutes_apart=2)
    first = await _page(client, viewer["token"], url, limit=5)
    assert _rows(first) == ids[:5]

    dropped = ids[2]
    verb = "like" if field == "likes" else "pass"
    method = client.post if field == "likes" else client.delete
    resp = await method(
        f"/api/v1/users/{dropped}/{verb}", headers=auth_headers(viewer["token"])
    )
    assert resp.status_code == 200, resp.text

    tail: list[str] = []
    cursor: str | None = first["next_cursor"]
    while cursor is not None:
        body = await _page(client, viewer["token"], url, cursor=cursor, limit=5)
        tail.extend(_rows(body))
        cursor = body["next_cursor"]

    assert tail == ids[5:], (
        f"the pages after a {verb} answered {tail} instead of the rows still standing behind the link"
    )
    assert len(tail) == len(set(tail)), f"a row was named twice below a {verb}"


@pytest.mark.parametrize(("url", "field", "cap"), _DOORS)
async def test_an_account_with_nothing_to_read_answers_the_same_shape(
    client: AsyncClient, session: AsyncSession, url: str, field: str, cap: int
) -> None:
    """Empty, full and paged are one shape: the screen does not branch on which one it got."""
    viewer = await _account(client, f"empty_{field}")

    body = await _page(client, viewer["token"], url)

    assert body[field] == []
    assert body["has_more"] is False
    assert body["next_cursor"] is None


@pytest.mark.parametrize(("url", "field", "cap"), _DOORS)
async def test_a_link_turned_twice_answers_the_same_page(
    client: AsyncClient, session: AsyncSession, url: str, field: str, cap: int
) -> None:
    """A link is a place in the list, so asking for it twice gets the same page twice.

    The reader can lose a response and press again, and the screen must not have to know whether the
    retry re-serves rows it already showed or quietly advances. Nothing is remembered between the calls:
    the boundary travels in the link, so the second answer is the first one again, down to its own next
    link.
    """
    viewer = await _account(client, f"replay_{field}")
    if field == "likes":
        ids = await _seed_inbox(session, viewer["user_id"], 12, tag=f"replay_{field}", minutes_apart=3)
    else:
        ids = await _seed_passes(session, viewer["user_id"], 12, tag=f"replay_{field}", minutes_apart=3)
    first = await _page(client, viewer["token"], url, limit=4)
    assert _rows(first) == ids[:4]
    held = first["next_cursor"]
    assert isinstance(held, str)

    again = await _page(client, viewer["token"], url, cursor=held, limit=4)
    once = await _page(client, viewer["token"], url, cursor=held, limit=4)

    assert _rows(again) == ids[4:8]
    assert again == once, f"{url} answered the same link differently the second time it was turned"


def _probe():
    """Load the stand as a module: it is a script, so it is not on the import path."""
    spec = importlib.util.spec_from_file_location("scale_probe", _PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("path", "handler"),
    [
        pytest.param("liked_me", "liked_me", id="inbox"),
        pytest.param("passed", "passed_users", id="pass-list"),
    ],
)
def test_the_priced_wrapper_names_every_parameter_the_handler_declares(
    path: str, handler: str
) -> None:
    """A harness that calls a route handler directly receives values, not `Query` descriptors.

    `backend/ops/scale_probe.py` prices these two doors by calling the functions the API dispatches —
    stage 78's rule, and the reason a row is the price of the route rather than of what somebody
    believed the route does. Giving either function a page size and a link therefore breaks a wrapper
    that kept calling it with only a reader and a session, and a wrapper that quietly picked a page size
    of its own would price a page no screen asks for.
    """
    from app.api.v1 import discover

    probe = _probe()
    fn = getattr(discover, handler)
    source = inspect.getsource(probe._build_paths()[path])

    for name, parameter in inspect.signature(fn).parameters.items():
        if name in ("current_user", "session"):
            continue
        assert parameter.default is not inspect.Parameter.empty, (
            f"`{handler}` now takes {name} without a default, so an old caller has no page to ask for"
        )
        assert f"{name}=" in source, (
            f"`{handler}` declares {name} and the priced wrapper never names it: {source}"
        )
    assert "cursor=None" in source, (
        f"the published row for `{path}` must be the price of the first page — the one the screen "
        "opens with"
    )
