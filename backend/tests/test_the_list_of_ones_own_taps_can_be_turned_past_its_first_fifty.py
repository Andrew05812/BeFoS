"""The account's own taps stop at fifty, and nothing in the answer says how to go past them (stage 123).

`GET /api/v1/discover/liked` reads the newest `LIKED_SHOWN + 1` rows, shows fifty and sets `has_more`.
The screen paints the notice that stage 116 wrote for it — «за ними ждут другие» — and then admits in
the same sentence that it cannot reach them: `Dtos.kt:76` spells the bargain out for the sessions list
and it reads the same here, *has_more is not a pagination hint the client can follow: the route takes no
cursor*. So a person who liked two hundred people can review two and a half percent of them, and the
door that lists the rest does not exist.

The stand makes the size of that silence a number rather than an impression. `s122_walk.json` counts
the viewer's own outgoing taps at 87 / 893 / 4 493 for 1 000 / 10 000 / 50 000 анкет, so even the
smallest scale the table publishes leaves 37 taps unread, and the largest leaves 4 443.

This file names the shape that closes it. The mechanism is not invented: the deck has paged by an
opaque base64url cursor since stage 17 (`encode_cursor`/`decode_cursor`), the pair's history has broken
a `created_at` tie by the row's own id since stage 54, and the blocked list answers a write with the
page the server holds. What is new is putting those two existing devices behind this door — a keyset
over `(created_at, id)` so that a page boundary cannot swallow a row, and a refusal that answers a
tampered cursor as bad input rather than as an empty page.

What deliberately does not change: the default page still carries fifty rows and pays the same three
reads it pays today, so the published price of `liked` in `docs/SCALE_PLAN.md` stays re-derivable, and
the withdrawal still answers with the first page rather than with the page the caller was on.
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

from httpx import AsyncClient
from sqlalchemy import event, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models import Like, Profile, User
from app.models.base import utcnow
from app.services.discovery_service import BAD_CURSOR, LIKED_SHOWN

from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)

BIRTH = date(1996, 5, 10)
LIKED = "/api/v1/discover/liked"


async def _account(client: AsyncClient, tag: str, *, name: str = "Вера") -> dict:
    creds = await register_and_auth(client, f"s123_{tag}@befos.app")
    await complete_onboarding(client, creds["token"], name=name)
    await answer_all_questions(client, creds["token"])
    return creds


async def _page(client: AsyncClient, token: str, **params) -> dict:
    resp = await client.get(LIKED, headers=auth_headers(token), params=params)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "next_cursor" in body, (
        f"the page answered {sorted(body)} — a door that says more taps exist has to name the key that "
        "reaches them"
    )
    return body


async def _raw(client: AsyncClient, token: str, **params) -> tuple[int, str]:
    resp = await client.get(LIKED, headers=auth_headers(token), params=params)
    return resp.status_code, resp.text


async def _seed_taps(
    session: AsyncSession,
    viewer_id: str,
    count: int,
    *,
    tag: str,
    minutes_apart: int = 5,
) -> list[str]:
    """Taps written straight into the tables: this is about reading a page, not about signing up.

    The rows carry what a live tap carries — a `likes` line pointing *from* the viewer, with the score
    the viewer's card held at that moment — and they step back in time by `minutes_apart`. Zero spacing
    puts every row on the same microsecond, which is the case a page boundary built on the timestamp
    alone loses.
    """
    ids = [uuid.uuid4() for _ in range(count)]
    await session.execute(
        insert(User),
        [
            {
                "id": uid,
                "email": f"s123_{tag}_t{i}@befos.app",
                "password_hash": "not-a-real-hash",
                "is_active": True,
                "is_deleted": False,
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
                "name": f"Тэп {i}",
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
    newest = utcnow()
    await session.execute(
        insert(Like),
        [
            {
                "id": uuid.uuid4(),
                "from_user_id": uuid.UUID(viewer_id),
                "to_user_id": uid,
                "compatibility_score": 0.7,
                "created_at": newest - timedelta(minutes=minutes_apart * i),
            }
            for i, uid in enumerate(ids)
        ],
    )
    await session.commit()
    return [str(uid) for uid in ids]


_MARKERS = {
    "taps": "from likes",
    "cards": "from profiles",
    "photos": "from photos",
}


def _listener(seen: list[str]) -> Callable[..., None]:
    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    return _record


def _counts(seen: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for statement in seen:
        for name, marker in _MARKERS.items():
            if marker in statement:
                counts[name] += 1
    return counts


async def _counted_page(
    client: AsyncClient, token: str, **params
) -> tuple[dict, Counter[str], int]:
    """One call, its answer, and what the database was asked to do for it."""
    seen: list[str] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        body = await _page(client, token, **params)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    return body, _counts(seen), len(seen)


async def _walk(client: AsyncClient, token: str, *, limit: int) -> list[str]:
    """Every page in order, following nothing but the cursors the server handed out."""
    ids: list[str] = []
    cursor: str | None = None
    for _ in range(200):  # a guard against a cursor that points at where it already was
        params: dict = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        body = await _page(client, token, **params)
        ids.extend(card["user_id"] for card in body["likes"])
        if not body["has_more"]:
            assert body["next_cursor"] is None, (
                "the last page says nothing stands behind it and still hands over a way forward"
            )
            return ids
        cursor = body["next_cursor"]
        assert cursor, "a page that promises more answers no cursor to reach it"
    raise AssertionError("the walk never ended")


async def test_a_page_that_stopped_at_fifty_hands_over_the_way_forward(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """`has_more` has to come with something a reader can act on."""
    viewer = await _account(client, "forward_v")
    ids = await _seed_taps(session, viewer["user_id"], LIKED_SHOWN + 5, tag="forward")

    body = await _page(client, viewer["token"])

    assert len(body["likes"]) == LIKED_SHOWN, "the default page changed size with this stage"
    assert body["has_more"] is True
    assert isinstance(body["next_cursor"], str) and body["next_cursor"], (
        "the answer admits more taps exist and gives no cursor to reach them"
    )
    assert [card["user_id"] for card in body["likes"]] == ids[:LIKED_SHOWN]


async def test_the_cursor_opens_the_taps_that_stood_behind_the_first_page(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """Page two is the rest of the list, not a second copy of the first page."""
    viewer = await _account(client, "second_v")
    ids = await _seed_taps(session, viewer["user_id"], LIKED_SHOWN + 5, tag="second")
    first = await _page(client, viewer["token"])

    second = await _page(client, viewer["token"], cursor=first["next_cursor"])

    assert [card["user_id"] for card in second["likes"]] == ids[LIKED_SHOWN:], (
        "the cursor reopened rows the first page had already named"
    )
    assert second["has_more"] is False
    assert second["next_cursor"] is None


async def test_a_walk_over_every_page_names_each_tap_exactly_once(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """Pages are a partition of the list: no row between them lost, no row twice."""
    viewer = await _account(client, "walk_v")
    ids = await _seed_taps(session, viewer["user_id"], 23, tag="walk", minutes_apart=1)

    seen = await _walk(client, viewer["token"], limit=7)

    assert Counter(seen) == Counter(ids), (
        f"23 taps walked as {len(seen)} rows, {len(set(seen))} of them distinct"
    )


async def test_taps_written_at_the_same_moment_do_not_fall_between_two_pages(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """The boundary is the pair `(created_at, id)`, because the timestamp alone is not a total order.

    Stage 54 proved the loss for the pair's history: rows sharing a microsecond sit on both sides of a
    boundary drawn through `created_at`, so the page that resumes *strictly older* never reads them. The
    same arithmetic applies to a deck of taps swiped fast.
    """
    viewer = await _account(client, "tie_v")
    ids = await _seed_taps(session, viewer["user_id"], 12, tag="tie", minutes_apart=0)

    seen = await _walk(client, viewer["token"], limit=5)

    assert Counter(seen) == Counter(ids), (
        f"12 taps at one microsecond walked as {len(seen)} rows, {len(set(seen))} distinct"
    )


async def test_a_smaller_page_can_be_asked_for_and_the_walk_still_covers_the_list(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """The cap is the default, not the only page size the door answers with."""
    viewer = await _account(client, "small_v")
    ids = await _seed_taps(session, viewer["user_id"], 12, tag="small", minutes_apart=1)

    body = await _page(client, viewer["token"], limit=4)

    assert len(body["likes"]) == 4
    assert body["has_more"] is True
    assert [card["user_id"] for card in body["likes"]] == ids[:4]
    assert await _walk(client, viewer["token"], limit=4) == ids


async def test_the_page_size_keeps_its_bounds(client: AsyncClient) -> None:
    """Zero asks the database for no rows and 501 asks it for a page nobody can paint."""
    viewer = await _account(client, "bounds_v")

    for bad in (0, LIKED_SHOWN + 1, -3):
        code, text = await _raw(client, viewer["token"], limit=bad)
        assert code == 422, f"limit={bad} answered {code}: {text[:120]}"

    code, text = await _raw(client, viewer["token"], limit=LIKED_SHOWN)
    assert code == 200, text


async def test_a_cursor_nobody_handed_out_is_refused_as_input(client: AsyncClient) -> None:
    """A broken link is a bad link, not an empty page.

    Answering `{"likes": []}` would let a mistyped cursor look like the end of the list, and the screen
    would stop loading and say the account has no more taps. The deck already refuses a cursor it
    cannot read with this sentence; the tap list refuses with the same one.
    """
    viewer = await _account(client, "tampered_v")

    for bad in (
        "not-a-cursor",
        "%%%",
        base64.urlsafe_b64encode(b"tap:x:y").decode().rstrip("="),
    ):
        code, text = await _raw(client, viewer["token"], cursor=bad)
        assert code == 422, f"cursor={bad!r} answered {code}: {text[:160]}"
        assert BAD_CURSOR in text, f"cursor={bad!r} was refused with another sentence: {text[:160]}"

    # An absent cursor and an empty one are the same question: start from the newest tap. That is how
    # the deck reads its own `decode_cursor(None)`, and a page that refused an empty link would give
    # the client two ways to ask for the first page and only one way to get it.
    code, text = await _raw(client, viewer["token"], cursor="")
    assert code == 200, f"an empty cursor was refused rather than read as the top of the list: {text[:160]}"


async def test_the_decks_cursor_does_not_turn_this_page(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """Two doors, two cursors: a rank from one is not a place in the other.

    Both are base64url and both are opaque to the client, so the only thing that keeps a deck cursor
    from being read as a tap position is the prefix it carries. Without it the number would mean a row
    that does not exist in this ordering, and the page would answer rather than refuse.
    """
    from app.services.discovery_service import encode_cursor

    viewer = await _account(client, "prefix_v")
    await _seed_taps(session, viewer["user_id"], 3, tag="prefix", minutes_apart=1)

    code, text = await _raw(client, viewer["token"], cursor=encode_cursor(3))

    assert code == 422, f"a deck cursor turned the tap list with {code}: {text[:160]}"


async def test_a_cursor_beyond_any_clock_is_refused_rather_than_raising(
    client: AsyncClient,
) -> None:
    """A hand-built payload is input: the bound that stage 17 put on the deck's rank belongs here too.

    PostgreSQL's `timestamptz` ends in 294276, and Python's `datetime` refuses what is beyond it. A
    cursor that reaches past either answers 422 with the broken-link sentence — a 500 would put a
    traceback behind a person's typo.
    """
    from app.services.discovery_service import TAP_CURSOR_PREFIX

    viewer = await _account(client, "absurd_v")

    for payload in (
        f"{TAP_CURSOR_PREFIX}:{10**25}:00000000000000000000000000000000",
        f"{TAP_CURSOR_PREFIX}:1730000000000000:{'not-hex-at-all'}",
        f"{TAP_CURSOR_PREFIX}:1730000000000000:" + "f" * 32 + ":extra",
    ):
        cursor = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
        code, text = await _raw(client, viewer["token"], cursor=cursor)
        assert code == 422, f"{payload[:40]!r} answered {code}: {text[:160]}"
        assert BAD_CURSOR in text


async def test_a_cursor_carried_from_another_account_reads_only_ones_own_taps(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The position is somebody's place in *their* list; the rows belong to the reader.

    Nothing in the cursor names an account, and the read is addressed by `from_user_id`, so a borrowed
    link must filter the reader's own taps from that moment rather than reveal a stranger's list or
    answer with the rows the stranger was standing on.
    """
    viewer = await _account(client, "own_a", name="Вера")
    stranger = await _account(client, "own_b", name="Пётр")
    mine = await _seed_taps(session, viewer["user_id"], 12, tag="own_a", minutes_apart=7)
    theirs = await _seed_taps(session, stranger["user_id"], 12, tag="own_b", minutes_apart=1)
    borrowed = (await _page(client, stranger["token"], limit=5))["next_cursor"]

    body = await _page(client, viewer["token"], cursor=borrowed, limit=5)

    listed = [card["user_id"] for card in body["likes"]]
    assert listed, "a borrowed moment silenced the reader's own older taps"
    assert set(listed) <= set(mine), "the read named rows belonging to somebody else's list"
    assert not set(listed) & set(theirs), "the borrowed cursor carried a stranger's taps"


async def test_the_deeper_pages_hold_the_same_visibility_rule_as_the_first(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """Hiding a profile behind the page boundary must not slip it in through page two."""
    viewer = await _account(client, "hidden_v")
    ids = await _seed_taps(session, viewer["user_id"], LIKED_SHOWN + 5, tag="hidden")
    hidden_id = ids[LIKED_SHOWN + 2]
    await session.execute(
        update(Profile).where(Profile.user_id == uuid.UUID(hidden_id)).values(is_hidden=True)
    )
    await session.commit()

    body = await _page(client, viewer["token"])
    second = await _page(client, viewer["token"], cursor=body["next_cursor"])

    listed = [card["user_id"] for card in body["likes"]] + [
        card["user_id"] for card in second["likes"]
    ]
    assert hidden_id not in listed, "a profile that stopped being showable is named past the boundary"
    assert len(listed) == LIKED_SHOWN + 4, (
        f"the walk of 55 taps with one hidden answered {len(listed)} cards"
    )


async def test_a_withdrawn_tap_leaves_the_walk_whole(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """A row that goes while the reader stands on page one must not swallow the page behind it.

    The boundary is drawn through values the reader already holds, so the tail keeps coming when the row
    the boundary was drawn on is gone. A cursor carrying a row id and looking that row up would answer
    the withdrawal with a missing row and stop the walk.
    """
    viewer = await _account(client, "undo_v")
    ids = await _seed_taps(session, viewer["user_id"], 14, tag="undo", minutes_apart=2)
    first = await _page(client, viewer["token"], limit=5)
    assert [card["user_id"] for card in first["likes"]] == ids[:5]

    dropped = ids[2]
    resp = await client.delete(
        f"/api/v1/users/{dropped}/like", headers=auth_headers(viewer["token"])
    )
    assert resp.status_code == 200, resp.text

    tail: list[str] = []
    cursor: str | None = first["next_cursor"]
    while cursor is not None:
        body = await _page(client, viewer["token"], cursor=cursor, limit=5)
        tail.extend(card["user_id"] for card in body["likes"])
        cursor = body["next_cursor"]

    assert tail == ids[5:], (
        f"the pages after a withdrawal answered {tail} instead of the taps still standing behind them"
    )
    assert await _walk(client, viewer["token"], limit=5) == ids[:2] + ids[3:]


async def test_the_withdrawal_answers_a_page_that_can_still_be_turned(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """After a row leaves, the screen still has to be able to reach the taps behind the cap.

    The withdrawal replaced the visible page and, with the cursor absent from its answer, replaced it
    with a page the reader can no longer leave.
    """
    viewer = await _account(client, "undo_page_v")
    ids = await _seed_taps(session, viewer["user_id"], LIKED_SHOWN + 3, tag="undo_page")

    resp = await client.delete(
        f"/api/v1/users/{ids[0]}/like", headers=auth_headers(viewer["token"])
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(body["likes"]) == LIKED_SHOWN
    assert body["has_more"] is True
    assert isinstance(body["next_cursor"], str) and body["next_cursor"], (
        "the page a withdrawal answered cannot be turned further"
    )


async def test_an_account_that_tapped_nobody_still_answers_the_same_shape(
    client: AsyncClient,
) -> None:
    """Empty, full and paged are one shape: the screen does not branch on which one it got."""
    viewer = await _account(client, "empty_v")

    assert await _page(client, viewer["token"]) == {
        "likes": [],
        "has_more": False,
        "next_cursor": None,
    }


async def test_a_second_page_costs_what_a_first_page_costs(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """The cursor is read from what the page already holds, so paging adds no round trip.

    Three statements paint a page — the taps, the profiles, the leading photos — and the price published
    for `liked` is built from them. A cursor that made the door fetch its own anchor row would put a
    fourth read on every page after the first, and the row in `docs/SCALE_PLAN.md` would no longer be
    the number the door pays.
    """
    viewer = await _account(client, "price_v")
    await _seed_taps(session, viewer["user_id"], LIKED_SHOWN + 8, tag="price")

    first, first_counts, first_total = await _counted_page(client, viewer["token"])
    second, second_counts, second_total = await _counted_page(
        client, viewer["token"], cursor=first["next_cursor"], limit=8
    )

    for name, marker in _MARKERS.items():
        assert first_counts[name] == 1, f"the first page read {marker} {first_counts[name]} times"
        assert second_counts[name] == 1, (
            f"the second page read {marker} {second_counts[name]} times, and the row's price moved"
        )
    assert second_total == first_total, (
        f"page one cost {first_total} statements and page two cost {second_total}: "
        "the cursor is being looked up rather than carried"
    )


_PROBE_PATH = Path(__file__).resolve().parents[1] / "ops" / "scale_probe.py"


def _probe():
    """Load the stand as a module: it is a script, so it is not on the import path."""
    spec = importlib.util.spec_from_file_location("scale_probe", _PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_priced_call_names_every_parameter_the_handler_declares() -> None:
    """A harness that calls a route handler directly receives its `Query` descriptors, not values.

    `backend/ops/scale_probe.py` prices this door by calling `liked_users` — the function the API
    dispatches, which is stage 78's rule and the reason the row is the price of the route rather than of
    what somebody believed the route does. Giving that function two query parameters therefore breaks a
    wrapper that kept calling it with only a reader and a session: `decode_tap_cursor` would be handed a
    `Query` object. A wrapper that quietly picked a page size of its own would price a page no screen
    asks for.
    """
    from app.api.v1.discover import liked_users

    source = inspect.getsource(_probe()._build_paths()["liked"])
    for name, parameter in inspect.signature(liked_users).parameters.items():
        if name in ("current_user", "session"):
            continue
        assert parameter.default is not inspect.Parameter.empty, (
            f"`liked_users` now takes {name} without a default, so an old caller has no page to ask for"
        )
        assert f"{name}=" in source, (
            f"`liked_users` declares {name} and the priced wrapper never names it: {source}"
        )
    assert "cursor=None" in source, (
        "the published row must be the price of the first page — the one the screen opens with"
    )
    assert "limit=LIKED_SHOWN" in source, (
        "the priced page size is written as a number of its own instead of the constant the cap is"
    )
