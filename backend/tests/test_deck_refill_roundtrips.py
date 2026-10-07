"""The page that says «there is nobody left» asks the selection three times.

`GET /discover` refills the deck from a rule scan — the widest query the product makes, seven
correlated `NOT EXISTS` over `likes`, `passes`, `blocks`, `matches` and the queue itself, named in
`docs/SCALE_PLAN.md` as the read that stops first. A viewer who has run out of cards paid it three
times in one request: the pre-emptive refill, the refill the short page tries next because the
first attempt's `False` could not tell "nobody left" from "nobody looked for", and
`has_unqueued_candidate` at the bottom of the method answering the same predicate with the same
preferences one more time.

The bounds below are about repeats again, not totals: one scan per request, and the `has_more` the
answer carries is the same `False` the three-scan version gave. The last check is the reason the
remembered answer is safe — a candidate who appears after the empty page is served by the next one.
"""

from __future__ import annotations

import uuid
from typing import Callable

from httpx import AsyncClient
from sqlalchemy import event

from app.core.database import engine

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth


def _selection_scan(statement: str) -> bool:
    """`new_candidate_ids`: the rule as a page of ids."""
    return statement.startswith("select profiles.user_id from profiles join users")


def _unqueued_ask(statement: str) -> bool:
    """`has_unqueued_candidate`: the same rule as a yes-or-no."""
    return statement.startswith("select 1 from (select profiles.user_id")


def _listener(seen: list[str]) -> Callable[..., None]:
    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    return _record


async def _account(client: AsyncClient, email: str, *, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def _deck(client: AsyncClient, token: str, cursor: str | None = None):
    params = {"cursor": cursor} if cursor else None
    return await client.get("/api/v1/discover", params=params, headers=auth_headers(token))


async def test_the_exhausted_deck_scans_the_selection_once(client: AsyncClient) -> None:
    """Nobody left to show: one scan has to be enough to learn it, and to say so."""
    viewer = await _account(client, "s27_viewer@befos.app", name="Вера", gender="female")
    peer = await _account(client, "s27_peer@befos.app", name="Пётр", gender="male")

    # The only candidate is now invisible to the rule: liked, and matched with the viewer.
    liked = await client.post(
        f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    assert liked.status_code == 200, liked.text
    assert (
        await client.post(
            f"/api/v1/users/{viewer['user_id']}/like", headers=auth_headers(peer["token"])
        )
    ).status_code == 200

    seen: list[str] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        resp = await _deck(client, viewer["token"])
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    scans = sum(1 for statement in seen if _selection_scan(statement))
    asks = sum(1 for statement in seen if _unqueued_ask(statement))
    assert scans == 1, (
        f"the selection was scanned {scans} times in one page: the refill that found nobody "
        "already answered what the next refill and `has_unqueued_candidate` would ask"
    )
    assert asks == 0, "`has_more` re-asked a question this request already paid for"
    assert len(seen) <= 8, f"the exhausted deck cost {len(seen)} statements"

    # The answer the three-scan version gave, unchanged.
    assert body["items"] == []
    assert body["has_more"] is False
    assert body["next_cursor"] is None


async def test_a_deck_with_somebody_left_still_hands_over_the_card(
    client: AsyncClient,
) -> None:
    """Remembering an empty selection must not swallow a page that has one."""
    viewer = await _account(client, "s27_alone@befos.app", name="Нина", gender="female")
    await _account(client, "s27_stranger@befos.app", name="Олег", gender="male")

    resp = await _deck(client, viewer["token"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["has_more"] is False, "a viewer who saw the only candidate is told there is more"


async def test_a_candidate_who_appears_after_the_empty_page_is_shown(
    client: AsyncClient,
) -> None:
    """The remembered answer lives inside one request, not across them."""
    viewer = await _account(client, "s27_late_viewer@befos.app", name="Лидия", gender="female")

    first = await _deck(client, viewer["token"])
    assert first.status_code == 200, first.text
    assert first.json()["items"] == []
    assert first.json()["has_more"] is False

    late = await _account(client, "s27_late_peer@befos.app", name="Глеб", gender="male")

    second = await _deck(client, viewer["token"])
    assert second.status_code == 200, second.text
    cards = second.json()["items"]
    assert [c["user_id"] for c in cards] == [late["user_id"]]


async def test_a_short_page_from_stale_rows_does_not_ask_the_selection_again(
    client: AsyncClient,
) -> None:
    """The claim can come back with nothing to serve while the selection is known empty.

    A queued row is a promise about a person who may have hidden since it was ranked. The page
    that drops it still has to stop after one refill attempt, because the attempt that found
    nobody and the attempt that would follow it read the same rule in the same request.
    """
    viewer = await _account(client, "s27_stale_viewer@befos.app", name="Раиса", gender="female")
    peer = await _account(client, "s27_stale_peer@befos.app", name="Тимур", gender="male")

    warm = await _deck(client, viewer["token"])
    assert warm.status_code == 200, warm.text
    assert len(warm.json()["items"]) == 1

    hidden = await client.post(
        "/api/v1/users/me/visibility",
        json={"hidden": True},
        headers=auth_headers(peer["token"]),
    )
    assert hidden.status_code == 200, hidden.text

    seen: list[str] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        resp = await _deck(client, viewer["token"])
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)

    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []
    scans = sum(1 for statement in seen if _selection_scan(statement))
    assert scans <= 1, f"the page dropped a stale row and then scanned the selection {scans} times"
