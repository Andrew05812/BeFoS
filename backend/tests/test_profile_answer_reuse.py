"""A profile write raises its own row twice with the same question, and answers from the second.

``before_cursor_execute`` paired every statement of a profile write with its parameters and
found the same pair twice on each of them: ``select profiles.id, profiles.user_id, …  where
profiles.user_id = $1`` runs once to load the row the request is about to write and once more,
after the commit, to build the answer. The session is configured with ``expire_on_commit=False``
(``app/core/database.py:43``), so the row the write holds is readable after the commit and carries
exactly the values that request wrote — ``age`` is a property over ``birth_date``, not a column the
server computes, so nothing in the answer waits on the second read. What the answer genuinely adds
is the interest set, and a write that replaces that set already read those rows from the catalogue.

So the second read of the row buys nothing, and on the writes that replace the set the list read
buys nothing either.

What must not move is the answer: the same fields, the same interest order, the same status.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable

from httpx import AsyncClient
from sqlalchemy import event

from app.core.database import engine

from .conftest import auth_headers, register_and_auth

# The entity read of the profile row. The join that carries another person's interests is a
# different shape and belongs to other paths; this file counts only the row of the writer.
_PROFILE_ROW = "select profiles.id, profiles.user_id"

# Both shapes of «what does this profile like»: the eager loader hanging the link table onto the
# row, and the plain select through it. A bound that named one of them would be met by a path
# that switched to the other.
_INTEREST_LIST_SHAPES = ("join user_interests", "from interests, user_interests")

_INTEREST_SLUG_READ = "select interests.id, interests.slug, interests.name, interests.category from interests where interests.slug in"

_WRITTEN = ["hiking", "cinema", "cooking", "travel"]


def _profile_row_reads(seen: list[str]) -> int:
    return sum(1 for statement in seen if statement.startswith(_PROFILE_ROW))


def _interest_list_reads(seen: list[str]) -> int:
    return sum(1 for s in seen if any(shape in s for shape in _INTEREST_LIST_SHAPES))


def _slug_reads(seen: list[str]) -> int:
    return sum(1 for s in seen if s.startswith(_INTEREST_SLUG_READ))


def _repeats(seen: list[tuple[str, str]]) -> list[tuple[str, int]]:
    from collections import Counter

    counts = Counter(seen)
    return [(text, n) for (text, _params), n in counts.items() if n > 1]


async def _counted(client: AsyncClient, awaitable: Awaitable) -> tuple[object, list[str]]:
    seen: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    try:
        resp = await awaitable
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)
    return resp, seen


async def _account(client: AsyncClient, email: str, interests: list[str]) -> dict:
    creds = await register_and_auth(client, email)
    resp = await client.post(
        "/api/v1/users/me/onboarding",
        headers=auth_headers(creds["token"]),
        json={
            "name": "Виктор",
            "birth_date": "1996-05-10",
            "gender": "male",
            "city": "Самара",
            "dating_goal": "relationship",
            "interests": interests,
        },
    )
    assert resp.status_code == 200, resp.text
    creds["profile"] = resp.json()
    return creds


async def test_an_edit_of_one_field_raises_the_written_row_once(client: AsyncClient) -> None:
    """The name edit is the smallest write there is, and it paid for its row twice."""
    creds = await _account(client, f"s36_name_{uuid.uuid4().hex[:6]}@befos.app", _WRITTEN)
    resp, seen = await _counted(
        client,
        client.patch(
            "/api/v1/users/me", json={"name": "Пётр"}, headers=auth_headers(creds["token"])
        ),
    )
    assert resp.status_code == 200, resp.text
    assert _profile_row_reads(seen) == 1, (
        f"the profile row was read {_profile_row_reads(seen)} times by one edit of one field: "
        "the row the write holds is readable after the commit, and the answer needs only the "
        "interest set from the table"
    )
    assert len(seen) <= 5, f"{len(seen)} statements to change a name"
    body = resp.json()
    assert body["name"] == "Пётр"
    assert {item["slug"] for item in body["interests"]} == set(_WRITTEN)


async def test_a_write_of_the_set_answers_the_rows_it_already_read(client: AsyncClient) -> None:
    """Interests are read from the catalogue to be stored; the answer uses that same set."""
    creds = await _account(client, f"s36_set_{uuid.uuid4().hex[:6]}@befos.app", ["music_live"])
    resp, seen = await _counted(
        client,
        client.patch(
            "/api/v1/users/me",
            json={"interests": _WRITTEN},
            headers=auth_headers(creds["token"]),
        ),
    )
    assert resp.status_code == 200, resp.text
    assert _profile_row_reads(seen) == 1, (
        f"the profile row was read {_profile_row_reads(seen)} times by a write that replaces the "
        "interest set"
    )
    assert _slug_reads(seen) == 1, f"the catalogue was read {_slug_reads(seen)} times"
    assert _interest_list_reads(seen) == 0, (
        f"{_interest_list_reads(seen)} reads of the stored set: the write just wrote it, and the "
        "rows it wrote are the rows the catalogue read brought back"
    )
    assert {item["slug"] for item in resp.json()["interests"]} == set(_WRITTEN)


async def test_an_edit_that_leaves_the_set_alone_still_reads_it_once(client: AsyncClient) -> None:
    """A goal edit touches no interest, so the answer's set has to come from the table — once."""
    creds = await _account(client, f"s36_goal_{uuid.uuid4().hex[:6]}@befos.app", _WRITTEN)
    resp, seen = await _counted(
        client,
        client.patch(
            "/api/v1/users/me",
            json={"dating_goal": "marriage"},
            headers=auth_headers(creds["token"]),
        ),
    )
    assert resp.status_code == 200, resp.text
    assert _profile_row_reads(seen) == 1, (
        f"the profile row was read {_profile_row_reads(seen)} times by a goal edit"
    )
    assert _interest_list_reads(seen) == 1, (
        f"the stored interest set was read {_interest_list_reads(seen)} times"
    )
    assert {item["slug"] for item in resp.json()["interests"]} == set(_WRITTEN)


async def test_onboarding_answers_from_the_row_it_wrote(client: AsyncClient) -> None:
    """The setup request writes the row, the set and the preferences, and then read the row again."""
    creds = await register_and_auth(client, f"s36_onb_{uuid.uuid4().hex[:6]}@befos.app")
    resp, seen = await _counted(
        client,
        client.post(
            "/api/v1/users/me/onboarding",
            headers=auth_headers(creds["token"]),
            json={
                "name": "Виктор",
                "birth_date": "1996-05-10",
                "gender": "male",
                "city": "Самара",
                "dating_goal": "relationship",
                "interests": _WRITTEN,
            },
        ),
    )
    assert resp.status_code == 200, resp.text
    assert _profile_row_reads(seen) == 1, (
        f"onboarding read the profile row {_profile_row_reads(seen)} times"
    )
    assert _interest_list_reads(seen) == 0, (
        f"onboarding read the set it had just written {_interest_list_reads(seen)} times"
    )
    assert len(seen) <= 10, f"{len(seen)} statements to answer an onboarding"


async def test_the_answer_of_a_write_is_the_answer_of_a_fresh_read(client: AsyncClient) -> None:
    """Nothing in the response moved: the same fields, the same order of the same set."""
    creds = await _account(client, f"s36_echo_{uuid.uuid4().hex[:6]}@befos.app", ["cinema"])
    written, _ = await _counted(
        client,
        client.patch(
            "/api/v1/users/me",
            json={"interests": _WRITTEN, "city": "Казань"},
            headers=auth_headers(creds["token"]),
        ),
    )
    assert written.status_code == 200, written.text
    shown = await client.get("/api/v1/users/me", headers=auth_headers(creds["token"]))
    assert shown.status_code == 200, shown.text
    answer = written.json()
    fresh = shown.json()
    assert answer == fresh, (
        "the answer the write built from its own row is not the answer a fresh read gives for "
        f"the same account: {sorted(set(answer) ^ set(fresh))} differ as fields, and where the "
        "fields agree the values do not — "
        + "; ".join(
            f"{key}: {answer.get(key)!r} against {fresh.get(key)!r}"
            for key in sorted(answer)
            if answer.get(key) != fresh.get(key)
        )
    )
