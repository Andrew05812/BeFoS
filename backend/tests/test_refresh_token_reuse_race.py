"""A single-use refresh token must rotate once, even when it arrives twice at the same instant.

Rotation is the defence that makes a stolen refresh token useless: redeem it, the old one dies, a
new pair is born. ``AuthService.refresh`` used to read the stored row, check ``revoked`` and then
revoke it — a read-then-write with a window. Two requests bearing the same token both read
``revoked = false`` before either commits, so both rotate and both mint a fresh pair: one stolen
token, two live sessions, and the rotation guarantee is void. Sequential reuse was already caught
(the second sees the row revoked); only the simultaneous replay slipped through.

The fix makes a single ``UPDATE … WHERE revoked = false`` (``consume``) the first touch of the row
and its own arbiter: the row lock serialises the two requests, the loser re-evaluates the predicate
after the winner commits, matches no row, and is refused — the same answer a serial retry gets. The
read that opened the window is gone rather than merely locked, so this test now makes the two
requests rendezvous at the redeem itself, which is where the decision is made.

Without the fix both return 200 with two different new tokens; with it exactly one succeeds.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.repositories.token_repo import TokenRepository
from .conftest import register_and_auth


class _TwoPartyGate:
    """Release the first caller only once the second arrives, or after a short wait.

    The wait keeps a lone redemption (the sequential path used elsewhere) from hanging: the
    second caller never arrives, so the first must be free to proceed alone.
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


async def test_the_same_refresh_token_redeemed_twice_at_once_rotates_once(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    account = await register_and_auth(client, "refresh-race@befos.app")
    stolen = account["refresh"]

    original = TokenRepository.consume
    gate = _TwoPartyGate(parties=2, timeout=1.0)

    async def rendezvous(self, token_hash):  # type: ignore[no-untyped-def]
        await gate.wait()
        return await original(self, token_hash)

    monkeypatch.setattr(TokenRepository, "consume", rendezvous)

    responses = await asyncio.gather(
        client.post("/api/v1/auth/refresh", json={"refresh_token": stolen}),
        client.post("/api/v1/auth/refresh", json={"refresh_token": stolen}),
    )

    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 401], (
        "a refresh token redeemed twice in the same instant must rotate exactly once, "
        f"got {[r.status_code for r in responses]}: {[r.text for r in responses]}"
    )

    # The one that won handed back a brand-new pair, and the stolen token is now dead: a third,
    # serial attempt against it is refused like any reused token.
    dead = await client.post("/api/v1/auth/refresh", json={"refresh_token": stolen})
    assert dead.status_code == 401, dead.text
