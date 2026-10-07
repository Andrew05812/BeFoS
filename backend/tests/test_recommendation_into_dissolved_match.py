"""A cached-miss recommendation write that races a dissolve of its match must not answer 500.

`RecommendationService.for_match` reads the match via `session.get(Match, match_id)`, then scores
the pair — `_signal` on each user, `list_for_cities` on the whole activity catalogue, the pure
recommendation engine over both — and only then calls `ActivityRepository.replace_recommendations`,
which DELETEs the cached rows and INSERTs eight new `recommendations` rows whose `match_id` column
carries `ForeignKey("matches.id", ondelete="CASCADE")`. `SafetyService.block` (stage 9) and
`SafetyService.delete_account`'s purge (stage 13) both hold the pair advisory lock and delete the
parent; the recommendation path never took that lock, so either writer could commit its
`DELETE FROM matches` in the wide window between the initial membership read and the child
INSERT. The INSERT then references a `match_id` that is already gone, asyncpg raises
`ForeignKeyViolationError` on `recommendations_match_id_fkey`, the app's generic `Exception`
handler turns it into HTTP 500 on `GET /api/v1/matches/{id}/recommendations?force=true` — the
exact class closed on stages 11, 12, and 13, but on a different child of the match row.

The fix has the cache-miss write path take the same pair lock the other writers already serialise
on, and re-check the parent under it via a fresh `select(Match.id)` that bypasses the identity map.
Whichever commits last wins cleanly: the recommendation either writes under the lock and the later
dissolve cascades it away (200, then a follow-up 404 on any further GET), or the dissolve lands
first and the post-lock re-check answers 404 without ever reaching `replace_recommendations`.
"""

from __future__ import annotations

import asyncio
import uuid

from httpx import AsyncClient
from sqlalchemy import or_, select

from app.core.database import AsyncSessionLocal
from app.models import Match, Recommendation
from app.services.recommendation_service import RecommendationService
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


async def _recommendations_involving(match_id: uuid.UUID) -> list[uuid.UUID]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Recommendation.id).where(Recommendation.match_id == match_id)
            )
        ).all()
    return [r[0] for r in rows]


async def _matches_involving(*user_ids: uuid.UUID) -> list[uuid.UUID]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Match.id).where(
                    or_(Match.user_a_id.in_(user_ids), Match.user_b_id.in_(user_ids))
                )
            )
        ).all()
    return [r[0] for r in rows]


async def test_a_recommendation_write_racing_the_dissolve_of_its_match_is_refused_not_crashed(
    client: AsyncClient, monkeypatch
) -> None:
    """`_signal` returns after the initial membership read and is the last gate before the write.

    Holding the recomputation at `_signal` forces the block to commit its DELETE during the same
    window the fix later closes with `lock_pair` + `match_still_present`. Without that lock, the
    next step in the write path is `replace_recommendations` and its INSERT into `recommendations`
    — a child row against an absent `matches.id` and a foreign-key violation.
    """
    a, b, match_id_str = await _matched_pair(client, "recdissolve")
    match_id = uuid.UUID(match_id_str)

    signal_reached = asyncio.Event()
    block_committed = asyncio.Event()
    original = RecommendationService._signal
    state = {"fired": False}

    async def gated(self, user_id):  # type: ignore[no-untyped-def]
        result = await original(self, user_id)
        if not state["fired"]:
            state["fired"] = True
            signal_reached.set()
            try:
                await asyncio.wait_for(block_committed.wait(), timeout=1.5)
            except asyncio.TimeoutError:
                pass
        return result

    monkeypatch.setattr(RecommendationService, "_signal", gated)

    responses: dict[str, object] = {}

    async def do_recompute() -> None:
        responses["recs"] = await client.get(
            f"/api/v1/matches/{match_id}/recommendations?force=true",
            headers=auth_headers(b["token"]),
        )

    async def do_block() -> None:
        await asyncio.wait_for(signal_reached.wait(), timeout=6.0)
        responses["block"] = await client.post(
            f"/api/v1/users/{b['user_id']}/block", json={}, headers=auth_headers(a["token"])
        )
        block_committed.set()

    await asyncio.wait_for(asyncio.gather(do_recompute(), do_block()), timeout=30.0)

    block = responses["block"]
    assert block.status_code == 200, block.text

    recs = responses["recs"]
    # Pre-fix: the write's INSERT lands against a match_id the block has already deleted
    # and the FK violation surfaces as 500. Post-fix: either the write lands under the
    # pair lock and the later block cascades it away (200), or the block lands first and
    # the post-lock re-check answers 404. Neither is a crash.
    assert recs.status_code in (200, 404), recs.text

    # And the invariant: no Recommendation row survives the pair's dissolution.
    orphans = await _recommendations_involving(match_id)
    assert orphans == [], f"recommendation outlived the match it belongs to: {orphans}"
    survivors = await _matches_involving(uuid.UUID(a["user_id"]), uuid.UUID(b["user_id"]))
    assert survivors == [], f"match survived the block: {survivors}"
