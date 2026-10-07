"""Two people liking each other at the same instant must still form one match.

``MatchService.like`` reads-then-writes: it looks for a mutual like and only then opens the
match. Under the default READ COMMITTED isolation the check has a window: both transactions
insert their own like, and each then asks whether the other liked back while the other's row is
still uncommitted. Both hear "nobody liked me", no match is created, and the two likes sit in the
table belonging to no pair. Nothing repairs it later — liking drops each person from the other's
deck, so the check never runs again. The like that could form a pair therefore takes a
transaction-scoped advisory lock on the unordered pair, so the second like reads only after the
first has committed.

The test below does not hope the race happens by timing; it forces it. The two ``has_liked_back``
calls are made to rendezvous, guaranteeing both read before either commits. Without the lock the
rendezvous releases both into the window and no match forms; with the lock the second like cannot
reach the rendezvous until the first has committed, so the pair is formed once.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.repositories.social_repo import SocialRepository
from .conftest import auth_headers, complete_onboarding, register_and_auth


class _TwoPartyGate:
    """Release the first caller only once the second arrives, or after a short wait.

    The wait is what keeps the locked (correct) path from hanging: the second like never reaches
    the gate while the first holds the pair lock, so the first must be free to proceed alone.
    """

    def __init__(self, parties: int, timeout: float) -> None:
        self._parties = parties
        self._timeout = timeout
        self._count = 0
        self._open = asyncio.Event()

    async def wait(self) -> None:
        self._count += 1
        if self._count >= self._parties:
            self._open.set()
        try:
            await asyncio.wait_for(self._open.wait(), timeout=self._timeout)
        except asyncio.TimeoutError:
            pass


async def _pair(client: AsyncClient) -> tuple[dict, dict]:
    a = await register_and_auth(client, "mutual-a@befos.app")
    b = await register_and_auth(client, "mutual-b@befos.app")
    await complete_onboarding(client, a["token"], name="Аня", gender="female")
    await complete_onboarding(client, b["token"], name="Боря", gender="male")
    return a, b


async def test_simultaneous_single_like_each_side_still_matches(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = await _pair(client)

    # One like each, fired at the same moment — the smallest schedule the bug needs. The 4-plus-4
    # variant elsewhere in the suite hides it: with many requests, at least one ordering commits
    # before another reads, so a match always seems to appear.
    original = SocialRepository.has_liked_back
    gate = _TwoPartyGate(parties=2, timeout=0.5)

    async def rendezvous(self, from_id, to_id):  # type: ignore[no-untyped-def]
        await gate.wait()
        return await original(self, from_id, to_id)

    monkeypatch.setattr(SocialRepository, "has_liked_back", rendezvous)

    responses = await asyncio.gather(
        client.post(f"/api/v1/users/{b['user_id']}/like", headers=auth_headers(a["token"])),
        client.post(f"/api/v1/users/{a['user_id']}/like", headers=auth_headers(b["token"])),
    )
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]

    a_matches = (await client.get("/api/v1/matches", headers=auth_headers(a["token"]))).json()["matches"]
    b_matches = (await client.get("/api/v1/matches", headers=auth_headers(b["token"]))).json()["matches"]

    # The pair exists, exactly once, and both people can see it.
    assert len(a_matches) == 1, "a mutual like that happened at the same instant must still match"
    assert len(b_matches) == 1
    assert a_matches[0]["match_id"] == b_matches[0]["match_id"]

    # Exactly one of the two responses announces the match — the reader that ran second, never
    # both, and never none.
    announced = [r.json()["match"] for r in responses].count(True)
    assert announced == 1
