"""A profile write named a gender preference the server does not carry, and the answer kept the secret.

Measured on the live stand before this stage (throwaway accounts, ``POST /users/me/onboarding`` and
``PATCH /users/me`` against the running container, snapshots ``s66_probe_silence.txt`` and
``s66_probe_deck.txt``): a body naming ``["male", "third_gender"]`` returned ``200`` and stored one
value, with no ``error`` field and no word about the name it dropped. The same body read back as
``["male"]``, so the answer was true about the row and false about the answer. The costly variant is
``["Male"]`` — a capital the four-value set does not carry: it stored the empty list, and because
``social_repo._preference_conditions`` only hangs ``Profile.gender.in_(...)`` on a non-empty
preference, removing the value removed the filter. A viewer who had named men got a deck of 94
cards where the same stand serves 47 for ``["male"]``, and the profile read back nothing at all.

Two silences share one missing check: the write turned the named list into the subset the server
knows and stored that subset, never comparing the two. The checks below pin that a name the server
does not know is refused rather than dropped, that a past-the-ceiling answer is refused rather than
cut, that case and spaces are cleaned before anything is compared — and that a refused write leaves
the stored preference, and the rest of the same body, exactly as it was.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import event

from app.core.database import engine
from app.repositories.user_repo import UserRepository

from .conftest import auth_headers, complete_onboarding, register_and_auth

# The whole set the server carries. The refusal is about names outside it, so the accepted half of
# every check below has to use these, not invented ones.
_KNOWN = ["male", "female", "nonbinary", "other"]
_UNKNOWN = ["third_gender", "genderqueer"]


async def _stored(client: AsyncClient, session, user_id: str) -> list[str]:
    # Rollback, not a cached read: the write landed on the request's session, and this session's
    # identity map would otherwise answer from the row it loaded before that write.
    await session.rollback()
    profile = await UserRepository(session).get_profile(uuid.UUID(user_id))
    return list(profile.gender_preference)


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


def _patch(client: AsyncClient, token: str, genders: list[str], **extra):
    return client.patch("/api/v1/users/me", json={"gender_preference": genders, **extra},
                        headers=auth_headers(token))


async def _baseline(client: AsyncClient, email: str, genders: list[str]) -> dict:
    """An onboarding through the helper plus one accepted write, so the stored set is known."""
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], interests=["hiking", "cinema", "cooking"])
    resp = await _patch(client, creds["token"], genders)
    assert resp.status_code == 200, resp.text
    return creds


async def test_a_gender_the_server_does_not_know_is_refused(client: AsyncClient) -> None:
    """The answer used to be a shorter list; now it is a refusal that says which name."""
    creds = await _baseline(client, "s66_refuse@befos.app", _KNOWN[:2])

    resp, seen = await _statements(_patch(client, creds["token"], [_KNOWN[0], _UNKNOWN[0]]))

    assert resp.status_code == 422, resp.text
    body = resp.json()["error"]
    assert body["code"] == "validation_error", body
    assert _UNKNOWN[0] in body["message"], body
    assert _KNOWN[0] not in body["message"], "a name the server carries is not part of the fault"
    assert not any(s.startswith("update profiles") for s in seen), seen


async def test_the_refusal_names_every_unknown_gender(client: AsyncClient) -> None:
    """One refusal for both faults, so the caller does not have to guess the second."""
    creds = await _baseline(client, "s66_both@befos.app", _KNOWN[:2])

    resp = await _patch(client, creds["token"], [_KNOWN[0], *_UNKNOWN])

    message = resp.json()["error"]["message"]
    for gender in _UNKNOWN:
        assert gender in message, message


async def test_a_refused_write_leaves_the_answered_set_stored(client: AsyncClient, session) -> None:
    """The case that cost the whole filter: one real name and two the server has never heard of.

    Before this stage the same body stored ``["male"]`` alone. The refusal has to arrive before the
    row is written, otherwise refusing a write would still move the preference it refused to change.
    """
    creds = await _baseline(client, "s66_keep@befos.app", _KNOWN[:2])

    resp = await _patch(client, creds["token"], [_KNOWN[2], *_UNKNOWN])

    assert resp.status_code == 422, resp.text
    assert await _stored(client, session, creds["user_id"]) == _KNOWN[:2]


async def test_a_refused_write_leaves_the_rest_of_the_body_alone(client: AsyncClient, session) -> None:
    """A refusal about genders must not half-apply the other fields of the same body."""
    creds = await _baseline(client, "s66_city@befos.app", _KNOWN[:2])

    resp = await _patch(client, creds["token"], _UNKNOWN, city="Омск")

    assert resp.status_code == 422, resp.text
    assert await _stored(client, session, creds["user_id"]) == _KNOWN[:2]
    me = await client.get("/api/v1/users/me", headers=auth_headers(creds["token"]))
    assert me.json()["city"] != "Омск", me.json()["city"]


async def test_the_four_genders_are_kept_and_the_fifth_is_refused(
    client: AsyncClient, session
) -> None:
    """The ceiling is the size of the set the names are checked against, so it cannot drift.

    It runs before the names are compared: a huge answer is then refused by a sentence that
    counts it, instead of a sentence that has to echo it back.
    """
    creds = await _baseline(client, "s66_cap@befos.app", _KNOWN[:1])

    resp = await _patch(client, creds["token"], _KNOWN)
    assert resp.status_code == 200, resp.text
    assert resp.json()["gender_preference"] == _KNOWN

    resp = await _patch(client, creds["token"], [*_KNOWN, _UNKNOWN[0]])
    assert resp.status_code == 422, resp.text
    assert str(len(_KNOWN)) in resp.json()["error"]["message"], resp.json()
    assert await _stored(client, session, creds["user_id"]) == _KNOWN, (
        "the refused answer past the ceiling must not cut the set it already stored"
    )


async def test_an_answer_of_nothing_still_clears_the_preference(client: AsyncClient, session) -> None:
    """An empty list is an answer, not a fault: it is how the screen removes every chip here."""
    creds = await _baseline(client, "s66_empty@befos.app", _KNOWN[:2])

    resp = await _patch(client, creds["token"], [])

    assert resp.status_code == 200, resp.text
    assert resp.json()["gender_preference"] == []
    assert await _stored(client, session, creds["user_id"]) == []


async def test_a_gender_that_differs_only_by_case_or_spaces_is_still_accepted(
    client: AsyncClient, session
) -> None:
    """``[" Male "]`` used to store nothing and widen the deck; cleaning runs before comparing."""
    creds = await _baseline(client, "s66_case@befos.app", _KNOWN[:2])

    resp = await _patch(client, creds["token"], ["  Male  ", _KNOWN[1], _KNOWN[1]])

    assert resp.status_code == 200, resp.text
    assert resp.json()["gender_preference"] == [_KNOWN[0], _KNOWN[1]]
    assert await _stored(client, session, creds["user_id"]) == [_KNOWN[0], _KNOWN[1]]


async def test_a_value_of_only_spaces_is_refused_not_read_as_an_empty_answer(
    client: AsyncClient, session
) -> None:
    """``["   "]`` used to clear the preference. It names nothing, so it cannot answer nothing."""
    creds = await _baseline(client, "s66_blank@befos.app", _KNOWN[:2])

    resp = await _patch(client, creds["token"], ["   "])

    assert resp.status_code == 422, resp.text
    assert await _stored(client, session, creds["user_id"]) == _KNOWN[:2]


async def test_onboarding_refuses_the_same_gender_the_edit_refuses(client: AsyncClient, session) -> None:
    """One rule for both writes; the second route used to store one of two names in silence."""
    creds = await register_and_auth(client, "s66_onboard@befos.app")

    resp = await client.post(
        "/api/v1/users/me/onboarding",
        json={
            "name": "Стадия шесть шесть", "birth_date": "1996-04-12", "city": "Самара",
            "gender": "male", "about": "Отказ на обоих маршрутах", "dating_goal": "relationship",
            "interests": ["hiking", "cinema", "cooking"],
            "lifestyle": {"smoking": "never", "alcohol": "rarely", "sport": "often"},
            "age_min": 20, "age_max": 45,
            "gender_preference": [_KNOWN[1], _UNKNOWN[0]],
        },
        headers=auth_headers(creds["token"]),
    )

    assert resp.status_code == 422, resp.text
    assert _UNKNOWN[0] in resp.json()["error"]["message"]
    assert await _stored(client, session, creds["user_id"]) == []
