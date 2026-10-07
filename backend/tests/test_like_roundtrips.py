"""One tap of the heart writes one row and asks the database once about it.

`POST /users/{id}/like` is the action the app is made of, and it was the fattest path the
statement counter had left: fifteen round trips, of which two were pure repeats. The answer
vectors of the two people were read one statement per person from a table keyed by `user_id`
with a unique index that fits both ids, and the like row was read back — then inserted with an
`ON CONFLICT DO NOTHING` that had already decided whether a row was missing. `RETURNING` answers
that question in the write itself, which is also the answer the pair lock was taken to make
reliable: a pre-read can be stale by the moment it is acted on, a conflict clause cannot.

The bounds below are about repeats, not totals: the availability checks stay two, because the
second one runs after the lock and is what separates a like that answers 404 from one that
re-creates a match a fresh block dissolved. Each count is paired with the answer staying the
same — the percent stored has to still be the one the engine computes from those rows, and a
second tap still has to change nothing in the database.
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Callable

from httpx import AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models import Like, Pass
from app.services.compatibility_service import CompatibilityService

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

_MARKERS = {
    "profile": "profiles.name",
    "vector": "compatibility_profiles.vector",
    # The loader of what a person likes. `interests.slug` would also match the read of the
    # interest *names*, which this path does not make.
    "interests": "user_interests",
    "like_insert": "insert into likes",
    "like_select": "from likes",
    "pass_delete": "delete from passes",
}


def _listener(seen: list[tuple[str, str]]) -> Callable[..., None]:
    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append((" ".join(statement.lower().split()), str(parameters)))

    return _record


def _counts(seen: list[tuple[str, str]]) -> Counter[str]:
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


async def _pair(client: AsyncClient, prefix: str) -> tuple[dict, dict]:
    viewer = await _account(client, f"{prefix}_viewer@befos.app", name="Вера", gender="female")
    peer = await _account(client, f"{prefix}_peer@befos.app", name="Пётр", gender="male")
    return viewer, peer


async def test_a_first_like_asks_for_both_answer_vectors_once(
    client: AsyncClient,
) -> None:
    """Two people, one read of their vectors — and the write the tap owes still happens."""
    viewer, peer = await _pair(client, "s26_first")

    resp, seen = await _counted(
        client,
        client.post(
            f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(viewer["token"])
        ),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["liked"] is True

    counts = _counts(seen)
    assert counts["vector"] == 1, (
        f"answer vectors read {counts['vector']} times for two people"
    )
    assert counts["profile"] == 2, (
        f"profile rows read {counts['profile']} times: the peer once for the check and the "
        "viewer once for their own side of the score"
    )
    assert counts["interests"] == 2, f"interest lists read {counts['interests']} times"
    assert counts["like_insert"] == 1, "the tap wrote something other than exactly one like"
    assert counts["pass_delete"] == 1, (
        "a like that landed did not try to drop the pass it replaces"
    )
    assert len(seen) <= 13, f"the first like cost {len(seen)} statements"

    body = resp.json()
    assert 0 <= body["compatibility"] <= 100


async def test_the_like_stores_the_number_the_engine_computes(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The batch must not move the percent: it is the same number the per-person read gives.

    `score_pair` still reads each person on their own, so agreeing with it means the batch carried
    the viewer's row and the peer's row and both vectors.
    """
    viewer, peer = await _pair(client, "s26_score")

    resp = await client.post(
        f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    assert resp.status_code == 200, resp.text

    reference = await CompatibilityService(session).score_pair(
        uuid.UUID(viewer["user_id"]), uuid.UUID(peer["user_id"])
    )
    assert resp.json()["compatibility"] == int(round(reference.overall * 100))

    stored = await session.execute(
        select(Like.compatibility_score).where(
            Like.from_user_id == uuid.UUID(viewer["user_id"]),
            Like.to_user_id == uuid.UUID(peer["user_id"]),
        )
    )
    assert stored.scalar_one() == reference.overall, (
        "the row stores a rounded snapshot, and the match list would show that instead of the "
        "number the screen computes"
    )


async def test_a_second_tap_changes_nothing(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The insert's own conflict clause replaces the read that used to precede it.

    Repeat taps have to keep writing no second row and keep leaving the pass row that was written
    after the first like alone — the behaviour the pre-read produced, now decided by `RETURNING`.
    """
    viewer, peer = await _pair(client, "s26_repeat")
    headers = auth_headers(viewer["token"])
    target = peer["user_id"]

    first = await client.post(f"/api/v1/users/{target}/like", headers=headers)
    assert first.status_code == 200, first.text
    passed = await client.post(f"/api/v1/users/{target}/pass", headers=headers)
    assert passed.status_code == 200, passed.text

    resp, seen = await _counted(
        client, client.post(f"/api/v1/users/{target}/like", headers=headers)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["match"] is False, "a second tap fired the match moment again"

    counts = _counts(seen)
    assert counts["like_insert"] == 1, "the second tap issued its INSERT anyway"
    assert counts["pass_delete"] == 0, (
        "the second tap deleted the pass the viewer put down after liking — the row a like that "
        "was already there does not replace"
    )
    assert len(seen) <= 12, f"the repeat tap cost {len(seen)} statements"

    rows = await session.execute(
        select(Like.id).where(
            Like.from_user_id == uuid.UUID(viewer["user_id"]),
            Like.to_user_id == uuid.UUID(target),
        )
    )
    assert len(rows.all()) == 1, "the pair has more than one like row"
    left = await session.execute(
        select(Pass.id).where(
            Pass.from_user_id == uuid.UUID(viewer["user_id"]),
            Pass.to_user_id == uuid.UUID(target),
        )
    )
    assert len(left.all()) == 1, "the pass row written between two taps disappeared"


async def test_a_like_after_a_pass_drops_that_pass(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The branch the conflict clause reports is the branch that still cleans the pass up."""
    viewer, peer = await _pair(client, "s26_passfirst")
    headers = auth_headers(viewer["token"])

    passed = await client.post(
        f"/api/v1/users/{peer['user_id']}/pass", headers=headers
    )
    assert passed.status_code == 200, passed.text

    resp = await client.post(f"/api/v1/users/{peer['user_id']}/like", headers=headers)
    assert resp.status_code == 200, resp.text

    gone = await session.execute(
        select(Pass.id).where(
            Pass.from_user_id == uuid.UUID(viewer["user_id"]),
            Pass.to_user_id == uuid.UUID(peer["user_id"]),
        )
    )
    assert gone.all() == [], "liking somebody left the pass in front of them standing"
