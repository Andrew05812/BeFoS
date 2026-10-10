"""The pair list reads more columns than it answers with.

``GET /api/v1/matches`` builds nine fields per card — a name, an age, a city, a photo url, the
percent the pair stored, the newest line with its time, the unread counter and the date of the pair.
Until this stage the path produced them by materialising four ORM entities per card: a ``Match``
(6 columns), a ``Profile`` (16, among them the free-text ``about``, the ``lifestyle`` jsonb and the
two preference arrays), a ``Photo`` (7) and a ``Message`` (8, among them ``client_msg_id`` and
``updated_at``). Measured 2026-10-10 on a stand of 3 000 анкет with the viewer holding a thousand
pairs, two photos per partner and three messages per pair (`ops/_s49_probe.py`, `ops/_s49_pilot.py`):
PostgreSQL spent 20.4 ms of plan execution on the four reads while the call cost 235.8 ms, and the
same pass reading only the columns the card answers with cost 146.2 ms — interleaved repeats, −38.0 %,
answers identical field by field.

What must not move is the answer again: the age still comes from the birth date through the same
calendar the profile row computes with, the photo still follows the one display order, a partner
whose account was deleted still leaves the list, and the newest line with its counter still come
from one pass over ``messages``.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select, update

from app.models import Photo, User
from app.models.user import Profile

from .conftest import auth_headers, complete_onboarding, register_and_auth
from .test_chat_receipt_roundtrips import _counted


async def _reader_with_pair(client: AsyncClient, slug: str, *, messages: int = 2) -> tuple[dict, str, dict]:
    """A reader, one partner who sent ``messages`` lines, and the partner's account."""
    reader = await register_and_auth(client, f"{slug}_reader@befos.app")
    await complete_onboarding(client, reader["token"], name="Вера", gender="female")
    peer = await register_and_auth(client, f"{slug}_peer@befos.app")
    await complete_onboarding(client, peer["token"], name="Пётр", gender="male")
    await client.post(f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(reader["token"]))
    back = await client.post(
        f"/api/v1/users/{reader['user_id']}/like", headers=auth_headers(peer["token"])
    )
    assert back.status_code == 200, back.text
    match_id = back.json()["match_id"]
    for i in range(messages):
        sent = await client.post(
            f"/api/v1/matches/{match_id}/messages",
            headers=auth_headers(peer["token"]),
            json={"body": f"{slug} line {i}"},
        )
        assert sent.status_code == 201, sent.text
    return reader, match_id, peer


def _profile_statement(seen: list[str]) -> str:
    found = [s for s in seen if s.startswith("select") and "from profiles" in s]
    assert len(found) == 1, f"the pair list read profiles {len(found)} times: {found}"
    return found[0]


def _photo_statement(seen: list[str]) -> str:
    found = [s for s in seen if s.startswith("select") and "from photos" in s]
    assert len(found) == 1, f"the pair list read photos {len(found)} times: {found}"
    return found[0]


def _message_statement(seen: list[str]) -> str:
    found = [s for s in seen if s.startswith("select") and "from messages" in s]
    assert len(found) == 1, f"the pair list read messages {len(found)} times: {found}"
    return found[0]


async def test_the_profile_read_asks_for_the_columns_the_card_shows(
    client: AsyncClient,
) -> None:
    """The card carries a name, an age and a city — not the questionnaire the row also holds."""
    reader, _, _ = await _reader_with_pair(client, "s49_profile")
    _, seen = await _counted(
        client, client.get("/api/v1/matches", headers=auth_headers(reader["token"]))
    )
    statement = _profile_statement(seen)
    unused = [
        column
        for column in ("profiles.about", "profiles.lifestyle", "profiles.gender_preference",
                       "profiles.city_preference", "profiles.dating_goal", "profiles.is_hidden")
        if column in statement
    ]
    assert not unused, (
        f"the pair list materialised columns it never answers with: {unused}. The card carries a "
        "name, an age and a city, and the read builds one ORM object per pair out of the whole "
        "profile row — including the free text, the jsonb lifestyle and both preference arrays"
    )


async def test_the_photo_read_asks_for_the_url_alone(client: AsyncClient) -> None:
    """Only the url is answered; the ordering columns belong in ORDER BY, not in the projection."""
    reader, _, _ = await _reader_with_pair(client, "s49_photo")
    _, seen = await _counted(
        client, client.get("/api/v1/matches", headers=auth_headers(reader["token"]))
    )
    statement = _photo_statement(seen)
    projection = statement.split(" from photos ")[0]
    unused = [
        column
        for column in ("photos.id", "photos.is_primary", "photos.position", "photos.created_at",
                       "photos.updated_at")
        if column in projection
    ]
    assert not unused, (
        f"the pair list fetched photo columns it does not answer with: {unused} — the card carries "
        f"one url per partner, and the order stays in ORDER BY: {projection}"
    )


async def test_the_message_read_asks_for_the_line_and_the_counter(client: AsyncClient) -> None:
    """The newest line needs a body and a time; the client id and the row stamps belong to a chat."""
    reader, _, _ = await _reader_with_pair(client, "s49_message")
    _, seen = await _counted(
        client, client.get("/api/v1/matches", headers=auth_headers(reader["token"]))
    )
    statement = _message_statement(seen)
    projection = statement.split(" from messages ")[0]
    unused = [
        column
        for column in ("messages.client_msg_id", "messages.updated_at", "messages.is_deleted")
        if column in projection
    ]
    assert not unused, (
        f"the pair list fetched message columns it does not answer with: {unused} — the card shows "
        f"the newest body and a count, nothing else: {projection}"
    )


async def test_the_card_still_carries_the_name_the_age_the_city_and_the_photo(
    client: AsyncClient, session
) -> None:
    """A narrow read that answers differently is the defect this test exists to catch."""
    reader, match_id, peer = await _reader_with_pair(client, "s49_answer", messages=3)
    peer_id = uuid.UUID(peer["user_id"])

    # A birth date the calendar cannot round two ways, and a primary photo among two.
    profile = (
        await session.execute(select(Profile).where(Profile.user_id == peer_id))
    ).scalar_one()
    profile.birth_date = profile.birth_date.replace(year=1990)
    await session.flush()
    other = Photo(user_id=peer_id, url="/uploads/other.jpg", is_primary=False, position=0)
    chosen = Photo(user_id=peer_id, url="/uploads/chosen.jpg", is_primary=True, position=1)
    session.add_all([other, chosen])
    await session.commit()

    resp = await client.get("/api/v1/matches", headers=auth_headers(reader["token"]))
    assert resp.status_code == 200, resp.text
    card = next(row for row in resp.json()["matches"] if row["match_id"] == match_id)

    assert card["name"] == "Пётр", card
    assert card["city"] == profile.city, card
    assert card["age"] == profile.age, (
        f"the list answered age {card['age']} while the row computes {profile.age}"
    )
    assert card["photo_url"] == "/uploads/chosen.jpg", (
        f"the card picked {card['photo_url']} out of the partner's photos"
    )
    assert card["last_message"] == "s49_answer line 2", card
    assert card["unread"] == 3, card


async def test_a_partner_whose_account_was_deleted_still_leaves_the_list(
    client: AsyncClient, session
) -> None:
    """The visible rule lives in the profile read's join to ``users``; a narrow read must keep it."""
    reader, match_id, peer = await _reader_with_pair(client, "s49_deleted")
    await session.execute(
        update(User).where(User.id == uuid.UUID(peer["user_id"])).values(is_deleted=True)
    )
    await session.commit()

    resp = await client.get("/api/v1/matches", headers=auth_headers(reader["token"]))
    assert resp.status_code == 200, resp.text
    rows = resp.json()["matches"]
    assert all(row["match_id"] != match_id for row in rows), (
        f"a deleted partner is still answered: {[r['user_id'] for r in rows]}"
    )
