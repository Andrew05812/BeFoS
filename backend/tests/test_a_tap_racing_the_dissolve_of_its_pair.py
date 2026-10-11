"""A tap that races the dissolution of its pair must be refused, not crash.

Stage 63 gave `activity_preferences` a `match_id` column with `ForeignKey("matches.id", ondelete=
"CASCADE")`, because a choice recorded for one pair cannot be read back on another pair's page. That
new edge puts the select route into a genre this repository has closed five times before: between
the membership read at the top of `RecommendationService.mark_selected` and the INSERT there is a
wide window, and `SafetyService.block` (stage 9) deletes the parent `matches` row in it. The child
INSERT then names a `match_id` that is already gone, asyncpg raises `ForeignKeyViolationError` on
`activity_preferences_match_id_fkey`, and the app's generic handler answers HTTP 500 on a route the
client fires right after a chat send — for a pair that simply stopped existing.

The repair is the one the other writers of match children already use: take the pair advisory lock
and re-check the parent under it with a fresh `select(Match.id)`, which bypasses the identity map.
Whoever commits last then wins cleanly — the tap lands under the lock and the later dissolve
cascades the row away (204), or the dissolve lands first and the re-check answers 404 without
reaching the INSERT. Neither is a crash, and in neither case does a row survive its pair.

The red state of this check is not the tree before stage 63 — there was no such foreign key to
violate. It is stage 63's own schema with the two lock lines taken out, which is what the edge
without the lock is, and it was run that way.
"""
from __future__ import annotations

import asyncio
import uuid

from httpx import AsyncClient
from sqlalchemy import text

from app.repositories.activity_repo import ActivityRepository
from .conftest import auth_headers, complete_onboarding, register_and_auth


async def _matched_pair(client: AsyncClient, prefix: str) -> tuple[dict, dict, str]:
    a = await register_and_auth(client, f"{prefix}-a@befos.app")
    b = await register_and_auth(client, f"{prefix}-b@befos.app")
    await complete_onboarding(client, a["token"], name="Аня", gender="female")
    await complete_onboarding(client, b["token"], name="Боря", gender="male")
    await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    second = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    assert second.status_code == 200, second.text
    assert second.json()["match"] is True
    return a, b, second.json()["match_id"]


async def _rows_without_a_pair() -> int:
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "select count(*) from activity_preferences ap "
                    "where ap.match_id is not null "
                    "and not exists (select 1 from matches m where m.id = ap.match_id)"
                )
            )
        ).scalar_one()


async def test_a_tap_racing_the_dissolve_of_its_pair_is_refused_not_crashed(
    client: AsyncClient, monkeypatch
) -> None:
    """The catalogue check is the last read before the write, so it is where the gate goes.

    `mark_selected` reads the membership, then the activity, then writes. Holding it at the activity
    read lets the block commit its `DELETE FROM matches` in exactly the window the lock closes.
    """
    a, b, match_id_str = await _matched_pair(client, "tapdissolve")
    match_id = uuid.UUID(match_id_str)
    cards = await client.get(
        f"/api/v1/matches/{match_id}/recommendations?force=true",
        headers=auth_headers(a["token"]),
    )
    assert cards.status_code == 200, cards.text
    activity_id = cards.json()["recommendations"][0]["activity"]["id"]

    read_reached = asyncio.Event()
    block_committed = asyncio.Event()
    original = ActivityRepository.get_by_ids
    state = {"fired": False}

    async def gated(self, activity_ids):  # type: ignore[no-untyped-def]
        result = await original(self, activity_ids)
        if not state["fired"]:
            state["fired"] = True
            read_reached.set()
            try:
                await asyncio.wait_for(block_committed.wait(), timeout=1.5)
            except asyncio.TimeoutError:
                pass
        return result

    monkeypatch.setattr(ActivityRepository, "get_by_ids", gated)

    responses: dict[str, object] = {}

    async def do_tap() -> None:
        responses["tap"] = await client.post(
            f"/api/v1/matches/{match_id}/recommendations/{activity_id}/select",
            headers=auth_headers(a["token"]),
        )

    async def do_block() -> None:
        await asyncio.wait_for(read_reached.wait(), timeout=6.0)
        responses["block"] = await client.post(
            f"/api/v1/users/{b['user_id']}/block", json={}, headers=auth_headers(a["token"])
        )
        block_committed.set()

    await asyncio.wait_for(asyncio.gather(do_tap(), do_block()), timeout=30.0)

    assert responses["block"].status_code == 200, responses["block"].text  # type: ignore[union-attr]
    tap = responses["tap"]
    # Without the pair lock this is a 500 built on ForeignKeyViolationError; with it the tap either
    # lands under the lock (204, then the dissolve cascades it) or the dissolve lands first (404).
    assert tap.status_code in (204, 404), tap.text  # type: ignore[union-attr]

    orphans = await _rows_without_a_pair()
    assert orphans == 0, f"{orphans} recorded choices outlived the pair they were made for"
