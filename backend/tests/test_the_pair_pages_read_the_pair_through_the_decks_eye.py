"""The pair screens read whoever the harness named, and the capture throws away every write.

Two defects, one measurement each. `docs/SCALE_PLAN.md` §«Задержки горячих путей» publishes
`match_detail` as `... / 5` and `compatibility` as `... / 3` statements per call. The mounted
`GET /matches/{match_id}` and `GET /matches/{match_id}/compatibility` are three-step routes: the
handler reads the `matches` row to prove the caller belongs to the pair, derives the partner from
that row — not from whatever person the harness picked first by email — and the compatibility
handler then reads `interests` to title the shared interests it prints. The harness wrappers skip
the membership read, ask about `ctx["peer_id"]` instead of the match's own partner, and never title
anything; a paired replay on the 10 000 stand measured 3 statements / 23.607 мс for the wrapper
against 6 / 34.794 for the route, and 5 / 31.029 against 7 / 40.232 (`s78_pair.json`, and
`peer_equals_match_other` was false even there).

The second defect was found while re-reading the run A artifact of stage 77 for this stage: the
fixed `login` wrapper does send its `INSERT INTO refresh_tokens` — a listener over the same engine
sees it — yet the artifact reports `statements_per_call = 1.0`, because the harness's window filter
in `_measure_size` records only statements that start with `s` or `w`. The filter was written for
the EXPLAIN replay, where a write must never run again (`_read_only`), and it silently governs the
counted column too. So `login` publishes 1 where the wrapper pays 2, `session_refresh` publishes 1
where the rotation pays 3, `session_logout` publishes 0 where the revocation pays 1, and the
document has to explain a zero that the count should never have printed
(«ноль в третьей колонке — не пропуск и не пустой вызов»).

Ten checks:

* the capture rule, stated as a function the harness itself uses: a write inside the window is a
  statement the call paid;
* the login wrapper really sends that write — the premise for the rule above, measured;
* the pair page route reads the `matches` row and shows the match's own partner — the premise;
* the harness's `match_detail` pays the same statements, in the same order, as the handler;
* the partner it asks about is the match's, not the harness's;
* the pair's percent screen pays the membership read and the titles read;
* the pair map pays the pair read but no sign-in read, because the auth read belongs to the
  dependency and the harness keeps dependencies outside the window;
* the deck's rebuild does not delete what only a profile edit or a completed test deletes;
* the tap writes exactly what `POST /users/{id}/like` writes;
* the published table has one row per harness path, in harness order — the guard this stage must
  re-green with its re-shot numbers.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import uuid

from httpx import AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.matches import get_match, match_compatibility, match_universe
from app.core.database import engine
from app.models import Match, User

from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)

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


def _relation(after_from: str) -> str:
    words = after_from.split()
    head = words[0] if words else "?"
    if len(words) > 2 and words[1] == "as":
        head = words[2]
    return head.split(".")[-1].strip("(),")


def _token(statement: str) -> str:
    """Reduce a statement to the relation it touches: what a wrapper must share with its route.

    Compared as (verb, relation) pairs because the two sides are recorded in different sessions and
    even with different parameter styles; which row a read binds is asserted separately, by id.
    """
    flat = " ".join(statement.lower().split())
    verb = flat.split(" ", 1)[0]
    if verb == "insert":
        return "insert " + _relation(flat.split(" into ", 1)[-1])
    if verb == "delete":
        return "delete " + _relation(flat.split(" from ", 1)[-1])
    if verb == "update":
        return "update " + _relation(flat.split(" update ", 1)[-1])
    if verb in ("select", "with"):
        # The first FROM is the relation of the outer read; `get_public_profile` joins its
        # loaders into one statement, and both sides of the comparison build it the same way.
        tail = flat.split(" from ", 1)
        return f"{verb} " + (_relation(tail[-1]) if len(tail) == 2 else "?")
    return f"other {verb}"


async def _record(call) -> tuple[object, list[str]]:
    """(result, tokens) for one call, through the engine the app itself uses.

    The listener sits on the engine, not the session, so every statement the call sends lands in
    `seen` regardless of which session opened. A handler that receives an object already in some
    session's identity map sends no SELECT for it — which is why the parity calls below each get a
    session of their own: a mounted route always reads on a fresh request session, and a parity
    test that hides the membership read would certify exactly the wrapper this stage replaces.
    """
    seen: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        seen.append(_token(statement))

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    try:
        result = await call()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)
    return result, seen


async def _fresh(call):
    """Run `call(session)` on its own request session, the way `get_session` hands one per HTTP call."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        _, tokens = await _record(lambda: call(session))
        await session.rollback()
    return tokens


async def _viewer_row(user_id: str) -> User:
    """The viewer as the harness holds it: read before any window opens, then handed over detached.

    `_context()` of the stand reads this row once, outside every measured call, because on the wire
    `get_current_user` resolves it before the handler runs. Both sides of the parity checks below are
    given the same shape, so neither can hide a membership read behind an identity map.
    """
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await session.get(User, uuid.UUID(user_id))


async def _handler_body(user_id: str, run) -> list[str]:
    """Statements of the route's own handler, on a fresh request session, dependency read excluded.

    The boundary this stage settles for every path: the auth read of `users` belongs to
    `get_current_user`, and the harness keeps it out of the window — so the wrapper it prices has to
    match the handler's reads, not the request's total. The wire route test below measures the
    dependency read where it actually happens, on the mounted route.
    """
    current_user = await _viewer_row(user_id)
    return await _fresh(lambda fresh: run(fresh, current_user))


async def _record_full(call) -> list[str]:
    """Tokens AND bound parameters, as one string per statement, for identity assertions."""
    seen: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        seen.append(" ".join(statement.lower().split()) + " || " + str(parameters))

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    try:
        await call()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)
    return seen


def _writes(tokens: list[str]) -> set[str]:
    return {t for t in tokens if not t.startswith("select")}


async def _account(client: AsyncClient, email: str, *, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def _pair(client: AsyncClient, prefix: str) -> tuple[dict, dict, str]:
    """Two onboarded, answered accounts that liked each other, and their match."""
    viewer = await _account(client, f"{prefix}_viewer@befos.app", name="Вера", gender="female")
    partner = await _account(client, f"{prefix}_partner@befos.app", name="Пётр", gender="male")
    await client.post(
        f"/api/v1/users/{partner['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    back = await client.post(
        f"/api/v1/users/{viewer['user_id']}/like", headers=auth_headers(partner["token"])
    )
    assert back.status_code == 200, back.text
    match_id = back.json()["match_id"]
    assert match_id
    return viewer, partner, match_id


async def _ctx(viewer: dict, match_id: str, stranger_id: str | None = None) -> dict:
    """The harness context for one path, shaped like `_context()` builds it for a stand.

    `peer_id` is a deliberate stranger: on the stand the deck's peer and the match's partner are
    different people (`peer_equals_match_other: false` in `s78_pair.json`), so a wrapper that reads
    the deck's person instead of the pair's cannot hide behind equal answers here. `viewer_user` is
    the row the dependency would have handed over, read outside whatever window the test records.
    """
    return {
        "viewer_id": uuid.UUID(viewer["user_id"]),
        "viewer_email": viewer["email"],
        "viewer_user": await _viewer_row(viewer["user_id"]),
        "match_id": uuid.UUID(match_id),
        "peer_id": uuid.UUID(stranger_id) if stranger_id else uuid.UUID(viewer["user_id"]),
        "like_peers": [uuid.UUID(stranger_id)] if stranger_id else [],
        "like_turn": 0,
    }


async def test_the_capture_keeps_every_statement_the_window_pays() -> None:
    """The rule the counted column runs on: a write is a statement the call paid.

    The stage-77 artifact is the evidence: `login` reports 1 statement per call while the wrapper
    demonstrably sends a SELECT and an INSERT, and `session_logout` reports 0 for a call whose whole
    answer is an UPDATE. The filter that drops them was written for the EXPLAIN replay, where a
    write must not run twice; the count has no such reason.
    """
    probe = _probe()
    captured = getattr(probe, "_captured_by_harness", None)
    assert captured is not None, (
        "the harness has no named capture rule, so the window filter is an inline expression again "
        "and any change to it stays invisible to this check"
    )
    assert captured("SELECT users.id FROM users WHERE users.id = $1"), "a read must be counted"
    assert captured(
        "INSERT INTO refresh_tokens (id, user_id) VALUES ($1, $2)"
    ), "the login write of stage 77 must be counted — the published `login` row says 1 without it"
    assert captured(
        "UPDATE refresh_tokens SET revoked = true WHERE token_hash = $1"
    ), "a revocation is the whole answer of the logout route; the table publishes 0 for it today"
    assert captured(
        "WITH queued AS (INSERT INTO discovery_queue RETURNING id) SELECT 1"
    ), "the queue fill is a statement the rebuild paid; only its replay is unsafe, not its count"
    assert captured("DELETE FROM passes WHERE from_user_id = $1"), "a pass forget is a write the tap sends"
    assert not captured(
        "CREATE INDEX ix_profiles_deck_order ON profiles (created_at DESC)"
    ), "the window should still ignore DDL and connection plumbing, which no route pays per call"
    assert not captured(
        "SAVEPOINT sa_savepoint_1"
    ), "a savepoint is the ORM wrapping its own work, not a statement the screen charges for"
    assert not captured("SET timezone = 'UTC'"), "the connection's setup is not part of a call's price"


async def test_the_login_wrapper_sends_the_write_the_capture_threw_away(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Premise for the rule above, measured: the wrapper really pays two statements, not one."""
    probe = _probe()
    email = "s78_login@befos.app"
    await register_and_auth(client, email, password=probe.PASSWORD)
    ctx = {"viewer_email": email}

    _, tokens = await _record(
        lambda: probe._build_paths()["login"](session, ctx)
    )
    assert "insert refresh_tokens" in _writes(tokens), (
        f"the fixed wrapper no longer writes a session; it sent {tokens}. The published 1 for "
        "`login` was defended by the paired replay `s77_login_pair.json` (457.699 vs 464.468 мс), "
        "which counted this INSERT in its own shapes — the loss is in the count, not in the call"
    )


async def test_the_pair_page_route_proves_membership_and_shows_the_match_partner(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The premise: `GET /matches/{id}` reads `matches` first, then the partner's card.

    Also the auth boundary, stated where it is paid: the mounted route opens with a read of `users`
    by the token's subject — `get_current_user` — and this stage's rule puts that read outside the
    harness window, beside the token mint that produced it.
    """
    viewer, partner, match_id = await _pair(client, "s78_wire")
    stranger = await _account(
        client, "s78_wire_stranger@befos.app", name="Игорь", gender="male"
    )

    body, tokens = await _record(
        lambda: client.get(
            f"/api/v1/matches/{match_id}", headers=auth_headers(viewer["token"])
        )
    )
    assert body.status_code == 200, body.text
    assert tokens[0] == "select users", f"the route opens with the auth read, saw {tokens}"
    assert "select matches" in tokens, (
        f"the mounted pair page no longer reads the membership row; it sent {tokens} — then the "
        "harness wrapper that skips it would be honest again and this stage's premise is stale"
    )
    assert body.json()["other_user"]["user_id"] == partner["user_id"], (
        "the page showed somebody who is not the match's partner"
    )
    assert stranger["user_id"] not in str(body.json())


async def test_the_stands_pair_page_pays_the_handlers_own_reads_in_order(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The rule stage 76 wrote for `universe_map` and stage 77 for `login`, aimed at `match_detail`."""
    viewer, partner, match_id = await _pair(client, "s78_detail")
    stranger = await _account(
        client, "s78_detail_stranger@befos.app", name="Игорь", gender="male"
    )
    probe = _probe()
    ctx = await _ctx(viewer, match_id, stranger["user_id"])

    handler_tokens = await _handler_body(
        viewer["user_id"],
        lambda fresh, user: get_match(uuid.UUID(match_id), current_user=user, session=fresh),
    )
    assert "select matches" in handler_tokens, (
        f"a request session must read the membership row; it sent {handler_tokens}"
    )
    wrapper_tokens = await _fresh(
        lambda fresh: probe._build_paths()["match_detail"](fresh, ctx)
    )
    assert wrapper_tokens == handler_tokens, (
        f"the published `match_detail` row prices a call the route does not make: the wrapper sent "
        f"{wrapper_tokens}, the handler of the same route sent {handler_tokens}. The row says 5 "
        "statements; the pair page pays the membership read the wrapper skips"
    )


async def test_the_pair_page_asks_about_the_match_partner_not_the_decks_first_letter(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Whose card the wrapper reads, bound by id rather than by shape.

    On the stand `peer_id` is the crowd's first email and the match's partner is the newest
    partner — different people (`peer_equals_match_other: false`). A wrapper that keeps asking the
    deck's person would price a profile read of a stranger even after it learned to read `matches`.
    """
    viewer, partner, match_id = await _pair(client, "s78_who")
    stranger = await _account(client, "s78_who_stranger@befos.app", name="Игорь", gender="male")
    ctx = await _ctx(viewer, match_id, stranger["user_id"])

    statements = await _record_full(
        lambda: _probe()._build_paths()["match_detail"](session, ctx)
    )
    blob = " ".join(statements)
    assert stranger["user_id"] not in blob, (
        "the pair page read the harness's deck peer: the partner has to come from the match's own "
        "row, the way `match.other_user(current_user.id)` produces it in the handler"
    )
    assert partner["user_id"] in blob, (
        "the pair page never read the partner's card — the screen answers with that profile, so a "
        "window without it is not that screen's price"
    )


async def test_the_stands_percent_screen_pays_what_the_route_reads(
    client: AsyncClient, session: AsyncSession
) -> None:
    """`compatibility` = `GET /matches/{id}/compatibility`: membership, pair, then the titles read.

    The titles read is conditional in the handler (`if explanation.shared_interests`), so it is
    not hardcoded here; sequence equality against the same handler on the same pair puts it inside
    the compared window on both sides.
    """
    probe = _probe()
    viewer, partner, match_id = await _pair(client, "s78_compat")
    stranger = await _account(
        client, "s78_compat_stranger@befos.app", name="Игорь", gender="male"
    )
    ctx = await _ctx(viewer, match_id, stranger["user_id"])

    handler_tokens = await _handler_body(
        viewer["user_id"],
        lambda fresh, user: match_compatibility(
            uuid.UUID(match_id), current_user=user, session=fresh
        ),
    )
    wrapper_tokens = await _fresh(
        lambda fresh: probe._build_paths()["compatibility"](fresh, ctx)
    )
    assert wrapper_tokens == handler_tokens, (
        f"the published `compatibility` row says 3 statements while the route pays "
        f"{len(handler_tokens)}: wrapper {wrapper_tokens} vs handler {handler_tokens}. Two of the "
        "missing ones are the `matches` proof and the `interests` titles the screen prints"
    )


async def test_the_pair_map_pays_the_pair_read_and_no_sign_in_read(
    client: AsyncClient, session: AsyncSession
) -> None:
    """`universe_map` calls its handler — that part stage 76 got right — but read `users` itself.

    The boundary this stage settles for every path: the auth dependency's read of `users` is what
    the token carries, the same class of setup as the minted session of `session_refresh`, and it
    is resolved outside the window. A wrapper that re-reads the viewer inside the window counts a
    statement the handler does not pay; a wrapper that skipped the `matches` row would undercount.
    """
    probe = _probe()
    viewer, partner, match_id = await _pair(client, "s78_universe")
    ctx = await _ctx(viewer, match_id)

    handler_tokens = await _handler_body(
        viewer["user_id"],
        lambda fresh, user: match_universe(uuid.UUID(match_id), current_user=user, session=fresh),
    )
    wrapper_tokens = await _fresh(
        lambda fresh: probe._build_paths()["universe_map"](fresh, ctx)
    )
    assert "select matches" in handler_tokens, (
        f"a request session must read the pair's own row; it sent {handler_tokens}"
    )
    assert wrapper_tokens == handler_tokens, (
        f"the map row counts a read the handler does not pay, or skips one it does: wrapper "
        f"{wrapper_tokens} vs handler {handler_tokens}"
    )
    assert "select users" not in wrapper_tokens, (
        "the wrapper still loads the viewer inside the window; the sign-in read belongs to the "
        "dependency and this stage moves it out, beside the token mint"
    )


async def test_the_decks_rebuild_does_not_delete_what_only_an_edit_deletes(
    client: AsyncClient, session: AsyncSession
) -> None:
    """`deck_invalidate` runs when a profile is saved or a test completed — not on `GET /discover`.

    The wrapper's extra DELETE is the only way that statement would appear in the rebuild's window,
    so it is checked directly: the route was recorded on a viewer whose queue this test had never
    touched. The read filter never counted the DELETE, but the median always paid it, so this moves
    the statement out of the window and into `_empty_deck`, which the harness now runs between the
    repeats — a deck that refilled on the first call would leave the second timing a warm page.
    """
    probe = _probe()
    viewer = await _account(client, "s78_deck_viewer@befos.app", name="Вера", gender="female")
    for i in range(2):
        await _account(client, f"s78_deck_peer{i}@befos.app", name=f"Пётр{i}", gender="male")

    _, route_tokens = await _record(
        lambda: client.get("/api/v1/discover", headers=auth_headers(viewer["token"]))
    )
    assert "delete discovery_queue" not in route_tokens, (
        f"GET /discover now invalidates the deck itself ({route_tokens}); the wrapper's DELETE "
        "would be faithful again and this check is stale"
    )

    _, wrapper_tokens = await _record(
        lambda: probe._build_paths()["discovery_rebuild"](
            session, {"viewer_id": uuid.UUID(viewer["user_id"])}
        )
    )
    assert "delete discovery_queue" not in wrapper_tokens, (
        f"the harness's rebuild sends a DELETE the route never sends; it paid {wrapper_tokens}. "
        "The published 13 statements and the median both include somebody else's screen"
    )


async def test_the_tap_writes_exactly_what_the_like_route_writes(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The writes half of the rule for `POST /users/{id}/like`, on two fresh targets.

    Reads are not compared here: `MatchService.like` commits internally and its second tap would
    take the delete branch a stranger never triggers; the writes are what the row claims.
    """
    probe = _probe()
    viewer, partner, _ = await _pair(client, "s78_tap")
    first = await _account(client, "s78_tap_target1@befos.app", name="Игорь", gender="male")
    second = await _account(client, "s78_tap_target2@befos.app", name="Олег", gender="male")

    ctx = await _ctx(viewer, partner["user_id"], second["user_id"])
    _, wrapper_tokens = await _record(
        lambda: probe._build_paths()["like"](session, ctx)
    )
    await session.rollback()

    _, route_tokens = await _record(
        lambda: client.post(
            f"/api/v1/users/{first['user_id']}/like", headers=auth_headers(viewer["token"])
        )
    )
    wrapper_writes = _writes(wrapper_tokens)
    route_writes = _writes(route_tokens)
    assert wrapper_writes == route_writes, (
        f"the `like` row prices a tap with different writes: wrapper {sorted(wrapper_writes)} vs "
        f"route {sorted(route_writes)}"
    )
    assert "insert likes" in wrapper_writes, (
        "the tap wrote no like row, so it measured the repeat branch instead of a first swipe"
    )


def test_the_published_table_has_one_row_per_harness_path_in_harness_order() -> None:
    """The doc half of the rule, re-greened by this stage's re-shot table.

    Stage 77 wrote this check for its own sixteen rows; after this stage's fixes every path keeps
    its row, and the capture change must not quietly retire a path whose count moved.
    """
    doc = _SCALE_DOC.read_text(encoding="utf-8")
    parts = doc.split("## Задержки горячих путей", 1)
    assert len(parts) == 2, "docs/SCALE_PLAN.md no longer carries the hot-path table"
    section = parts[1].split("\n### ", 1)[0]
    rows = re.findall(r"^\|\s*`([a-z_]+)`\s*\|", section, re.MULTILINE)
    carried = list(_probe()._build_paths())

    assert rows == carried, (
        f"the published table rows {rows} do not match the harness paths {carried} in order — a "
        "path measured but not published is a claim the document never made"
    )
