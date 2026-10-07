"""A block and a like landing at the same instant must not leave the pair matched.

Blocking promises a wall: it dissolves the match, and the app keeps no other door into the
conversation. That promise is a *state* invariant — no committed match may coexist with a
committed block for the same pair. ``MatchService.like`` reads-then-writes just like the mutual-
like race, and ``SafetyService.block`` read the match list before deleting it, so under the default
READ COMMITTED the two could interleave: the like checks for a block (none yet), a block commits
and deletes a match that has not been created yet, and then the like creates that match and
commits. Both a block and a match now stand in the tables, the ex-blocker sees the person in the
match list, and — because ``ChatService.send`` only checks membership, not the block — keeps
accepting their messages. Blocking silently failed to block.

The fix borrows the pair advisory lock from the mutual-like repair: ``block`` takes it too, and
``like`` re-reads the block after it holds the lock. Whichever transaction commits last wins —
either the like answers 404 into a committed block, or the block dissolves the match the like
just made. The two tests below force each of those two schedules, so each half of the fix has a
regression that fails without it.

``test_a_block_racing...`` parks the like's first block check until the block has committed, so
the like reads "not blocked" against an absent block and would write its match afterwards — the
schedule the post-lock re-check defuses. ``test_a_matching_like_racing...`` parks the like after
its match row is inserted but before that transaction commits, so a block without the pair lock
deletes nothing (READ COMMITTED cannot see the in-flight row) and commits — the schedule only the
lock defuses, by making the block wait for the like's commit and then dissolve it.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.repositories.social_repo import SocialRepository
from .conftest import auth_headers, complete_onboarding, register_and_auth


async def _pair(client: AsyncClient) -> tuple[dict, dict]:
    a = await register_and_auth(client, "blockrace-a@befos.app")
    b = await register_and_auth(client, "blockrace-b@befos.app")
    await complete_onboarding(client, a["token"], name="Аня", gender="female")
    await complete_onboarding(client, b["token"], name="Боря", gender="male")
    return a, b


async def test_a_block_racing_a_matching_like_leaves_the_pair_unmatched(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = await _pair(client)

    # A has already liked B. When B likes back the pair forms — so B's like is the one that can
    # slip a match past a block committed at the same instant.
    first = await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    assert first.status_code == 200, first.text
    assert first.json()["match"] is False  # one-sided so far

    like_precheck = asyncio.Event()
    block_committed = asyncio.Event()

    original = SocialRepository.is_blocked_either
    state = {"fired": False}

    async def gated(self, x, y):  # type: ignore[no-untyped-def]
        # Read the real answer first: on B's like this is the pre-_ensure_target block check,
        # taken while the block has not committed, so it honestly returns "not blocked". Then,
        # on that first call only, let the block run to completion before the like proceeds.
        # The like is thus guaranteed to have read "no block" and to write its match only after
        # the block's dissolve has already found nothing to delete — the schedule that leaves
        # both rows standing without the fix.
        result = await original(self, x, y)
        if not state["fired"]:
            state["fired"] = True
            like_precheck.set()
            try:
                await asyncio.wait_for(block_committed.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
        return result

    monkeypatch.setattr(SocialRepository, "is_blocked_either", gated)

    responses: dict[str, object] = {}

    async def do_like() -> None:
        responses["like"] = await client.post(
            f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
        )

    async def do_block() -> None:
        await asyncio.wait_for(like_precheck.wait(), timeout=2.0)
        responses["block"] = await client.post(
            f"/api/v1/users/{b['user_id']}/block", json={}, headers=auth_headers(a["token"])
        )
        block_committed.set()

    await asyncio.wait_for(
        asyncio.gather(do_like(), do_block()), timeout=15.0
    )

    # The block itself succeeded — otherwise "no match" would be vacuous.
    block = responses["block"]
    assert block.status_code == 200, block.text
    assert block.json()["blocked"] is True

    async def partners_of(who: dict) -> set[str]:
        listed = await client.get("/api/v1/matches", headers=auth_headers(who["token"]))
        assert listed.status_code == 200, listed.text
        return {m["user_id"] for m in listed.json()["matches"]}

    # A blocked pair must list no match for either side: a match row surviving the race would
    # appear here, because list_matches trusts the block to have dissolved it.
    assert b["user_id"] not in await partners_of(a), (
        "a block that lost the race to a like still leaves the pair matched and chatting"
    )
    assert a["user_id"] not in await partners_of(b)


async def test_a_matching_like_racing_a_block_leaves_the_pair_unmatched(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = await _pair(client)

    first = await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    assert first.status_code == 200, first.text
    assert first.json()["match"] is False

    like_inserted = asyncio.Event()
    block_finished = asyncio.Event()

    original = SocialRepository.ensure_match
    state = {"fired": False}

    async def gated(self, x, y, score):  # type: ignore[no-untyped-def]
        # Insert the match row first, so it exists inside this still-open transaction, then let
        # the block try to dissolve it before this like commits. A block with no pair lock runs
        # now, cannot see the uncommitted row, deletes nothing and commits its block — leaving the
        # match to appear a heartbeat later. A block holding the lock waits here instead, so by
        # the time it deletes, the match is committed and really dissolves.
        result = await original(self, x, y, score)
        if not state["fired"]:
            state["fired"] = True
            like_inserted.set()
            try:
                await asyncio.wait_for(block_finished.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
        return result

    monkeypatch.setattr(SocialRepository, "ensure_match", gated)

    responses: dict[str, object] = {}

    async def do_like() -> None:
        responses["like"] = await client.post(
            f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
        )

    async def do_block() -> None:
        await asyncio.wait_for(like_inserted.wait(), timeout=2.0)
        responses["block"] = await client.post(
            f"/api/v1/users/{b['user_id']}/block", json={}, headers=auth_headers(a["token"])
        )
        block_finished.set()

    await asyncio.wait_for(asyncio.gather(do_like(), do_block()), timeout=20.0)

    block = responses["block"]
    assert block.status_code == 200, block.text
    assert block.json()["blocked"] is True

    async def partners_of(who: dict) -> set[str]:
        listed = await client.get("/api/v1/matches", headers=auth_headers(who["token"]))
        assert listed.status_code == 200, listed.text
        return {m["user_id"] for m in listed.json()["matches"]}

    assert b["user_id"] not in await partners_of(a), (
        "a block that ran before the like committed must still dissolve the match it could not see"
    )
    assert a["user_id"] not in await partners_of(b)

