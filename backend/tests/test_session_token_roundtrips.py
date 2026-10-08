"""The session routes stop raising the token row before writing it.

``POST /api/v1/auth/refresh`` and ``POST /api/v1/auth/logout`` both begin by reading the stored
``refresh_tokens`` row by its hash. ``before_cursor_execute`` counted four statements for the
rotation and two for the logout, and in both cases one of them was that read. It decided nothing
that the following write does not decide itself: the rotation's ``consume`` is an
``UPDATE … WHERE revoked is false`` whose row count already says whether the token was there and
still live, and logout answers 204 whatever the row looked like. So every session call paid a
round trip up front to ask permission for a write that asks nothing.

Written as one guarded UPDATE, the logout costs a single statement, and the rotation loses the
read that opened the window the reuse race had to be tested around.

What must not move is the answer: the presented token dies, the caller's other sessions survive,
a token already redeemed by rotation is refused the same way, and a deactivated account is still
refused before anything is minted.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable
from typing import Callable

from httpx import AsyncClient
from sqlalchemy import event, func, select, update

from app.core.database import engine
from app.core.security import create_token, generate_token_hash
from app.models import RefreshToken, User

from .conftest import auth_headers, register_and_auth


def _listener(seen: list[str]) -> Callable[..., None]:
    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    return _record


async def _counted(client: AsyncClient, awaitable: Awaitable) -> tuple[object, list[str]]:
    seen: list[str] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        resp = await awaitable
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    return resp, seen


def _token_reads(seen: list[str]) -> list[str]:
    """Statements that raise the stored token row before deciding anything about it."""
    return [s for s in seen if s.startswith("select") and "from refresh_tokens" in s]


def _token_writes(seen: list[str]) -> list[str]:
    return [s for s in seen if "refresh_tokens" in s and not s.startswith("select")]


async def test_logout_writes_the_stored_token_in_one_statement(client: AsyncClient) -> None:
    account = await register_and_auth(client, "s34_logout_one@befos.app")

    resp, seen = await _counted(
        client,
        client.post("/api/v1/auth/logout", json={"refresh_token": account["refresh"]}),
    )
    assert resp.status_code == 204, resp.text

    reads = _token_reads(seen)
    assert not reads, (
        f"logout raised the token row in {len(reads)} statement(s) to decide a write that the "
        "guarded UPDATE decides itself"
    )
    writes = _token_writes(seen)
    assert len(writes) == 1, f"logout touched refresh_tokens in {len(writes)} statements: {writes}"
    assert writes[0].startswith("update refresh_tokens"), writes[0]
    assert len(seen) == 1, f"{len(seen)} trips to revoke one session token"


async def test_the_rotation_writes_the_stored_token_without_reading_it_first(
    client: AsyncClient,
) -> None:
    account = await register_and_auth(client, "s34_refresh_one@befos.app")

    resp, seen = await _counted(
        client, client.post("/api/v1/auth/refresh", json={"refresh_token": account["refresh"]})
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["refresh_token"] != account["refresh"], "rotation handed back the same token"

    reads = _token_reads(seen)
    assert not reads, (
        f"the rotation raised the token row in {len(reads)} statement(s) before the UPDATE that "
        "already reports whether the token was there and live"
    )
    writes = _token_writes(seen)
    assert len(writes) == 2, f"rotation touched refresh_tokens in {len(writes)} statements: {writes}"
    assert writes[0].startswith("update refresh_tokens"), writes[0]
    assert writes[1].startswith("insert into refresh_tokens"), writes[1]
    assert len(seen) == 3, f"{len(seen)} trips to rotate one session"


async def test_the_logged_out_token_is_dead_and_the_other_sessions_stay_alive(
    client: AsyncClient,
) -> None:
    """One presented token dies; the same person's second device is not asked to leave."""
    account = await register_and_auth(client, "s34_sessions@befos.app")
    second = await client.post(
        "/api/v1/auth/login", json={"email": account["email"], "password": "Test12345"}
    )
    assert second.status_code == 200, second.text
    other_session = second.json()["tokens"]["refresh_token"]

    out = await client.post("/api/v1/auth/logout", json={"refresh_token": account["refresh"]})
    assert out.status_code == 204, out.text

    reused = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": account["refresh"]}
    )
    assert reused.status_code == 401, reused.text
    assert reused.json()["error"]["message"] == "Refresh token has been revoked.", reused.text

    alive = await client.post("/api/v1/auth/refresh", json={"refresh_token": other_session})
    assert alive.status_code == 200, alive.text

    # A second logout of the token that is already dead still answers 204 and writes nothing new.
    again = await client.post("/api/v1/auth/logout", json={"refresh_token": account["refresh"]})
    assert again.status_code == 204, again.text


async def test_a_deactivated_account_is_still_refused_before_anything_is_minted(
    client: AsyncClient, session
) -> None:
    account = await register_and_auth(client, "s34_deactivated@befos.app")
    minted = (
        await session.execute(
            select(func.count(RefreshToken.id)).where(
                RefreshToken.user_id == account["user_id"]
            )
        )
    ).scalar_one()
    await session.execute(
        update(User).where(User.id == account["user_id"]).values(is_active=False, is_deleted=True)
    )
    await session.commit()

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": account["refresh"]})
    assert resp.status_code == 401, resp.text
    assert resp.json()["error"]["message"] == "User no longer active.", resp.text

    after = (
        await session.execute(
            select(func.count(RefreshToken.id)).where(
                RefreshToken.user_id == account["user_id"]
            )
        )
    ).scalar_one()
    assert after == minted, (
        f"the refused rotation minted a session: {after} rows where {minted} were expected"
    )


async def test_a_signed_token_whose_row_is_gone_is_refused_the_same_way(
    client: AsyncClient, session
) -> None:
    """A token the database has never seen still answers the same one thing."""
    account = await register_and_auth(client, "s34_missing_row@befos.app")
    forged, _ = create_token(account["user_id"], "refresh")
    await session.execute(
        RefreshToken.__table__.delete().where(RefreshToken.user_id == account["user_id"])
    )
    await session.commit()

    resp, seen = await _counted(
        client, client.post("/api/v1/auth/refresh", json={"refresh_token": forged})
    )
    assert resp.status_code == 401, resp.text
    assert resp.json()["error"]["message"] == "Refresh token has been revoked.", resp.text
    assert not _token_reads(seen), "the refusal still raised the row that is not there"


async def test_the_redeemed_token_is_refused_by_the_write_that_found_nothing(
    client: AsyncClient,
) -> None:
    """Sequential reuse: the UPDATE matches no row, and that is the whole answer."""
    account = await register_and_auth(client, "s34_reuse@befos.app")
    stolen = account["refresh"]

    first = await client.post("/api/v1/auth/refresh", json={"refresh_token": stolen})
    assert first.status_code == 200, first.text

    second, seen = await _counted(
        client, client.post("/api/v1/auth/refresh", json={"refresh_token": stolen})
    )
    assert second.status_code == 401, second.text
    assert second.json()["error"]["message"] == "Refresh token has been revoked.", second.text
    assert not _token_reads(seen), "the refusal still raised the token row before writing it"


async def test_the_guard_is_the_owner_of_the_row_and_not_only_its_hash(
    client: AsyncClient, session
) -> None:
    """The owner predicate the read used to apply in Python has to live in the UPDATE instead.

    A row whose `user_id` disagrees with the subject of the token it hashes is only reachable by
    writing the table directly — no route mints one — but it is the state that proves the logout
    revokes the caller's own session and nobody else's.
    """
    owner = await register_and_auth(client, "s34_owner@befos.app")
    stranger = await register_and_auth(client, "s34_stranger@befos.app")

    stored = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == generate_token_hash(owner["refresh"]))
        )
    ).scalar_one()
    assert stored.user_id == uuid.UUID(owner["user_id"]), (
        "the minted row does not belong to its caller"
    )
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.id == stored.id)
        .values(user_id=stranger["user_id"])
    )
    await session.commit()

    out = await client.post("/api/v1/auth/logout", json={"refresh_token": owner["refresh"]})
    assert out.status_code == 204, out.text

    row = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == generate_token_hash(owner["refresh"]))
        )
    ).scalar_one()
    assert not row.revoked, "the logout revoked a row that belongs to somebody else"
