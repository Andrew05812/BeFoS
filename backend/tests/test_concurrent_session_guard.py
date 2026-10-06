"""The guard that keeps one pytest session per test database.

Nothing in the product is exercised here. What is pinned is the harness's own safety property:
the suite wipes every domain table before each test, so two sessions sharing one database do not
fail — they destroy each other's rows and print the wreckage as regressions. That mistake was
made twice on 2026-10-06, and both times the output looked like a broken product (13 and 14
failures against a tree that passes 245 alone). The lease is what turns that accident into a
refusal with a sentence that names the cause.
"""

from __future__ import annotations

import pytest
from _pytest.outcomes import Exit

from .conftest import (
    _TEST_DB_LOCK_KEY,
    _TestDatabaseLease,
    _refuse_a_second_session,
)

# A key of its own, so these tests cannot disturb the lease the running session holds.
_PROBE_KEY = _TEST_DB_LOCK_KEY + 1


def test_the_running_session_holds_the_database_it_is_about_to_wipe() -> None:
    """The guard is not decorative: while the suite runs, the production key really is held.

    If the session fixture stopped taking the lease, this is the assertion that would notice —
    a newcomer would get the key, which is exactly the state the wipe-per-test cannot survive.
    """
    newcomer = _TestDatabaseLease()
    try:
        assert newcomer.acquire() is False, (
            "nobody holds the test database, so a second session could start wiping rows the "
            "first one is still reading"
        )
    finally:
        newcomer.release()


def test_the_lease_refuses_a_second_holder_and_frees_the_key_when_the_first_leaves() -> None:
    """Acquire, refuse, release, reacquire — the whole mechanism on a key of its own."""
    first = _TestDatabaseLease(key=_PROBE_KEY)
    rival = _TestDatabaseLease(key=_PROBE_KEY)
    try:
        assert first.acquire() is True
        assert rival.acquire() is False, "the second holder got in while the first was alive"

        first.release()
        assert rival.acquire() is True, "releasing did not give the key back"
    finally:
        rival.release()
        first.release()


def test_a_refusal_ends_the_run_naming_the_cause_and_the_way_out(monkeypatch) -> None:
    """The session does not limp on with a taken database; it stops, and says why.

    A guard that only returns False would be read as a test failure and investigated as one.
    """

    class _Refused:
        def acquire(self) -> bool:
            return False

        def release(self) -> None:
            raise AssertionError("nothing was acquired, so there is nothing to release")

    with pytest.raises(Exit) as refusal:
        _refuse_a_second_session(_Refused())  # type: ignore[arg-type]

    message = str(refusal.value)
    assert "wipe" in message, message
    assert "BEFOS_TEST_DB" in message, "the refusal has to name the way out, not just the wall"
