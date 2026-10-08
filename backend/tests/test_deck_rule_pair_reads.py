"""A card by the deck's rule is about two people too, and it asked every table for them twice.

``GET /api/v1/users/{id}`` shows a stranger: their profile, their interest list, their photos and
the percent the viewer would get with them. Listening to the route with ``before_cursor_execute``
counted 9 statements, and four of them asked the same three tables once per person — one ``SELECT
profiles`` for the target through ``_showable_conditions``, then a second one for the viewer, whose
row the percent is computed from, each with its own interest loader, plus two ``SELECT
compatibility_profiles``. Stage 30 had just given the pair's page one batched read for the same
concerns; this path kept the deck's rule but asked it about one id, so the viewer's half was left to
be read separately below.

The bounds are about the tables, not about a magic total: each of the three is asked once per
request, for both people. What must not move is the answer — the same percent a cold per-person read
gives — and what must not loosen is the rule, which belongs to one half of the statement: a profile
that hides from the deck has to stay invisible to a stranger, while the viewer's own row arrives
whatever it says about visibility.
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
    "photos": "photos.url",
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


async def _strangers(client: AsyncClient, prefix: str) -> tuple[dict, dict]:
    """Two onboarded, answered accounts that have never met: the deck's starting point."""
    viewer = await _account(client, f"{prefix}_viewer@befos.app", name="Вера", gender="female")
    peer = await _account(client, f"{prefix}_peer@befos.app", name="Пётр", gender="male")
    return viewer, peer


async def test_the_deck_card_reads_both_people_once_per_concern(client: AsyncClient) -> None:
    """One profile statement for the two of them, one interest read, one batch of vectors."""
    viewer, peer = await _strangers(client, "s31_screen")

    resp, seen = await _counted(
        client, client.get(f"/api/v1/users/{peer['user_id']}", headers=auth_headers(viewer["token"]))
    )
    assert resp.status_code == 200, resp.text

    counts = _reads(seen)
    assert counts["profile"] == 1, (
        f"profile rows read {counts['profile']} times for a card about two people"
    )
    assert counts["interests"] == 1, (
        f"interest lists read {counts['interests']} times for a card about two people"
    )
    assert counts["vector"] == 1, (
        f"answer vectors read {counts['vector']} times for a card about two people"
    )
    assert counts["photos"] == 1, "the card's photo list is not the profile batch"
    # The two that the batch above does not cover: the account behind the token and the block check.
    assert len(seen) <= 6, f"{len(seen)} trips to draw one stranger's card"


async def test_the_batched_card_shows_the_number_the_engine_computes(
    client: AsyncClient, session
) -> None:
    """Fewer statements, same percent: the batch has to have carried both people's rows.

    The reference path is ``score_pair``, which reads each person on their own, so the two agree
    only if one profile statement really brought both rows and one vector statement both vectors.
    """
    viewer, peer = await _strangers(client, "s31_equal")

    resp = await client.get(
        f"/api/v1/users/{peer['user_id']}", headers=auth_headers(viewer["token"])
    )
    assert resp.status_code == 200, resp.text
    card = resp.json()

    reference = await CompatibilityService(session).score_pair(
        uuid.UUID(viewer["user_id"]), uuid.UUID(peer["user_id"])
    )
    assert card["compatibility"] == reference.overall_percent, (
        "the batched card and the per-person read disagree on the percent"
    )
    assert card["interests"] and card["shared_interests"], (
        "the card lost the interest lists it scores the pair by"
    )


async def test_batching_keeps_the_rule_that_hides_a_stranger(client: AsyncClient) -> None:
    """The half of the statement that is the target still answers to the deck's rule.

    «Скрыть из подбора» withdraws introductions that have not happened, so a hidden profile has to
    stay a 404 for the stranger who asks for it even though the same statement now also fetches the
    viewer's row — which is unconditional, exactly as the separate read it replaced was.
    """
    viewer, peer = await _strangers(client, "s31_hidden")
    hidden = await client.post(
        "/api/v1/users/me/visibility",
        headers=auth_headers(peer["token"]),
        json={"hidden": True},
    )
    assert hidden.status_code == 200, hidden.text

    resp, seen = await _counted(
        client, client.get(f"/api/v1/users/{peer['user_id']}", headers=auth_headers(viewer["token"]))
    )
    assert resp.status_code == 404, resp.text
    # A refusal stays cheaper than a card: the rule answers in the one profile statement, and the
    # only extra read the batch brings is the asking viewer's own interest list.
    assert len(seen) <= 3, f"{len(seen)} trips to refuse one stranger's card"
