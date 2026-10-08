"""A city edit recomputed pair percents that city never enters.

``PATCH /api/v1/users/me`` treated three fields — interests, city, dating_goal — as one trigger:
an edit of any of them dropped the cached activity page of every pair *and* rewrote the stored
percent of every pair. The percent is computed from one input type
(``app/compatibility/engine.py:19``): the answer vector, the interest set and the goal. City is
none of those, so the city edit read the match rows, both profiles of every pair, their interest
sets and their answer vectors, ran the engine over all of it, and wrote back the number it had
already found. Measured with ``before_cursor_execute`` on an account holding one pair: a city-only
edit cost eleven statements, four of them that recomputation.

The two questions are now asked separately: the cached page goes when an input of *its* scoring
moved, the percent is rewritten when an input of *the percent* moved.

What must not move: an interests edit still lands a new number on the match row, a goal edit
likewise, a city edit still empties the cached activity page, and the answer the person gets back
still describes the profile they just wrote.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import func, select

from app.models import Match, Recommendation

from .conftest import auth_headers
from .test_chat_receipt_roundtrips import _account, _counted


async def _slugs(client: AsyncClient, token: str) -> list[str]:
    resp = await client.get("/api/v1/users/interests", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    catalog = resp.json()
    items = catalog if isinstance(catalog, list) else catalog.get("interests", [])
    return [item["slug"] for item in items]


async def _pair(client: AsyncClient, viewer: dict, slug: str) -> str:
    peer = await _account(client, f"{slug}@befos.app", name=f"Пётр {slug}", gender="male")
    await client.post(
        f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    back = await client.post(
        f"/api/v1/users/{viewer['user_id']}/like", headers=auth_headers(peer["token"])
    )
    assert back.status_code == 200, back.text
    match_id = back.json()["match_id"]
    assert match_id, "the mutual like did not open a pair"
    return match_id


async def _viewer_with_pairs(client: AsyncClient, prefix: str, pairs: int) -> tuple[dict, list[str]]:
    viewer = await _account(client, f"{prefix}_viewer@befos.app", name="Вера", gender="female")
    ids = [await _pair(client, viewer, f"{prefix}_peer{i}") for i in range(pairs)]
    return viewer, ids


async def _scores(session, match_ids: list[str]) -> list[int]:
    rows = (
        await session.execute(
            select(Match.id, Match.compatibility_score).where(
                Match.id.in_([uuid.UUID(m) for m in match_ids])
            )
        )
    ).all()
    return sorted(int(round(score * 100)) for _id, score in rows)


def _percent_reads(seen: list[str]) -> list[str]:
    """Statements whose only caller is the pair-score recomputation."""
    return [
        statement
        for statement in seen
        if statement.startswith("select")
        and ("from compatibility_profiles" in statement or "from matches " in statement)
    ]


async def test_a_city_edit_does_not_read_the_percent_it_cannot_change(client: AsyncClient) -> None:
    viewer, ids = await _viewer_with_pairs(client, "s35_city", 1)

    resp, seen = await _counted(
        client,
        client.patch(
            "/api/v1/users/me", headers=auth_headers(viewer["token"]), json={"city": "Тверь"}
        ),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["city"] == "Тверь", resp.json()

    reads = _percent_reads(seen)
    assert not reads, (
        f"a city edit read the pairs in {len(reads)} statement(s) to recompute a percent whose "
        f"inputs are the answer vector, the interests and the goal: {reads}"
    )
    assert [s for s in seen if "delete from recommendations" in s], (
        "the city edit stopped dropping the cached activity page it is supposed to drop"
    )


async def test_the_stored_percent_survives_a_city_edit_unchanged(
    client: AsyncClient, session
) -> None:
    viewer, ids = await _viewer_with_pairs(client, "s35_keep", 2)
    before = await _scores(session, ids)

    resp = await client.patch(
        "/api/v1/users/me", headers=auth_headers(viewer["token"]), json={"city": "Сочи"}
    )
    assert resp.status_code == 200, resp.text

    assert await _scores(session, ids) == before, (
        "the city edit moved a stored percent, so city is an input of the engine after all"
    )


async def test_an_interests_edit_still_rewrites_the_percent(client: AsyncClient, session) -> None:
    """The field that is an input of the number must still move the number."""
    viewer, ids = await _viewer_with_pairs(client, "s35_move", 1)
    slugs = await _slugs(client, viewer["token"])
    before = await _scores(session, ids)

    resp = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers(viewer["token"]),
        json={"interests": slugs[20:26]},
    )
    assert resp.status_code == 200, resp.text

    after = await _scores(session, ids)
    assert after != before, (
        f"the interests edit left both pairs at {before}, so the recomputation is now wired to "
        "a field that is an input of the percent"
    )


async def test_a_goal_edit_still_rewrites_the_percent(client: AsyncClient, session) -> None:
    viewer, ids = await _viewer_with_pairs(client, "s35_goal", 1)
    before = await _scores(session, ids)

    resp = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers(viewer["token"]),
        json={"dating_goal": "casual"},
    )
    assert resp.status_code == 200, resp.text

    assert await _scores(session, ids) != before, (
        "the goal edit left the stored percent where it was, though the goal is an input of it"
    )


async def test_the_cached_activity_page_still_drops_when_the_city_moves(
    client: AsyncClient, session
) -> None:
    viewer, ids = await _viewer_with_pairs(client, "s35_cache", 1)
    match_id = ids[0]

    filled = await client.get(
        f"/api/v1/matches/{match_id}/recommendations", headers=auth_headers(viewer["token"])
    )
    assert filled.status_code == 200, filled.text
    stored = (
        await session.execute(
            select(func.count(Recommendation.id)).where(
                Recommendation.match_id == uuid.UUID(match_id)
            )
        )
    ).scalar_one()
    assert stored > 0, "the pair page cached nothing, so the check below would prove nothing"

    resp = await client.patch(
        "/api/v1/users/me", headers=auth_headers(viewer["token"]), json={"city": "Казань"}
    )
    assert resp.status_code == 200, resp.text

    left = (
        await session.execute(
            select(func.count(Recommendation.id)).where(
                Recommendation.match_id == uuid.UUID(match_id)
            )
        )
    ).scalar_one()
    assert left == 0, (
        f"the city edit left {left} cached activities standing, describing a person who no "
        "longer lives where they were scored"
    )
