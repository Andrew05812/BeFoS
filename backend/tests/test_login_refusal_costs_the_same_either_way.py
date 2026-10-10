"""A refused login must not say on the clock whether the address has an account.

`AuthService.authenticate` used to evaluate `user is None or not await verify_password_async(...)`,
and `or` stops at the first true operand: an address with no account never reached bcrypt, while a
wrong password on a known account always paid for one verify. Both answers are 401 with the same
body, so the only thing that separated them was wall time. Measured over a socket against one
uvicorn worker, 5 repeats with the first dropped as warm-up (`s52_login_oracle.json`): an absent
address answered in 24.69 ms median and a wrong password on a known one in 476.08 ms, a gap of
451.39 ms — one bcrypt at `rounds=12`, and nothing else. A caller with a stopwatch therefore
enumerated accounts, which is the fact this route is built to hide and the register route gives
away on purpose with a 409.

The fix is the shape Django uses: both branches pay for exactly one verify, the absent one against
a published filler hash whose plaintext sits next to it in `app/core/security.py`, and the account
check is re-evaluated after the verify so that plaintext cannot sign anybody in.

What these checks hold: the absent branch runs the verify once, and once only, against that filler;
the two refusals still answer byte-identically; the filler is a real hash at the cost factor the app
actually stores, belongs to no account, and its published plaintext authenticates nobody; and the
two branches land within a small factor of each other in wall time. That last one is deliberately
coarse — a test suite is not a stopwatch, and the socket numbers above are the precise claim. It
fails when the branch stops paying for bcrypt at all, which is the regression that reopens the oracle.
"""
from __future__ import annotations

import statistics
import time
import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.core import security
from app.models import User
from app.services import auth_service
from .conftest import register_and_auth

LOGIN = "/api/v1/auth/login"
WRONG_PASSWORD = "Definitely-Wrong-91827364"
# One bcrypt at rounds=12 costs hundreds of ms on the machine these numbers were taken on; the
# branch this file is about skipped it entirely and answered in tens. The floor only has to sit
# between those two, so a faster CI runner does not move the verdict.
VERIFY_FLOOR_MS = 50.0
ABSENT_RATIO_LOW = 0.4
ABSENT_RATIO_HIGH = 2.5
REPS = 5


def _filler(name: str) -> object:
    """Read the filler constants without failing collection on a tree that does not have them."""
    return getattr(security, name, None)


async def _timed_login(client: AsyncClient, email: str, password: str) -> tuple[int, float]:
    started = time.perf_counter()
    response = await client.post(LOGIN, json={"email": email, "password": password})
    return response.status_code, (time.perf_counter() - started) * 1000.0


async def test_an_absent_account_still_pays_for_one_password_check(
    client: AsyncClient, monkeypatch
) -> None:
    """`or` used to short-circuit past the verify for an address with no account."""
    calls: list[str] = []
    real = auth_service.verify_password_async

    async def spy(password: str, password_hash: str) -> bool:
        calls.append(password_hash)
        return await real(password, password_hash)

    monkeypatch.setattr(auth_service, "verify_password_async", spy)

    absent = f"s52-absent-{uuid.uuid4().hex[:8]}@befos.app"
    status_code, _ = await _timed_login(client, absent, WRONG_PASSWORD)

    assert status_code == 401
    assert len(calls) == 1, (
        f"a refused login for an absent address ran the password check {len(calls)} time(s); "
        "the oracle needs it to cost one check, the same one a known account costs"
    )
    filler = _filler("TIMING_FILLER_HASH")
    assert filler is not None, (
        "app/core/security.py has no TIMING_FILLER_HASH, so an address with no account has "
        "nothing to verify against and the clock again says whether it exists"
    )
    assert calls[0] == filler, (
        "the absent branch verified against a hash that is not the published filler — it is "
        "either cheaper than a stored hash or somebody's real one"
    )


async def test_the_two_refusals_still_answer_identically(client: AsyncClient) -> None:
    """The bodies already agreed before this fix; they are the reason the timing was the leak."""
    known = f"s52-known-{uuid.uuid4().hex[:8]}@befos.app"
    await register_and_auth(client, known)
    absent = f"s52-absent-{uuid.uuid4().hex[:8]}@befos.app"

    unknown_address = await client.post(LOGIN, json={"email": absent, "password": WRONG_PASSWORD})
    wrong_password = await client.post(LOGIN, json={"email": known, "password": WRONG_PASSWORD})

    assert (unknown_address.status_code, wrong_password.status_code) == (401, 401)
    assert unknown_address.json() == wrong_password.json()
    assert unknown_address.json()["error"]["message"] == "Invalid email or password."


def test_the_filler_hash_costs_what_a_stored_hash_costs() -> None:
    """Same algorithm marker, same cost factor, and the published plaintext opens it."""
    filler = _filler("TIMING_FILLER_HASH")
    preimage = _filler("TIMING_FILLER_PASSWORD")
    assert filler is not None and preimage is not None, (
        "no filler constants: the absent branch has no hash to pay for"
    )
    assert len(filler) == 60, f"a bcrypt hash is 60 characters, this one is {len(filler)}"
    assert filler.startswith("$2b$")
    # `[:7]` is the algorithm marker and the cost factor, e.g. `$2b$12$`. Read from a hash the app
    # itself produces, so the comparison follows bcrypt rather than a number written down here.
    stored = security.hash_password(WRONG_PASSWORD)
    assert filler[:7] == stored[:7], (
        f"the filler is {filler[:7]} while the app stores {stored[:7]}: verifying it would cost "
        "a different amount than verifying an account, which is the leak again"
    )
    assert security.verify_password(preimage, filler) is True
    assert security.verify_password(WRONG_PASSWORD, filler) is False


async def test_the_published_plaintext_signs_nobody_in(client: AsyncClient, session) -> None:
    """The filler's plaintext is public, so only the account check keeps it worthless."""
    filler = _filler("TIMING_FILLER_HASH")
    preimage = _filler("TIMING_FILLER_PASSWORD")
    assert filler is not None and preimage is not None, (
        "no filler constants: the absent branch has no hash to verify against, so this check has "
        "nothing to prove about the published plaintext"
    )
    await register_and_auth(client, f"s52-known-{uuid.uuid4().hex[:8]}@befos.app")

    status_code, _ = await _timed_login(
        client, f"s52-absent-{uuid.uuid4().hex[:8]}@befos.app", str(preimage)
    )
    assert status_code == 401, (
        "the published filler plaintext signed an address in: the verify passes by construction, "
        "so the missing account has to be what refuses it"
    )

    hashes = (await session.execute(select(User.password_hash))).scalars().all()
    assert len(hashes) >= 1
    assert filler not in hashes, "an account stores the filler hash, so its plaintext is a password"


async def test_the_two_refusals_cost_about_the_same(client: AsyncClient) -> None:
    """Coarse version of the socket measurement: neither refusal may become the cheap one."""
    known = f"s52-known-{uuid.uuid4().hex[:8]}@befos.app"
    await register_and_auth(client, known)
    absent = f"s52-absent-{uuid.uuid4().hex[:8]}@befos.app"

    absent_ms: list[float] = []
    known_ms: list[float] = []
    for _ in range(REPS):
        absent_status, absent_elapsed = await _timed_login(client, absent, WRONG_PASSWORD)
        known_status, known_elapsed = await _timed_login(client, known, WRONG_PASSWORD)
        assert (absent_status, known_status) == (401, 401)
        absent_ms.append(absent_elapsed)
        known_ms.append(known_elapsed)

    absent_median = statistics.median(absent_ms)
    known_median = statistics.median(known_ms)
    assert known_median >= VERIFY_FLOOR_MS, (
        f"a wrong password on a known account answered in {known_median:.1f} ms, below the "
        f"{VERIFY_FLOOR_MS} ms floor: nothing here proved that a bcrypt was paid for"
    )
    assert absent_median >= VERIFY_FLOOR_MS, (
        f"a refused login for an absent address answered in {absent_median:.1f} ms while a known "
        f"account cost {known_median:.1f} ms: the clock still separates the two"
    )
    assert absent_median >= known_median * ABSENT_RATIO_LOW, (
        f"absent {absent_median:.1f} ms against known {known_median:.1f} ms — the absent branch "
        "is cheaper than the one that verifies, which is the enumeration oracle"
    )
    assert absent_median <= known_median * ABSENT_RATIO_HIGH, (
        f"absent {absent_median:.1f} ms against known {known_median:.1f} ms — the absent branch "
        "now costs far more than a verify, which is a different denial of service"
    )
