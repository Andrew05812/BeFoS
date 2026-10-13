"""The stand prices half of a sign-in, and it prices no session route at all.

`docs/SCALE_PLAN.md` §«Задержки горячих путей» publishes `login` as `677.8 / 690.9 / 1` — медиана,
максимум и одно обращение за вызов. The single statement is the symptom. The mounted
`POST /api/v1/auth/login` is two steps: `AuthService.authenticate` reads the account and checks the
password, then `AuthService.issue_tokens` hashes a token, INSERTs a row into `refresh_tokens` and
commits. The harness wrapper calls the first step only, so the row in the published table is the
price of a password check, not the price of signing in — and the sign-in a user actually makes is
the one that leaves a session behind. `docs/SCALE_PLAN.md` names the same gap for the other half of
the flow: «Маршрутов сессии (`POST /auth/refresh`, `POST /auth/logout`) в этом списке тоже нет, и
стадия 34 их здесь не переснимала», because `ops/scale_probe.py` never carried those paths and the
stand's `refresh_tokens` table stayed empty.

Eight checks, in the order the risk sits:

* the route really writes a session — the premise, stated as a measurement rather than as a reading
  of the source;
* the harness's `login` pays every write the route pays, which is the rule stage 76 wrote for
  `universe_map` and which `login` breaks;
* the stand carries paths for the two session routes;
* the refresh path redeems a live token and carries its own rotation, because a call that ends in a
  401 writes nothing and would publish a refusal as the price of a session;
* the logout path revokes a session that exists, because `POST /auth/logout` answers 204 even when
  the token decodes to nothing, and measuring that branch would price an empty request;
* the published table carries the rows and the section no longer says the session routes are absent;
* the paragraph that lists the harness's paths names every path it carries, which is how the
  §«Как повторить замер» list went stale behind stages 76 and 77 without any check noticing;
* the published table carries a row for every path and no row for a path the harness dropped — the
  same rule for the other half of the document, so a sixteenth path cannot be measured and left out.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models import RefreshToken

from .conftest import register_and_auth

_PROBE_PATH = pathlib.Path(__file__).resolve().parents[1] / "ops" / "scale_probe.py"
_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCALE_DOC = _ROOT / "docs" / "SCALE_PLAN.md"


def _probe():
    """Load the stand as a module: it is a script, so it is not on the import path."""
    spec = importlib.util.spec_from_file_location("scale_probe", _PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _record(call) -> list[str]:
    """Statements one call sends, in order, through the engine the app itself uses."""
    seen: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        seen.append(" ".join(statement.lower().split()))

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    try:
        await call()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)
    return seen


def _writes(statements: list[str]) -> set[tuple[str, str]]:
    """The (verb, table) pairs a call sends, for writes only.

    Reads are compared loosely elsewhere; the writes are what a session route decides to do, and a
    harness that skips one publishes a number for a call the product never makes.
    """
    pairs: set[tuple[str, str]] = set()
    for statement in statements:
        verb = statement.split(" ", 1)[0]
        if verb not in ("insert", "update", "delete"):
            continue
        table = re.sub(r"^(?:insert into|update|delete from)\s*", "", statement).split()[0]
        pairs.add((verb, table))
    return pairs


async def _live_token_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(RefreshToken).where(RefreshToken.user_id == user_id)
        )
        or 0
    )


async def test_signing_in_on_the_wire_mints_the_session_the_harness_never_pays(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The premise: `POST /auth/login` writes a row, so a row that prices one statement is not it."""
    email = "s77_wire@befos.app"
    registered = await register_and_auth(client, email)
    before = await _live_token_count(session, uuid.UUID(registered["user_id"]))

    statements = await _record(
        lambda: client.post("/api/v1/auth/login", json={"email": email, "password": "Test12345"})
    )
    after = await _live_token_count(session, uuid.UUID(registered["user_id"]))

    assert ("insert", "refresh_tokens") in _writes(statements), (
        "the mounted login route no longer writes a session, so this stage's premise is stale and "
        f"the table's `login` row would be honest again. Writes it sent: {_writes(statements)}"
    )
    assert after == before + 1, (
        f"a sign-in left {after - before} token rows, expected exactly one — the harness has to "
        "price the write the route actually makes"
    )


async def test_the_stands_login_pays_every_write_the_login_route_pays(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The rule stage 76 wrote for `universe_map`, aimed at the row that breaks it."""
    probe = _probe()
    email = "s77_stand@befos.app"
    await register_and_auth(client, email, password=probe.PASSWORD)

    route_writes = _writes(
        await _record(
            lambda: client.post(
                "/api/v1/auth/login", json={"email": email, "password": probe.PASSWORD}
            )
        )
    )
    ctx = {"viewer_email": email}
    wrapper_writes = _writes(await _record(
        lambda: probe._build_paths()["login"](session, ctx)
    ))

    missing = route_writes - wrapper_writes
    assert not missing, (
        "the published `login` row prices a call the route does not make: the wrapper skips "
        f"{sorted(missing)} while the mounted route sends "
        f"{sorted(route_writes)}. The table cell for `login` therefore reports the price of checking "
        "a password, and a reader who wants the price of signing in gets a smaller number than the "
        "product charges"
    )


def test_the_stand_carries_paths_for_the_session_routes() -> None:
    paths = _probe()._build_paths()
    for name in ("session_refresh", "session_logout"):
        assert name in paths, (
            f"`{name}` is not in the harness, so `docs/SCALE_PLAN.md` is right to say the session "
            "routes are unpriced: a client pays a refresh the moment its access token dies, and the "
            "table that lists the hot paths has no row for it"
        )


async def test_the_refresh_path_redeems_a_live_token_and_carries_the_rotation(
    client: AsyncClient, session: AsyncSession
) -> None:
    from app.services.auth_service import AuthService

    probe = _probe()
    email = "s77_rotate@befos.app"
    await register_and_auth(client, email, password=probe.PASSWORD)
    ctx = {"viewer_email": email}
    await probe._build_setups()["session_refresh"](session, ctx)

    presented = ctx.get("refresh_token")
    assert presented, "the refresh path has no live token to redeem, so nothing in the window is a rotation"

    statements = await _record(lambda: probe._build_paths()["session_refresh"](session, ctx))
    writes = _writes(statements)

    assert ctx.get("refresh_token") != presented, (
        "the measured call did not carry its own rotation forward: refresh redeems the token it is "
        "given, so a wrapper that keeps handing out the same string measures one rotation and then "
        "measures a refusal four times"
    )
    assert ("insert", "refresh_tokens") in writes and ("update", "refresh_tokens") in writes, (
        f"a rotation should redeem and mint, the measured window wrote {sorted(writes)}"
    )

    with pytest.raises(Exception) as refusal:
        await AuthService(session).refresh(presented)
    assert "revoked" in str(refusal.value).lower(), (
        "the token the measured call presented is still live afterwards, so the window did not "
        "redeem it"
    )


async def test_the_logout_path_revokes_a_session_that_exists(
    client: AsyncClient, session: AsyncSession
) -> None:
    probe = _probe()
    email = "s77_logout@befos.app"
    account = await register_and_auth(client, email, password=probe.PASSWORD)
    ctx = {"viewer_email": email}
    await probe._build_setups()["session_logout"](session, ctx)

    queued = list(ctx.get("logout_tokens") or [])
    assert queued, "the logout path has no live session to end, so the window would price nothing"

    statements = await _record(lambda: probe._build_paths()["session_logout"](session, ctx))
    writes = _writes(statements)
    assert ("update", "refresh_tokens") in writes, (
        "the measured logout sent no revocation. `POST /auth/logout` answers 204 whether or not the "
        "token was there — its handler swallows the failure — so a wrapper that ends a session that "
        f"never existed publishes the price of an empty request. Writes: {sorted(writes)}"
    )

    row = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == await _hash_of(session, queued[0]))
    )
    assert row is not None and row.revoked, "the queued session the path was given is still live"


async def _hash_of(session: AsyncSession, token: str) -> str:
    from app.core.security import generate_token_hash

    return generate_token_hash(token)


def test_the_published_table_carries_rows_for_the_session_paths() -> None:
    doc = _SCALE_DOC.read_text(encoding="utf-8")
    parts = doc.split("## Задержки горячих путей", 1)
    assert len(parts) == 2, "docs/SCALE_PLAN.md no longer carries the hot-path table"
    section = parts[1].split("\n### ", 1)[0]

    for name in ("session_refresh", "session_logout"):
        row = re.search(rf"^\|\s*`{name}`\s*\|(.+)$", section, re.MULTILINE)
        assert row, (
            f"the harness now prices `{name}`, but the published table has no row for it — the "
            "document is the half of the rule that turns a run into a claim"
        )
        cells = [cell.strip() for cell in row.group(1).split("|") if cell.strip()]
        assert len(cells) == 3, f"a latency row carries one cell per scale, this one carries {cells}"
        for cell in cells:
            assert re.fullmatch(r"\d+(?:[.,]\d+)? / \d+(?:[.,]\d+)? / \d+(?:\.\d+)?", cell), (
                f"`{cell}` is not the published shape медиана / максимум / число запросов"
            )

    assert "в этом списке тоже нет" not in doc, (
        "the document still says the session routes are absent from the measured list while the table "
        "above carries rows for them — the sentence sits in the bullet list under the table, so the "
        "check reads the whole file rather than only the section"
    )


def _hot_path_rows() -> list[str]:
    doc = _SCALE_DOC.read_text(encoding="utf-8")
    parts = doc.split("## Задержки горячих путей", 1)
    assert len(parts) == 2, "docs/SCALE_PLAN.md no longer carries the hot-path table"
    section = parts[1].split("\n### ", 1)[0]
    return re.findall(r"^\|\s*`([a-z_]+)`\s*\|", section, re.MULTILINE)


def test_the_described_path_list_names_every_path_the_harness_carries() -> None:
    """§«Как повторить замер» lists the paths a reader can ask the stand about.

    The list went stale twice: stage 76 put `universe_map` into the harness and stage 77 put the two
    session paths there, while the paragraph still enumerated thirteen. A reader who trusts that
    paragraph over the table concludes the stand measures nothing of the pair map or of a session.
    """
    doc = _SCALE_DOC.read_text(encoding="utf-8")
    parts = doc.split("что стоят за маршрутами:", 1)
    assert len(parts) == 2, (
        "the sentence that enumerates the harness's paths is gone from §«Как повторить замер», so "
        "there is nothing left for this check to compare against the harness"
    )
    described = re.findall(r"`([a-z_]+)`", parts[1].split(".", 1)[0])
    carried = list(_probe()._build_paths())

    missing = [name for name in carried if name not in described]
    extra = [name for name in described if name not in carried]
    assert not missing and not extra, (
        f"the paragraph names {described} while the harness carries {carried} — "
        f"undescribed: {missing}, described but absent: {extra}"
    )


def test_the_published_table_carries_one_row_per_harness_path_in_harness_order() -> None:
    """The table claims its row order is the harness's dict order; the claim is the rule."""
    carried = list(_probe()._build_paths())
    rows = _hot_path_rows()

    assert rows == carried, (
        f"the published table rows {rows} do not match the harness paths {carried} in order — the "
        "section states «Порядок строк — порядок словаря путей harness'а», and a path measured but "
        "not published is a claim the document never made"
    )
