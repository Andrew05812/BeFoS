"""A pair is two people, so the compatibility screen and the score refresh read them in batches.

Stage 24 found the same shape in the recommendation page: ``CompatibilityService.build_input``
describes one person — their row, their interest list, their answer vector — and the pair screen
called it twice. Six round trips bought what the deck buys in three, because the deck has always
read a page of people with one profile statement that carries everyone's interests and one
statement for everyone's vectors.

The class of bug is paying per element inside a batch: the same numbers, the same answer, twice
as many trips as there are concerns. So each check here pairs a count with the answer staying
identical — the percent the screen shows has to still be the percent the engine computes from
those rows, and the percent the match list stores has to still be the one the fan just wrote.
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

_MARKERS = {
    "profile": "profiles.name",
    "vector": "compatibility_profiles.vector",
    # The loader of what people like joins this table; the read of interest *names* for the
    # shared list does not, so the marker counts the pair's interest lists, not the catalogue.
    "interests": "user_interests",
}


def _listener(seen: list[tuple[str, str]]) -> Callable[..., None]:
    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append((" ".join(statement.lower().split()), str(parameters)))

    return _record


def _reads(seen: list[tuple[str, str]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for statement, _ in seen:
        for name, marker in _MARKERS.items():
            if marker in statement:
                counts[name] += 1
    return counts


async def _account(client: AsyncClient, email: str, *, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def _counted(client: AsyncClient, coro):
    seen: list[tuple[str, str]] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        resp = await coro
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    return resp, seen


async def _pair(client: AsyncClient, prefix: str) -> tuple[dict, dict, str]:
    """Two onboarded, answered accounts and the match between them."""
    viewer = await _account(client, f"{prefix}_viewer@befos.app", name="Вера", gender="female")
    peer = await _account(client, f"{prefix}_peer@befos.app", name="Пётр", gender="male")
    await client.post(
        f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    back = await client.post(
        f"/api/v1/users/{viewer['user_id']}/like", headers=auth_headers(peer["token"])
    )
    assert back.status_code == 200, back.text
    match_id = back.json()["match_id"]
    assert match_id
    return viewer, peer, match_id


async def test_the_pair_screen_reads_both_people_once_per_concern(client: AsyncClient) -> None:
    """`GET /matches/{id}/compatibility`: one profile batch, one interest read, one vector read."""
    viewer, peer, match_id = await _pair(client, "s25_screen")

    resp, seen = await _counted(
        client,
        client.get(
            f"/api/v1/matches/{match_id}/compatibility", headers=auth_headers(viewer["token"])
        ),
    )
    assert resp.status_code == 200, resp.text

    counts = _reads(seen)
    assert counts["profile"] == 1, (
        f"profile rows read {counts['profile']} times for two people"
    )
    assert counts["interests"] == 1, (
        f"interest lists read {counts['interests']} times for two people"
    )
    assert counts["vector"] == 1, f"answer vectors read {counts['vector']} times for two people"
    assert len(seen) <= 6, f"the pair screen cost {len(seen)} statements"

    payload = resp.json()
    assert 0 <= payload["overall"] <= 100
    assert len(payload["categories"]) > 1
    assert payload["shared_interests"], (
        "the screen lost the interest list it is supposed to explain the pair by"
    )


async def test_the_batched_screen_shows_the_number_the_engine_computes(
    client: AsyncClient, session
) -> None:
    """Batching reads must not change the answer: the percent still comes from those rows.

    The reference path is `score_pair`, which reads each person on their own — so the two
    implementations agree only if the batch carried both people's profile, interests and vector.
    """
    viewer, peer, match_id = await _pair(client, "s25_equal")

    resp = await client.get(
        f"/api/v1/matches/{match_id}/compatibility", headers=auth_headers(viewer["token"])
    )
    assert resp.status_code == 200, resp.text
    reference = await CompatibilityService(session).score_pair(
        uuid.UUID(viewer["user_id"]), uuid.UUID(peer["user_id"])
    )
    assert resp.json()["overall"] == reference.overall_percent, (
        "the batched pair screen and the per-person read disagree on the percent"
    )


async def test_a_profile_edit_refreshes_the_pairs_from_one_read_per_concern(
    client: AsyncClient,
) -> None:
    """The fan after a profile edit touches this user and every peer: one vector read, not two.

    `refresh_pair_scores` read the peers' answers in a batch and then this user's own separately,
    which asked for the same table twice in one statement-sized job. The stored percent the match
    list shows has to still move with the edit, so the count is paired with the number agreeing
    with the screen.
    """
    viewer, peer, match_id = await _pair(client, "s25_fan")

    resp, seen = await _counted(
        client,
        client.patch(
            "/api/v1/users/me", headers=auth_headers(viewer["token"]), json={"city": "Казань"}
        ),
    )
    assert resp.status_code == 200, resp.text
    counts = _reads(seen)
    assert counts["vector"] == 1, (
        f"answer vectors read {counts['vector']} times while refreshing the pair scores"
    )
    assert counts["profile"] <= 3, (
        f"profile rows read {counts['profile']} times on a profile edit of one pair"
    )

    listed = await client.get("/api/v1/matches", headers=auth_headers(viewer["token"]))
    assert listed.status_code == 200, listed.text
    stored = [m for m in listed.json()["matches"] if m["match_id"] == match_id][0]["compatibility"]
    screen = await client.get(
        f"/api/v1/matches/{match_id}/compatibility", headers=auth_headers(viewer["token"])
    )
    assert screen.status_code == 200, screen.text
    assert stored == screen.json()["overall"], (
        "the list promises a percent the pair screen no longer computes"
    )


async def test_the_answer_recompute_fan_batches_its_pair_too(client: AsyncClient) -> None:
    """Retaking the test refreshes the same pairs, and pays for the rows once.

    `TestService.complete` runs the same fan, and it is the path a retake lands on: the vector this
    request just wrote is the one the pair is scored against.
    """
    viewer, peer, match_id = await _pair(client, "s25_retake")

    resp, seen = await _counted(
        client,
        client.post("/api/v1/tests/complete", headers=auth_headers(viewer["token"])),
    )
    assert resp.status_code == 200, resp.text
    counts = _reads(seen)
    assert counts["vector"] == 1, (
        f"answer vectors read {counts['vector']} times on a completion that refreshes one pair"
    )
