"""A profile write named interests the catalogue does not carry, and the answer kept the secret.

Measured on the live stand before this stage (a throwaway account, ``PATCH /users/me`` and
``POST /users/me/onboarding`` against the running container): a body naming five slugs of which two
do not exist returned ``200`` with three interests and no ``error`` field at all. A body naming all
forty catalogue slugs returned ``200`` with thirty, and the ten that survived differed between the
alphabetical body and the reversed one by twenty slugs — which ten vanish is decided by the order
the client happened to list them in. The sharpest case: a profile holding thirty interests, patched
with three names of which one is real, came back ``200`` with one interest, and the read afterwards
confirmed one stored row. Twenty-nine interests the person had actually chosen were gone, and
nothing in the response said so.

All three silences are the same missing check: the write turned the named set into catalogue rows
and stored what it found, never comparing the two counts. What the checks below pin is that a name
the catalogue does not know is now refused rather than dropped, that a past-the-ceiling answer is
refused rather than cut, and that a refused write leaves the stored set — and the rest of the
body — exactly as it was.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import event

from app.core.database import engine
from app.repositories.user_repo import UserRepository

from .conftest import auth_headers, complete_onboarding, register_and_auth

# Slugs the seeded catalogue really carries; the refusal is about names it does not carry, so a
# test that used a made-up name for the accepted half would be checking the wrong thing.
_KNOWN = ["hiking", "cinema", "cooking", "travel", "music_live", "running"]
_UNKNOWN = ["underwater_basket_weaving", "competitive_napping"]


async def _stored(client: AsyncClient, session, user_id: str) -> list[str]:
    # Rollback, not a cached read: the write landed on the request's session, and this session's
    # identity map would otherwise answer from rows it loaded before that write.
    await session.rollback()
    profile = await UserRepository(session).get_profile(uuid.UUID(user_id))
    return sorted(interest.slug for interest in profile.interests)


async def _statements(coro) -> tuple[object, list[str]]:
    """The SQL one request actually issued, so a refusal can be told from a half-write."""
    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    listener = record
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        result = await coro
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    return result, seen


def _patch(client: AsyncClient, token: str, slugs: list[str], **extra):
    return client.patch("/api/v1/users/me", json={"interests": slugs, **extra},
                        headers=auth_headers(token))


async def _catalog(client: AsyncClient, token: str) -> list[str]:
    resp = await client.get("/api/v1/users/interests", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return [item["slug"] for item in resp.json()["interests"]]


async def _onboarded(client: AsyncClient, email: str, slugs: list[str]) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], interests=slugs)
    return creds


async def test_a_name_the_catalogue_does_not_know_is_refused(client: AsyncClient) -> None:
    """The answer used to be a shorter list; now it is a refusal that says which name."""
    creds = await _onboarded(client, "s65_refuse@befos.app", _KNOWN[:3])

    resp, seen = await _statements(
        _patch(client, creds["token"], [_KNOWN[0], _UNKNOWN[0]])
    )

    assert resp.status_code == 422, resp.text
    body = resp.json()["error"]
    assert body["code"] == "validation_error", body
    assert _UNKNOWN[0] in body["message"], body
    assert _KNOWN[0] not in body["message"], "a name the catalogue knows is not part of the fault"
    assert not any(s.startswith("delete from user_interests") for s in seen), seen


async def test_the_refusal_names_every_unknown_name(client: AsyncClient) -> None:
    """One refusal for both faults, so the caller does not have to guess the second."""
    creds = await _onboarded(client, "s65_both@befos.app", _KNOWN[:3])

    resp = await _patch(client, creds["token"], [*_KNOWN[:1], *_UNKNOWN])

    message = resp.json()["error"]["message"]
    for slug in _UNKNOWN:
        assert slug in message, message


async def test_a_refused_write_leaves_the_answered_set_stored(client: AsyncClient, session) -> None:
    """The case that cost twenty-nine interests: one real name and two made-up ones.

    Before this stage the same body returned ``200`` with one row stored. The refusal has to
    arrive before the DELETE that replaces the set, otherwise refusing a write would still
    erase the set it refused to change.
    """
    creds = await _onboarded(client, "s65_keep@befos.app", _KNOWN[:3])

    resp = await _patch(client, creds["token"], [_KNOWN[3], *_UNKNOWN])

    assert resp.status_code == 422, resp.text
    assert await _stored(client, session, creds["user_id"]) == sorted(_KNOWN[:3])


async def test_a_refused_write_leaves_the_rest_of_the_body_alone(client: AsyncClient, session) -> None:
    """A refusal about interests must not half-apply the other fields of the same body."""
    creds = await _onboarded(client, "s65_city@befos.app", _KNOWN[:3])

    resp = await _patch(client, creds["token"], _UNKNOWN, city="Омск")

    assert resp.status_code == 422, resp.text
    me = await client.get("/api/v1/users/me", headers=auth_headers(creds["token"]))
    assert me.json()["city"] != "Омск", me.json()["city"]


async def test_thirty_names_are_kept_and_the_thirty_first_is_refused(
    client: AsyncClient, session
) -> None:
    """The ceiling stays, and it moved from a silent cut to an answer the caller can act on."""
    creds = await _onboarded(client, "s65_cap@befos.app", _KNOWN[:3])
    catalogue = await _catalog(client, creds["token"])
    assert len(catalogue) > 30, f"catalogue too small to reach the ceiling: {len(catalogue)}"

    resp = await _patch(client, creds["token"], catalogue[:30])
    assert resp.status_code == 200, resp.text
    assert sorted(item["slug"] for item in resp.json()["interests"]) == sorted(catalogue[:30])

    resp = await _patch(client, creds["token"], catalogue[:31])
    assert resp.status_code == 422, resp.text
    assert "30" in resp.json()["error"]["message"], resp.json()
    assert await _stored(client, session, creds["user_id"]) == sorted(catalogue[:30]), (
        "the refused answer past the ceiling must not cut the set it already stored"
    )


async def test_an_answer_of_nothing_still_clears_the_set(client: AsyncClient, session) -> None:
    """An empty list is an answer, not a fault: it is how the screen removes every interest."""
    creds = await _onboarded(client, "s65_empty@befos.app", _KNOWN[:3])

    resp = await _patch(client, creds["token"], [])

    assert resp.status_code == 200, resp.text
    assert resp.json()["interests"] == []
    assert await _stored(client, session, creds["user_id"]) == []


async def test_a_name_that_differs_only_by_case_or_spaces_is_still_accepted(
    client: AsyncClient
) -> None:
    """Cleaning runs before checking, so «HIKING» is the same name the catalogue carries."""
    creds = await _onboarded(client, "s65_case@befos.app", _KNOWN[:3])

    resp = await _patch(client, creds["token"], ["  HIKING  ", _KNOWN[1], _KNOWN[1]])

    assert resp.status_code == 200, resp.text
    assert sorted(item["slug"] for item in resp.json()["interests"]) == sorted([_KNOWN[0], _KNOWN[1]])


async def test_a_name_of_only_spaces_is_refused_not_read_as_an_empty_answer(
    client: AsyncClient, session
) -> None:
    """``["   "]`` used to clear the set. It names nothing, so it cannot answer nothing."""
    creds = await _onboarded(client, "s65_blank@befos.app", _KNOWN[:3])

    resp = await _patch(client, creds["token"], ["   "])

    assert resp.status_code == 422, resp.text
    assert await _stored(client, session, creds["user_id"]) == sorted(_KNOWN[:3])


async def test_onboarding_refuses_the_same_name_the_edit_refuses(client: AsyncClient, session) -> None:
    """One rule for both writes; the second route used to answer three of five names in silence."""
    creds = await register_and_auth(client, "s65_onboard@befos.app")

    resp = await client.post(
        "/api/v1/users/me/onboarding",
        json={
            "name": "Стадия шесть пять", "birth_date": "1996-04-12", "city": "Самара",
            "gender": "male", "about": "Отказ на обоих маршрутах", "dating_goal": "relationship",
            "interests": [_KNOWN[0], _KNOWN[1], _KNOWN[2], *_UNKNOWN],
            "lifestyle": {"smoking": "never", "alcohol": "rarely", "sport": "often"},
            "age_min": 20, "age_max": 45, "gender_preference": ["female"],
        },
        headers=auth_headers(creds["token"]),
    )

    assert resp.status_code == 422, resp.text
    assert _UNKNOWN[0] in resp.json()["error"]["message"]
    assert await _stored(client, session, creds["user_id"]) == []
