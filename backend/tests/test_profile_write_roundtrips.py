"""Writing a profile paid for the same rows more than once: per interest, for a list the write
never reads, and again for the response.

``UserRepository.set_profile_interests`` deleted the old rows with one statement and then
inserted the new ones one at a time, so the onboarding write grew with the answer rather than
with the request. Counting the statements of ``POST /users/me/onboarding`` on a fresh account
gave 15 trips for one interest and 44 for the thirty a profile is allowed to carry —
twenty-nine of them the same insert with different parameters. On top of that the route threw
away the profile its service had just written and refreshed and read the same row again, with
its interests, to build the answer: 13 trips became 15.

Both are bounded here. The write stays one statement whatever the answer says, and the totals
below are the stage-29 numbers for the same accounts: 12 trips to write a profile with one
interest, 12 with the thirty a profile may carry. What stage 29 took out is a read nobody
consulted. Every write path loaded the interest list together with the profile, before writing,
and then read it again for the answer — while the write itself replaces the whole set with a
DELETE and one INSERT and never asks what was in it, ``POST /users/me/visibility`` answers with a
single boolean, and ``DELETE /users/me`` answers that the account is gone. Four routes were
paying for that read: 13 trips became 12 for onboarding, 7 became 6 for a one-field ``PATCH``,
12 became 11 for an edit that invalidates a match, 4 became 3 for the visibility switch and 21
became 20 for the erasure. ``GET /users/me`` stayed at 4 — it shows the list, so it is the one
route that is allowed to read it, and it reads it once.

What the batch must still do is checked next to the counts: the set that gets stored is the set
that was answered, a replace really drops the old rows, the cap still cuts at thirty, and a pair
the statement meets twice is skipped instead of aborting the whole write, which is the reason the
conflict guard was there in the first place.
"""

from __future__ import annotations

import uuid
from typing import Callable

from httpx import AsyncClient
from sqlalchemy import event, select

from app.core.database import engine
from app.models import UserInterest
from app.repositories.user_repo import UserRepository

from .conftest import auth_headers, register_and_auth

_INTEREST_INSERT = "insert into user_interests"

# Slugs the seeded catalog actually carries; an unknown slug is dropped on the way in, and a
# test that answered with one would be checking nothing.
_REAL_INTERESTS = ["hiking", "cinema", "cooking", "travel", "music_live", "running"]


def _count_of(seen: list[str], prefix: str) -> int:
    return sum(1 for statement in seen if statement.startswith(prefix))


# The two shapes one question takes: «what does this profile like». The eager loader joins the
# link table onto the profile row, the plain loader selects the interests through it, and the
# identity map answers one of them from the other. A bound that counted only one shape would be
# met by a path that switched to the other, so both are counted as the same read.
_INTEREST_LIST_SHAPES = ("join user_interests", "from interests, user_interests")

# The shape the ORM gives a read of the profile row itself — the entity select, not the join
# that carries somebody else's interests with it.
_PROFILE_ROW = "select profiles.id, profiles.user_id"


def _interest_list_reads(seen: list[str]) -> int:
    return sum(1 for statement in seen if any(shape in statement for shape in _INTEREST_LIST_SHAPES))


def _profile_row_reads(seen: list[str]) -> int:
    return _count_of(seen, _PROFILE_ROW)


async def _counted(coro) -> tuple[object, list[str]]:
    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    listener: Callable[..., None] = record
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        resp = await coro
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    return resp, seen


async def _catalog(client: AsyncClient, token: str) -> list[str]:
    resp = await client.get("/api/v1/users/interests", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return [item["slug"] for item in resp.json()["interests"]]


def _onboarding(slugs: list[str]) -> dict:
    return {
        "name": "Виктор",
        "birth_date": "1996-04-12",
        "city": "Самара",
        "gender": "male",
        "about": "Замер записи профиля",
        "dating_goal": "relationship",
        "interests": slugs,
        "lifestyle": {"smoking": "never", "alcohol": "rarely", "sport": "often"},
        "age_min": 20,
        "age_max": 45,
        "gender_preference": ["female"],
    }


async def _onboard(client: AsyncClient, email: str, slugs: list[str]):
    creds = await register_and_auth(client, email)
    resp, seen = await _counted(
        client.post(
            "/api/v1/users/me/onboarding",
            json=_onboarding(slugs),
            headers=auth_headers(creds["token"]),
        )
    )
    assert resp.status_code == 200, resp.text
    return creds, resp, seen


async def test_the_write_does_not_grow_with_the_answer(client: AsyncClient) -> None:
    """One interest and thirty interests cost the same trips to the database."""
    creds = await register_and_auth(client, "s23_catalog@befos.app")
    slugs = await _catalog(client, creds["token"])
    assert len(slugs) >= 30, f"catalog too small to test the cap: {len(slugs)}"

    _, _, few = await _onboard(client, "s23_few@befos.app", slugs[:1])
    _, _, many = await _onboard(client, "s23_many@befos.app", slugs[:30])

    assert _count_of(few, _INTEREST_INSERT) == 1
    assert _count_of(many, _INTEREST_INSERT) == 1, "the set was written one row per statement"
    assert len(many) == len(few), f"{len(few)} trips for one interest, {len(many)} for thirty"
    assert len(many) <= 12, f"{len(many)} trips to write a profile and its interests"


async def test_the_answer_comes_from_the_row_the_write_returned(client: AsyncClient) -> None:
    """The response is built from the profile read back after the commit, not from a further
    read of it."""
    creds, resp, seen = await _onboard(client, "s23_echo@befos.app", _REAL_INTERESTS)
    assert resp.status_code == 200, resp.text

    assert _profile_row_reads(seen) == 2, (
        f"{_profile_row_reads(seen)} reads of the profile row: loading it for the write "
        "and reading it back after the commit, which is what the answer is built from"
    )
    body = resp.json()
    assert {item["slug"] for item in body["interests"]} == set(_REAL_INTERESTS)
    assert (body["name"], body["city"], body["gender"]) == ("Виктор", "Самара", "male")
    assert body["age_min"] == 20 and body["age_max"] == 45
    assert body["gender_preference"] == ["female"]
    assert body["lifestyle"] == _onboarding(_REAL_INTERESTS)["lifestyle"]
    # The age the answer carries is the server's computed column, so the refresh the response
    # relies on has to have brought it back rather than leaving the pre-write value in place.
    assert body["age"] == 30


async def test_a_write_reads_its_interest_list_once(client: AsyncClient) -> None:
    """The list the answer carries is read for the answer, not twice — once before a write
    that never asks what is in it."""
    creds = await register_and_auth(client, "s29_catalog@befos.app")
    slugs = await _catalog(client, creds["token"])

    creds, resp, seen = await _onboard(client, "s29_interests@befos.app", slugs[:6])
    assert resp.status_code == 200, resp.text
    assert {item["slug"] for item in resp.json()["interests"]} == set(slugs[:6])

    assert _interest_list_reads(seen) == 1, (
        f"{_interest_list_reads(seen)} reads of the interest list on a request that writes it: "
        "the write replaces the whole set with a DELETE and one INSERT and never asks what was "
        "there, so only the answer's read is spent for something"
    )

    resp, second = await _counted(
        client.patch(
            "/api/v1/users/me", json={"about": "строчка"}, headers=auth_headers(creds["token"])
        )
    )
    assert resp.status_code == 200, resp.text
    assert _interest_list_reads(second) == 1, (
        f"{_interest_list_reads(second)} reads of the interest list for a request that names "
        "one field of the profile and leaves the interests alone"
    )


async def test_hiding_a_profile_does_not_read_what_the_person_likes(client: AsyncClient) -> None:
    """The switch answers yes or no; the interest list belongs to neither the question nor the
    answer."""
    creds = await register_and_auth(client, "s29_hide@befos.app")
    slugs = await _catalog(client, creds["token"])
    creds, _, _ = await _onboard(client, "s29_hidden@befos.app", slugs[:6])

    resp, seen = await _counted(
        client.post(
            "/api/v1/users/me/visibility", json={"hidden": True}, headers=auth_headers(creds["token"])
        )
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"hidden": True}

    assert _interest_list_reads(seen) == 0, (
        f"{_interest_list_reads(seen)} reads of the interest list on the request that only "
        "flips `is_hidden`"
    )
    assert len(seen) <= 3, f"{len(seen)} trips to write one boolean"


async def test_deleting_an_account_does_not_read_the_interests_it_drops(client: AsyncClient) -> None:
    """Erasure writes the empty set: what the profile liked is about to be gone, and the answer
    says only that it happened."""
    creds = await register_and_auth(client, "s29_delete@befos.app")
    slugs = await _catalog(client, creds["token"])
    creds, _, _ = await _onboard(client, "s29_gone@befos.app", slugs[:6])

    resp, seen = await _counted(
        client.delete("/api/v1/users/me", headers=auth_headers(creds["token"]))
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": True}

    assert _interest_list_reads(seen) == 0, (
        f"{_interest_list_reads(seen)} reads of the interest list on the request that deletes "
        "those rows"
    )
    assert len(seen) <= 20, f"{len(seen)} trips to erase an account"


async def test_the_stored_set_is_the_answered_set(client: AsyncClient, session) -> None:
    """Fewer statements, same rows: the replace still drops everything it used to."""
    creds = await register_and_auth(client, "s23_set@befos.app")
    slugs = await _catalog(client, creds["token"])
    first, second = slugs[:6], slugs[6:11]

    creds, _, _ = await _onboard(client, "s23_rows@befos.app", first)

    async def _stored(read_creds: dict) -> list[str]:
        # Rollback, not a cached read: the write landed on the request's session, and this
        # session's identity map would otherwise answer from rows it loaded before that write.
        await session.rollback()
        profile = await UserRepository(session).get_profile(uuid.UUID(read_creds["user_id"]))
        return sorted(interest.slug for interest in profile.interests)

    assert await _stored(creds) == sorted(first)

    resp = await client.patch(
        "/api/v1/users/me",
        json={"interests": second},
        headers=auth_headers(creds["token"]),
    )
    assert resp.status_code == 200, resp.text
    assert sorted(item["slug"] for item in resp.json()["interests"]) == sorted(second)
    assert await _stored(creds) == sorted(second), "the old set survived the replace"


async def test_the_cap_still_cuts_the_answer(client: AsyncClient, session) -> None:
    """An answer past thirty interests stores thirty of them, still in one statement."""
    creds = await register_and_auth(client, "s23_cap@befos.app")
    slugs = await _catalog(client, creds["token"])
    assert len(slugs) > 30, f"catalog too small to test the cap: {len(slugs)}"

    answered = list(reversed(slugs))
    creds, _, seen = await _onboard(client, "s23_over@befos.app", answered)
    await session.rollback()
    profile = await UserRepository(session).get_profile(uuid.UUID(creds["user_id"]))
    stored = {interest.slug for interest in profile.interests}

    assert len(stored) == 30
    assert stored == set(answered[:30])
    assert _count_of(seen, _INTEREST_INSERT) == 1


async def test_a_pair_met_twice_is_skipped_not_fatal(client: AsyncClient, session) -> None:
    """The conflict guard survived batching: a duplicate row does not abort the write."""
    creds = await register_and_auth(client, "s23_dup@befos.app")
    resp = await client.post(
        "/api/v1/users/me/onboarding",
        json=_onboarding([]),
        headers=auth_headers(creds["token"]),
    )
    assert resp.status_code == 200, resp.text
    profile = await UserRepository(session).get_profile(uuid.UUID(creds["user_id"]))
    interests = await UserRepository(session).list_interests_by_slugs(
        (await _catalog(client, creds["token"]))[:3]
    )
    twice = [interests[0], interests[0], interests[1], interests[2]]

    _, seen = await _counted(
        UserRepository(session).set_profile_interests(profile.id, twice)
    )
    await session.commit()

    assert _count_of(seen, _INTEREST_INSERT) == 1
    rows = list(
        (
            await session.execute(
                select(UserInterest.interest_id).where(UserInterest.profile_id == profile.id)
            )
        ).scalars().all()
    )
    assert sorted(rows) == sorted(interest.id for interest in interests), "the batch lost a row"
