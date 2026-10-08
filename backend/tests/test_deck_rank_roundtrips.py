"""A page that refills the deck reads the same candidates twice.

`GET /discover` ranks a fresh batch of candidates (`new_candidate_ids` → the three batch reads of
profiles, interest lists and answer vectors → the engine → `deck_append`) and then, one step later
in the same request, builds cards for the ids it just claimed out of that batch. Before this stage
the card path asked for those three concerns again: measured on a page of 3 cards served from a
batch of 6, statements 7/8/9 ranked the six and statements 15/16/18 re-read the very same rows,
interests and vectors for the three of them the page delivers.

The bound below is about repeats, not totals: three batch reads per request on a page that ranks
and serves from the same batch, whichever path each read belongs to. The rest of the file is the
argument that the reuse is safe: a card served from a row the deck holds from an earlier request
still has to be read (the reused batch only answers ids it ranked), and a candidate who hid since
the ranking still has to be dropped — the check that decides both is `deck_fresh_ids`, and it stays
in front of the card builder.
"""

from __future__ import annotations

from typing import Callable
from collections import Counter

from httpx import AsyncClient
from sqlalchemy import event, select

from app.core.database import AsyncSessionLocal, engine
from app.models import DiscoveryQueue

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

# The three concerns a candidate is read through, by the prefix each batch statement starts with.
_CONCERNS = {
    "profile": "select profiles.id, profiles.user_id, profiles.name",
    "interests": "select profiles_1.id as profiles_1_id, interests.id",
    "vector": "select compatibility_profiles.id, compatibility_profiles.user_id",
}


def _batch_concern(statement: str) -> str | None:
    """Which concern of a candidate batch this statement reads, if it is one.

    A single-person read is not a batch: it binds one id, while a batch binds at least two, which
    is what the second placeholder says. That distinction is what keeps the viewer's own row and
    the interest list loaded with it out of the count — the loader for one profile is written with
    the same `IN` as the loader for fifty, and only the number of ids it hands differs.
    """
    if " in ($1::uuid, $2::uuid" not in statement:
        return None
    for concern, prefix in _CONCERNS.items():
        if statement.startswith(prefix):
            return concern
    return None


def _listener(seen: list[str]) -> Callable[..., None]:
    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    return _record


async def _account(client: AsyncClient, email: str, *, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def _deck(client: AsyncClient, token: str, *, limit: int, cursor: str | None = None):
    params: dict[str, object] = {"limit": limit}
    if cursor:
        params["cursor"] = cursor
    return await client.get("/api/v1/discover", params=params, headers=auth_headers(token))


async def _recorded_page(client: AsyncClient, token: str, *, limit: int, cursor: str | None = None):
    """One page, with its statements and their batch reads counted."""
    seen: list[str] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        resp = await _deck(client, token, limit=limit, cursor=cursor)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    assert resp.status_code == 200, resp.text
    return resp.json(), seen, Counter(c for c in (_batch_concern(s) for s in seen) if c)


async def _queue_scores(viewer_id: str) -> dict[str, int]:
    """The percentage each deck row was ranked and stored with."""
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(DiscoveryQueue.candidate_id, DiscoveryQueue.score).where(
                    DiscoveryQueue.viewer_id == viewer_id
                )
            )
        ).all()
    return {str(candidate_id): score for candidate_id, score in rows}


async def test_a_page_that_refills_reads_its_candidates_once(client: AsyncClient) -> None:
    """Six ranked, three served from them: three batch reads, not six."""
    viewer = await _account(client, "s28_viewer@befos.app", name="Вера", gender="female")
    for index in range(6):
        await _account(client, f"s28_peer{index}@befos.app", name="Пётр", gender="male")

    body, seen, batches = await _recorded_page(client, viewer["token"], limit=3)

    assert len(body["items"]) == 3, body
    reads = sum(batches.values())
    assert reads == 3, (
        f"a page that ranked a batch and served cards from it read its candidates {reads} times "
        f"({dict(batches)}): the card builder re-read the rows, the interest lists and the answer "
        "vectors the ranking had just loaded for the same ids"
    )
    assert len(seen) <= 16, f"a page that refills and serves cost {len(seen)} statements"


async def test_a_card_carries_the_percentage_the_deck_was_ordered_by(client: AsyncClient) -> None:
    """Ranking and serving are one decision now, so their numbers cannot drift apart."""
    viewer = await _account(client, "s28_strong@befos.app", name="Нина", gender="female")
    for index in range(4):
        await _account(client, f"s28_brother{index}@befos.app", name="Олег", gender="male")

    body, _seen, _batches = await _recorded_page(client, viewer["token"], limit=2)
    scores = await _queue_scores(viewer["user_id"])
    assert len(body["items"]) == 2, body
    for card in body["items"]:
        assert card["compatibility"] == scores[card["user_id"]], (
            f"a card reports {card['compatibility']}% while the deck row that ranked it stores "
            f"{scores[card['user_id']]}%"
        )


async def test_a_card_from_an_earlier_request_is_still_read(client: AsyncClient) -> None:
    """Reusing the ranked batch must not make a claim the deck already held come back empty.

    The second page claims rows the *first* request ranked: nothing in this request read them, so
    the card builder has to. Three cards, three batch reads, the same numbers the deck stores.
    """
    viewer = await _account(client, "s28_second@befos.app", name="Раиса", gender="female")
    for index in range(6):
        await _account(client, f"s28_late{index}@befos.app", name="Тимур", gender="male")

    first, _seen, _batches = await _recorded_page(client, viewer["token"], limit=3)
    assert len(first["items"]) == 3, first
    assert first["next_cursor"], first

    second, _seen, batches = await _recorded_page(
        client, viewer["token"], limit=3, cursor=first["next_cursor"]
    )
    assert len(second["items"]) == 3, (
        f"the second page served {len(second['items'])} cards: the rows it claimed were ranked by "
        "the previous request, so this one has to read them rather than serve nothing"
    )
    served_first = {card["user_id"] for card in first["items"]}
    served_second = {card["user_id"] for card in second["items"]}
    assert not served_first & served_second, "a card was handed over twice"
    assert sum(batches.values()) == 3, (
        f"the page that only served stored rows read them {sum(batches.values())} times "
        f"({dict(batches)})"
    )
    scores = await _queue_scores(viewer["user_id"])
    for card in second["items"]:
        assert card["compatibility"] == scores[card["user_id"]]


async def test_a_candidate_who_hides_after_the_ranking_is_not_served(client: AsyncClient) -> None:
    """The reused row is not the gate: a promise the deck made still has to be checked.

    One peer is left in the deck undelivered by the first page and hides before the second one,
    which ranks two newcomers. The page has to serve both newcomers from the batch it just ranked
    and drop the hider, whose row this same request also read.
    """
    viewer = await _account(client, "s28_gate@befos.app", name="Лидия", gender="female")
    peers = [
        await _account(client, f"s28_gate_{index}@befos.app", name="Глеб", gender="male")
        for index in range(2)
    ]

    page, _seen, _batches = await _recorded_page(client, viewer["token"], limit=1)
    assert len(page["items"]) == 1, page
    served_ids = {card["user_id"] for card in page["items"]}
    hider = next(peer for peer in peers if peer["user_id"] not in served_ids)

    hidden = await client.post(
        "/api/v1/users/me/visibility",
        json={"hidden": True},
        headers=auth_headers(hider["token"]),
    )
    assert hidden.status_code == 200, hidden.text

    newcomers = [
        await _account(client, f"s28_gate_new{index}@befos.app", name="Артём", gender="male")
        for index in range(2)
    ]

    body, _seen, batches = await _recorded_page(
        client, viewer["token"], limit=3, cursor=page["next_cursor"]
    )
    served = {card["user_id"] for card in body["items"]}
    assert served == {peer["user_id"] for peer in newcomers}, (
        f"the page served {sorted(served)}: a candidate who hid after being queued has to be "
        "dropped, and the candidates ranked in this request have to be served"
    )
    assert sum(batches.values()) == 3, (
        f"the page that ranked two newcomers and served them read candidates "
        f"{sum(batches.values())} times ({dict(batches)})"
    )
