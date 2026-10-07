"""Reading one profile must not ask the database for the same person twice.

``GET /api/v1/users/{id}`` is the most data-backed screen behind the deck, and the probe found it
costing 73.7…77.6 ms of median against 1.5…1.6 ms of SQL (`docs/SCALE_PLAN.md` §3): 16 separate
trips to the server, not a slow query. Most of the trips were repeats — the service built the
compatibility input for the viewer and for the target, then asked the scoring path to build the
same two inputs again, and the target's row was read a second time by id although the card was
already held.

The bounds are about repeats, not about a magic total: each person's profile row, answer vector
and interest list are read once per request, however many numbers the response carries. The last
test pins the product of that shortcut — the percent must be the number the engine gives when it
reads both people from scratch.
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Callable

from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.services.compatibility_service import CompatibilityService

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

# Which statement reads which part of a person. Counted by the columns each loader selects, so
# the interest loader and the profile loader are not mistaken for one another.
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


async def _counted_get(client: AsyncClient, token: str, user_id: str) -> tuple[int, Counter[str]]:
    seen: list[str] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        resp = await client.get(
            f"/api/v1/users/{user_id}", headers=auth_headers(token)
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    assert resp.status_code == 200, resp.text
    return len(seen), _reads(seen)


async def _account(client: AsyncClient, email: str, *, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def test_one_profile_read_asks_each_table_once(client: AsyncClient) -> None:
    viewer = await _account(client, "rt_viewer@befos.app", name="Вера", gender="female")
    peer = await _account(client, "rt_peer@befos.app", name="Пётр", gender="male")

    total, counts = await _counted_get(client, viewer["token"], peer["user_id"])

    # Two people answer for one card: each row of each kind is read once per person.
    assert counts["profile"] == 2, f"profile rows read {counts['profile']} times: {total} queries"
    assert counts["vector"] == 2, f"answer vectors read {counts['vector']} times"
    assert counts["interests"] == 2, f"interest lists read {counts['interests']} times"
    assert counts["photos"] == 1, f"photos read {counts['photos']} times"
    # The slack above the 7 reads that do the work is the auth lookup and the visibility checks;
    # it is a ceiling on the whole request, so a new per-card query in this path shows up here.
    assert total <= 10, f"{total} trips to the database for one profile card"


async def test_the_card_carries_the_number_the_engine_gives(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Fewer reads may not mean a different percent: the shortcut and a cold scoring agree."""
    viewer = await _account(client, "rt_ref_viewer@befos.app", name="Вера", gender="female")
    peer = await _account(client, "rt_ref_peer@befos.app", name="Пётр", gender="male")

    resp = await client.get(
        f"/api/v1/users/{peer['user_id']}", headers=auth_headers(viewer["token"])
    )
    assert resp.status_code == 200, resp.text
    card = resp.json()

    reference = await CompatibilityService(session).score_pair(
        uuid.UUID(viewer["user_id"]), uuid.UUID(peer["user_id"])
    )
    assert card["compatibility"] == reference.overall_percent
    assert card["shared_interests"] and card["interests"]


async def test_reading_your_own_card_reads_you_once(client: AsyncClient) -> None:
    """The branch that opens your own profile is the same shortcut, so it must not double up."""
    me = await _account(client, "rt_self@befos.app", name="Саша", gender="male")

    total, counts = await _counted_get(client, me["token"], me["user_id"])

    assert counts["profile"] == 1, "the person the request is about is read more than once"
    assert counts["vector"] == 1
    assert counts["interests"] == 1
    assert total <= 8, f"{total} trips to the database to open your own card"


async def test_the_like_repeats_only_the_check_that_has_to_repeat(client: AsyncClient) -> None:
    """`POST /users/{id}/like` checks the peer twice and reads the peer once.

    The pair lock forces a second visibility check after the lock is held (see the race tests),
    so two checks are the invariant, not waste. What was waste is what the first one cost: it
    loaded the person, their city and their whole interest list to answer four boolean columns,
    and then read them again properly after the lock. The score used to fetch both people a
    third time as well.

    The two rows stay separate because each of them is read for a different reason; the vectors
    do not, and since stage 26 both of them arrive in the one batch read the score needs.
    """
    viewer = await _account(client, "rt_like_viewer@befos.app", name="Вера", gender="female")
    peer = await _account(client, "rt_like_peer@befos.app", name="Пётр", gender="male")

    seen: list[str] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        resp = await client.post(
            f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(viewer["token"])
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)

    assert resp.status_code == 200, resp.text
    counts = _reads(seen)
    assert counts["profile"] == 2, (
        f"peer and viewer rows read {counts['profile']} times: the post-lock check and the "
        "viewer's own row is the floor, and the pre-lock check asks for a boolean"
    )
    assert counts["interests"] == 2, "an interest list read more than once per person"
    assert counts["vector"] == 1, "the two answer vectors did not come from one batch read"
