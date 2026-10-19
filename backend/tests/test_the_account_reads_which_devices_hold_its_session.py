"""The account reads which devices hold its own session, and ends one of them by name.

`POST /auth/register`, `/auth/login` and `/auth/refresh` each write a row into `refresh_tokens` and
store with it the `User-Agent` the request arrived under, and `docs/OPERATIONS.md` §14 has always
known how to read that table — with `psql`, by the operator. Until stage 110 no account could: the
only door that ended a session it was not standing on was `change-password`, which ends every session
the word opens, including the one the person is reading the answer with. So a device signed in at a
friend's house or in a browser at work was invisible, and the remedy for one was to lose all of them.

This file pins the surface that closes that gap — `GET /auth/sessions`,
`POST /auth/sessions/{session_id}/revoke`, `POST /auth/sessions/revoke-all` — and what it promises:

* the list is the account's own live rows and nothing else: a row the caller ended, a row past its
  expiry, and a row belonging to somebody else are outside it, and none of them can be named by the
  write either;
* the list carries what a device called itself and the two instants that say when it arrived and when
  it stops working, and no material that opens it — neither the refresh token nor the hash stored
  instead of it;
* exactly one row can say `current`, and it is the row the bearer's own access token names; a token
  that names no row marks nothing rather than guessing;
* ending one session leaves the others redeemable, and ending all of them ends the caller's own too.

The `sid` claim that makes `current` possible is written by `AuthService.issue_tokens`, so these tests
hold the pair to that claim too: the row the answer marks is the row the token points at.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.core.security import create_token, generate_token_hash
from app.models import RefreshToken
from app.services.auth_service import AuthService
from .conftest import auth_headers, register_and_auth

SESSIONS = "/api/v1/auth/sessions"
PASSWORD = "Test12345"
PHONE = "BeFoS/1.0 (Pixel 7; Android 14)"
BROWSER = "Mozilla/5.0 (X11; Linux x86_64) Firefox/129.0"
FIELDS = {"id", "device", "signed_in_at", "expires_at", "current"}


async def _registered(client: AsyncClient, email: str, device: str = PHONE) -> dict:
    """A pair minted by a named device, exactly as the product mints one.

    The `User-Agent` is the whole point: the list calls a session by the string it arrived with, so a
    helper that signed in without one would be testing the fallback instead of the feature.
    """
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "password_confirm": PASSWORD},
        headers={"User-Agent": device},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return {
        "token": data["tokens"]["access_token"],
        "refresh": data["tokens"]["refresh_token"],
        "user_id": data["user"]["id"],
        "email": email,
        "device": device,
    }


async def _another_device(client: AsyncClient, account: dict, device: str) -> dict:
    """The same word from a second device: one more live row, one more pair to answer with."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": account["email"], "password": PASSWORD},
        headers={"User-Agent": device},
    )
    assert response.status_code == 200, response.text
    tokens = response.json()["tokens"]
    return {"token": tokens["access_token"], "refresh": tokens["refresh_token"], "device": device}


async def _page(client: AsyncClient, token: str) -> dict:
    response = await client.get(SESSIONS, headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()


async def _devices(client: AsyncClient, token: str) -> list[dict]:
    return (await _page(client, token))["sessions"]


async def _end(client: AsyncClient, token: str, session_id: str) -> Response:
    return await client.post(f"{SESSIONS}/{session_id}/revoke", headers=auth_headers(token))


async def _end_every(client: AsyncClient, token: str) -> Response:
    return await client.post(f"{SESSIONS}/revoke-all", headers=auth_headers(token))


async def _rows(user_id: str) -> list[RefreshToken]:
    async with AsyncSessionLocal() as session:
        return list(
            (
                await session.execute(
                    select(RefreshToken)
                    .where(RefreshToken.user_id == uuid.UUID(user_id))
                    .order_by(RefreshToken.created_at.asc(), RefreshToken.id.asc())
                )
            ).scalars().all()
        )


async def _row(user_id: str, session_id: str) -> RefreshToken:
    return next(row for row in await _rows(user_id) if str(row.id) == session_id)


async def _shift_oldest(user_id: str, device: str) -> None:
    """Put one row's arrival a quarter-hour back, so ordering is checked against the real column.

    Two sign-ins in the same test land inside milliseconds of each other, and the tie is broken by the
    id — which is exactly what a `(created_at, id)` order is for, but not what a person reads as
    «сначала новое». Moving a row's own `created_at` makes the answer depend on the timestamp.
    """
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(RefreshToken)
                .where(RefreshToken.user_id == uuid.UUID(user_id))
                .order_by(RefreshToken.created_at.asc())
            )
        ).scalars().all()
        target = next(row for row in rows if row.user_agent == device)
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.id == target.id)
            .values(created_at=target.created_at - timedelta(minutes=15))
        )
        await session.commit()


async def _expire(user_id: str, session_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.id == uuid.UUID(session_id))
            .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        )
        await session.commit()


async def _add_live_row(user_id: str, device: str) -> str:
    """A live session written straight into the table.

    Reaching the bound any other way would cost one bcrypt hash per row — around 450 ms each, so fifty
    sign-ins is half a minute of the suite spent proving a `LIMIT`. The row this writes is the row a
    client leaves behind; only the hash is invented, and nothing reads it back.
    """
    async with AsyncSessionLocal() as session:
        row = RefreshToken(
            user_id=uuid.UUID(user_id),
            token_hash=uuid.uuid4().hex,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            user_agent=device,
        )
        session.add(row)
        await session.commit()
        return str(row.id)


async def test_the_account_reads_the_sessions_two_devices_opened(client: AsyncClient) -> None:
    """Two sign-ins are two rows, and their owner can now see both of them named."""
    phone = await _registered(client, "two-devices@befos.app")
    browser = await _another_device(client, phone, BROWSER)

    rows = await _devices(client, phone["token"])
    assert len(rows) == 2, rows
    assert {row["device"] for row in rows} == {PHONE, BROWSER}
    for row in rows:
        assert set(row) == FIELDS, row
        assert datetime.fromisoformat(row["signed_in_at"]) <= datetime.now(timezone.utc), row
        assert datetime.fromisoformat(row["expires_at"]) > datetime.now(timezone.utc), row

    from_browser = await _devices(client, browser["token"])
    assert {row["device"] for row in from_browser} == {PHONE, BROWSER}, from_browser


async def test_a_device_that_arrived_without_a_name_is_shown_as_having_none(
    client: AsyncClient,
) -> None:
    """An empty header is a fact about the session, not a blank to invent a name for."""
    account = await _registered(client, "nameless@befos.app")
    await client.post(
        "/api/v1/auth/login",
        json={"email": "nameless@befos.app", "password": PASSWORD},
        headers={"User-Agent": ""},
    )

    rows = await _devices(client, account["token"])
    assert {row["device"] for row in rows} == {None, PHONE}, rows


async def test_the_newest_device_is_answered_first_and_each_row_once(client: AsyncClient) -> None:
    """The list is ordered by when the device arrived, and no row is handed out twice."""
    account = await _registered(client, "ordered@befos.app")
    await _another_device(client, account, BROWSER)
    await _shift_oldest(account["user_id"], PHONE)

    rows = await _devices(client, account["token"])
    assert [row["device"] for row in rows] == [BROWSER, PHONE], rows
    assert len({row["id"] for row in rows}) == len(rows), rows


async def test_exactly_one_row_names_the_device_the_reader_stands_on(client: AsyncClient) -> None:
    """The token says which row it opened, and the list believes the token and nothing else."""
    phone = await _registered(client, "which-one@befos.app")
    browser = await _another_device(client, phone, BROWSER)

    marked = [row for row in await _devices(client, phone["token"]) if row["current"]]
    assert len(marked) == 1, marked
    assert marked[0]["device"] == PHONE, marked
    assert (await _row(phone["user_id"], marked[0]["id"])).user_agent == PHONE

    from_browser = [row for row in await _devices(client, browser["token"]) if row["current"]]
    assert [row["device"] for row in from_browser] == [BROWSER], from_browser


async def test_a_token_that_names_no_session_marks_no_row(client: AsyncClient) -> None:
    """A pair signed before the claim existed gets a list without a badge, not a guess at one.

    `current` is the field a person uses to decide which row to leave alone, so the only honest answer
    for a token that does not say is to say nothing.
    """
    account = await _registered(client, "old-token@befos.app")
    stale, _ = create_token(uuid.UUID(account["user_id"]), "access")

    rows = await _devices(client, stale)
    assert [row["current"] for row in rows] == [False], rows


async def test_the_list_carries_nothing_that_opens_a_session(client: AsyncClient) -> None:
    """A device is described, never handed out.

    `token_hash` is the key the refresh route matches a presented token against, and a list of
    sessions that also carried it would be a table of lookup keys. The raw refresh token is the
    credential itself. Neither belongs in an answer that only has to say which phone signed in, so the
    check covers the value, its hash, and the name of the column.
    """
    account = await _registered(client, "leak-check@befos.app")
    browser = await _another_device(client, account, BROWSER)

    answer = await _page(client, account["token"])
    text = str(answer)
    assert "token_hash" not in text, answer
    for secret in (account["refresh"], browser["refresh"]):
        assert secret not in text, "the answer carries the token itself"
        assert generate_token_hash(secret) not in text, "the answer carries the stored hash"


async def test_ending_one_device_leaves_the_other_one_working(client: AsyncClient) -> None:
    """The write moves one row, and the session it names is the only one that stops.

    Refreshing is what a device does when its access token runs out, so a refused refresh is the
    proof the row is gone and an accepted one is the proof the other row is not.
    """
    phone = await _registered(client, "cut-one@befos.app")
    browser = await _another_device(client, phone, BROWSER)

    rows = await _devices(client, phone["token"])
    browser_row = next(row for row in rows if row["device"] == BROWSER)
    phone_row = next(row for row in rows if row["device"] == PHONE)

    ended = await _end(client, phone["token"], browser_row["id"])
    assert ended.status_code == 204, ended.text
    assert ended.text == ""

    assert (await _row(phone["user_id"], browser_row["id"])).revoked is True
    assert (await _row(phone["user_id"], phone_row["id"])).revoked is False
    assert [row["device"] for row in await _devices(client, phone["token"])] == [PHONE]

    renewed = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": browser["refresh"]},
        headers={"User-Agent": BROWSER},
    )
    assert renewed.status_code == 401, renewed.text

    still_live = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": phone["refresh"]},
        headers={"User-Agent": PHONE},
    )
    assert still_live.status_code == 200, still_live.text


async def test_a_session_that_is_already_gone_answers_as_an_absent_one(client: AsyncClient) -> None:
    """Ending the same device twice is one ending; the second request changes nothing.

    The row is not reopened, no `revoked_at` is rewritten, and the refusal does not distinguish a
    session this account ended from a session that never was — the id space is not an oracle.
    """
    account = await _registered(client, "twice@befos.app")
    row_id = (await _devices(client, account["token"]))[0]["id"]

    assert (await _end(client, account["token"], row_id)).status_code == 204
    decided_at = (await _row(account["user_id"], row_id)).revoked_at

    again = await _end(client, account["token"], row_id)
    assert again.status_code == 404, again.text
    assert again.json()["error"]["code"] == "not_found", again.text
    row = await _row(account["user_id"], row_id)
    assert row.revoked is True and row.revoked_at == decided_at


async def test_another_account_cannot_end_someone_elses_session(client: AsyncClient) -> None:
    """A real session id of a stranger is an absent id here, and stays live there."""
    owner = await _registered(client, "owner@befos.app")
    stranger = await register_and_auth(client, "stranger@befos.app")
    row_id = (await _devices(client, owner["token"]))[0]["id"]

    refused = await _end(client, stranger["token"], row_id)
    assert refused.status_code == 404, refused.text
    assert (await _row(owner["user_id"], row_id)).revoked is False
    assert [row["id"] for row in await _devices(client, owner["token"])] == [row_id]


async def test_a_session_past_its_own_expiry_is_neither_shown_nor_cuttable(client: AsyncClient) -> None:
    """A row whose token can no longer be redeemed is not a device to be afraid of.

    `refresh` rejects the token on its signature's expiry before this table is ever consulted, so
    showing the row would point a person at a session that cannot open anything — and letting the
    write end it would make the set of ids this route accepts wider than the set it describes.
    """
    account = await _registered(client, "expiring@befos.app")
    row_id = (await _devices(client, account["token"]))[0]["id"]
    await _expire(account["user_id"], row_id)

    assert await _devices(client, account["token"]) == []
    refused = await _end(client, account["token"], row_id)
    assert refused.status_code == 404, refused.text
    assert (await _row(account["user_id"], row_id)).revoked is False


async def test_ending_every_session_ends_the_one_the_caller_stands_on(
    client: AsyncClient,
) -> None:
    """The lost-phone door takes the whole account with it, and says nothing about a new pair.

    A body carrying tokens here would contradict the write it answers: `change-password` gives up the
    same way for the same reason.
    """
    phone = await _registered(client, "lost-phone@befos.app")
    browser = await _another_device(client, phone, BROWSER)

    ended = await _end_every(client, phone["token"])
    assert ended.status_code == 204, ended.text
    assert ended.text == ""

    assert await _devices(client, phone["token"]) == []
    for token in (phone["refresh"], browser["refresh"]):
        refused = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": token}, headers={"User-Agent": BROWSER}
        )
        assert refused.status_code == 401, refused.text
    for row in await _rows(phone["user_id"]):
        assert row.revoked is True, row


@pytest.mark.parametrize("word", ["change-password", "logout"])
async def test_the_door_that_ends_a_session_is_still_the_door_that_keeps_the_word(
    client: AsyncClient, word: str
) -> None:
    """Two existing routes, one of which the new list must not silently replace.

    `logout` ends the token it is handed and nothing else, `change-password` ends every session the
    word opens. The list is the read that tells a person which of the two they need — so both answers
    stay exactly as they were, one row and all rows, and the new surface borrows neither.
    """
    account = await _registered(client, f"kept-door-{word}@befos.app")
    other = await _another_device(client, account, BROWSER)

    if word == "logout":
        answer = await client.post(
            "/api/v1/auth/logout", json={"refresh_token": account["refresh"]}
        )
        assert answer.status_code == 204, answer.text
        assert [row["device"] for row in await _devices(client, other["token"])] == [BROWSER]
    else:
        answer = await client.post(
            f"/api/v1/auth/{word}",
            json={"old_password": PASSWORD, "new_password": "Fresh12345", "password_confirm": "Fresh12345"},
            headers=auth_headers(account["token"]),
        )
        assert answer.status_code == 204, answer.text
        assert await _devices(client, other["token"]) == []


async def test_the_list_stops_at_its_bound_and_says_so(client: AsyncClient) -> None:
    """A list that runs out admits it rather than looking complete.

    A client that refreshes its pair on every launch leaves one live row per launch until the rows
    expire thirty days later, and a screen showing the first fifty of a hundred and twelve with no
    word about the rest is a screen that hides devices.
    """
    account = await _registered(client, "crowd@befos.app")
    for index in range(AuthService.SESSIONS_SHOWN):
        await _add_live_row(account["user_id"], f"device-{index}")

    answer = await _page(client, account["token"])
    assert len(answer["sessions"]) == AuthService.SESSIONS_SHOWN, len(answer["sessions"])
    assert answer["has_more"] is True, answer
    assert len(await _rows(account["user_id"])) > AuthService.SESSIONS_SHOWN

    one_row = await _end(client, account["token"], answer["sessions"][0]["id"])
    assert one_row.status_code == 204, one_row.text
