"""A pair is two people, and the pair page asked every table for them one at a time.

``GET /api/v1/matches/{id}`` introduces the peer: their card, their interest list, their photos and
the percent the pair carries. Listening to the route with ``before_cursor_execute`` counted 10
statements, and six of them asked the same three tables twice — once for the peer, whose row comes
through the match-peer rule, and once for the viewer, whose row the percent is computed from: two
``SELECT profiles``, two interest joins, two ``SELECT compatibility_profiles``. The compatibility
screen of the same pair had already been brought to three reads by stage 25, because the deck has
always read a page of people with one profile statement that carries everyone's interests and one
statement for everyone's answer vectors.

The bounds here are about the tables, not about a magic total: each of the three is asked once per
request, for both people. What must not move is the answer — the same percent a cold per-person read
gives, and the peer still shown even after they hid from the deck, because an established pair is not
a pending introduction. That second part is the risk of putting two people into one statement: the
rule belongs to one half of it.
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Callable

from httpx import AsyncClient
from sqlalchemy import event

from app.core.database import engine
from app.services.compatibility_service import CompatibilityService

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

# Which statement reads which part of a person, counted by the columns each loader selects so the
# interest loader and the profile loader are not mistaken for one another.
_MARKERS = {
    "profile": "profiles.name",
    "vector": "compatibility_profiles.vector",
    "interests": "interests.slug",
}


def _listener(seen: list[str]) -> Callable[..., None]:
    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    return _record


def _reads(seen: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for statement in seen:
        for name, marker in _MARKERS.items():
            if marker in statement:
                counts[name] += 1
    return counts


async def _counted(client: AsyncClient, coro):
    seen: list[str] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        resp = await coro
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    return resp, seen


async def _account(client: AsyncClient, email: str, *, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def _pair(client: AsyncClient, prefix: str) -> tuple[dict, dict, str]:
    """Two onboarded, answered accounts and the match between them."""
    viewer = await _account(client, f"{prefix}_viewer@befos.app", name="Вера", gender="female")
    peer = await _account(client, f"{prefix}_peer@befos.app", name="Пётр", gender="male")
    await client.post(f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(viewer["token"]))
    back = await client.post(
        f"/api/v1/users/{viewer['user_id']}/like", headers=auth_headers(peer["token"])
    )
    assert back.status_code == 200, back.text
    match_id = back.json()["match_id"]
    assert match_id
    return viewer, peer, match_id


async def test_the_pair_page_reads_both_people_once_per_concern(client: AsyncClient) -> None:
    """One profile statement for the two of them, one interest read, one batch of vectors."""
    viewer, _peer, match_id = await _pair(client, "s30_screen")

    resp, seen = await _counted(
        client, client.get(f"/api/v1/matches/{match_id}", headers=auth_headers(viewer["token"]))
    )
    assert resp.status_code == 200, resp.text

    counts = _reads(seen)
    assert counts["profile"] == 1, (
        f"profile rows read {counts['profile']} times for a page about two people"
    )
    assert counts["interests"] == 1, (
        f"interest lists read {counts['interests']} times for a page about two people"
    )
    assert counts["vector"] == 1, (
        f"answer vectors read {counts['vector']} times for a page about two people"
    )
    assert len(seen) <= 7, f"{len(seen)} trips to draw one pair page"


async def test_the_batched_pair_page_shows_the_number_the_engine_computes(
    client: AsyncClient, session
) -> None:
    """Fewer statements, same percent: the batch has to have carried both people's rows.

    The reference path is ``score_pair``, which reads each person on their own, so the two agree
    only if one profile statement really brought both rows and one vector statement both vectors.
    """
    viewer, peer, match_id = await _pair(client, "s30_equal")

    resp = await client.get(f"/api/v1/matches/{match_id}", headers=auth_headers(viewer["token"]))
    assert resp.status_code == 200, resp.text
    card = resp.json()["other_user"]

    reference = await CompatibilityService(session).score_pair(
        uuid.UUID(viewer["user_id"]), uuid.UUID(peer["user_id"])
    )
    assert card["compatibility"] == reference.overall_percent, (
        "the batched pair page and the per-person read disagree on the percent"
    )
    assert card["interests"] and card["shared_interests"], (
        "the page lost the interest lists it scores the pair by"
    )


async def test_batching_keeps_the_rule_that_shows_a_hidden_partner(client: AsyncClient) -> None:
    """The half of the statement that is the peer still answers to the peer rule, not the deck's.

    «Скрыть из подбора» withdraws introductions that have not happened yet. A pair that already said
    yes to each other keeps its page, so the batched read must filter the peer by the match rule and
    leave the viewer's own row unconditional.
    """
    viewer, peer, match_id = await _pair(client, "s30_hidden")
    hidden = await client.post(
        "/api/v1/users/me/visibility",
        headers=auth_headers(peer["token"]),
        json={"hidden": True},
    )
    assert hidden.status_code == 200, hidden.text

    resp, seen = await _counted(
        client, client.get(f"/api/v1/matches/{match_id}", headers=auth_headers(viewer["token"]))
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["other_user"]
    assert body["name"] == "Пётр"
    assert body["interests"], "the hidden partner's card came back without the list it shows"

    counts = _reads(seen)
    assert counts["profile"] == 1, (
        f"profile rows read {counts['profile']} times on a pair page that kept its peer"
    )
