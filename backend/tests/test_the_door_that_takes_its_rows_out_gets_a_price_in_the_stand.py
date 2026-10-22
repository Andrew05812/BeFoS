"""The door that hands a person their own rows has been unpriced since stage 121 named it so.

Stage 121 opened `GET /api/v1/users/me/export` and closed with its own open end written down: the
door has no path in `backend/ops/scale_probe.py` and no row in `docs/SCALE_PLAN.md`, so how many
statements a person pays to take their life out of the app was nobody's number. The ceiling of 500
rows per section was tested by swapping the ceiling for two, not by an account whose section is
actually longer than the ceiling, and the document's own volume was never counted either.

This file is the guard for that row, and it checks the door through the *harness wrapper* — the same
callable the stand times — so that the state it proves (nothing written, nothing marked read, no
secret travelling, one page length priced twice) is the state of the measured call rather than of a
copy someone made for the test.

Nine checks, in the order the risk sits:

* the registry has the path, and its wrapper calls the handler the route dispatches with the reader
  and the session id the context carries — stage 76 and stage 77 each published a price that
  belonged to `get_current_user` instead of the screen;
* the door is timed after every path whose rows it gathers: its own preparation must not move a
  number that is already in the published table, which is the rule stage 119 put on the plan seed;
* its preparation gives the sections rows to read — a document gathered from an account that holds
  no photographs, no complaints and no blocks prices an empty box, the mistake stage 113 met on the
  inbox — and the second call of one scale writes nothing new, the rule stage 118 met on the taps;
* the priced window writes nothing and marks nothing read: reading one's own file must not cost the
  partner their unread count;
* the answer the priced window returns is a file, and it carries neither the password hash nor the
  material of a token nor the hand of the moderator who closed a complaint;
* a section longer than the ceiling is named as cut while `counts` keeps the number of rows that
  stand, and the repeat of the same export costs the same as the first call did.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import pathlib
import re
import uuid

from httpx import AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models import User

from .test_a_pair_can_agree_on_when_to_meet import _pair, _ready

_PROBE_PATH = pathlib.Path(__file__).resolve().parents[1] / "ops" / "scale_probe.py"
_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCALE_DOC = _ROOT / "docs" / "SCALE_PLAN.md"

EXPORT = "account_export"
CEILING = 500


def _probe():
    """Load the stand as a module: it is a script, so it is not on the import path."""
    spec = importlib.util.spec_from_file_location("scale_probe", _PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _viewer_row(user_id: str) -> User:
    async with AsyncSessionLocal() as session:
        return await session.get(User, uuid.UUID(user_id))


async def _account(client: AsyncClient, tag: str, pairs: int = 2) -> tuple[dict, dict]:
    """An account with the state the stand's viewer holds: pairs, arrangements, taps, a session.

    The pairs are formed by the two taps that form a pair in the app, the arrangements are written by
    the harness's own seed, and the reader object is lifted the way `_context` lifts it — outside
    every measured window, as `get_current_user` hands it over.
    """
    a = await _ready(client, f"s122_{tag}_a@befos.app", "Аня")
    for index in range(pairs):
        peer = await _ready(client, f"s122_{tag}_peer_{index}@befos.app", f"Собеседник {index + 1}")
        await _pair(client, a, peer)
    ctx = {
        "viewer_email": a["email"],
        "viewer_id": uuid.UUID(a["user_id"]),
        "viewer_user": None,
    }
    async with AsyncSessionLocal() as session:
        ctx["viewer_user"] = await _viewer_row(a["user_id"])
        setups = _probe()._build_setups()
        for name in ("liked", "plans", "plan_detail"):
            setup = setups.get(name)
            if setup is not None:
                await setup(session, ctx)
    return a, ctx


async def _window(session: AsyncSession, ctx: dict):
    """Run one measured call of the export door and keep every statement its window sends."""
    statements: list[str] = []

    def before(conn, cursor, stmt, parameters, context, executemany):
        statements.append(" ".join(stmt.lower().split()))

    engine = session.sync_session.get_bind()
    event.listen(engine, "before_cursor_execute", before)
    try:
        out = await _probe()._build_paths()[EXPORT](session, ctx)
    finally:
        event.remove(engine, "before_cursor_execute", before)
    return statements, out


def _body(response) -> dict:
    """The document of a priced call: whatever the wrapper hands back, it is the handler's answer."""
    payload = getattr(response, "body", None)
    if payload is not None:
        return json.loads(payload.decode("utf-8"))
    return response


async def _unread(session: AsyncSession, match_id: uuid.UUID, reader_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            text(
                "SELECT count(*) FROM messages m WHERE m.match_id = :m AND m.sender_id <> :r "
                "AND NOT EXISTS (SELECT 1 FROM message_reads r WHERE r.message_id = m.id "
                "AND r.user_id = :r)"
            ),
            {"m": match_id, "r": reader_id},
        )
    )


def test_the_harness_has_a_path_for_the_export_door() -> None:
    paths = _probe()._build_paths()
    assert EXPORT in paths, (
        f"the harness prices {len(paths)} paths and `{EXPORT}` is not one of them: stage 121 named "
        "the missing row as its own open end, and the door has answered taps since that night"
    )


def test_the_export_wrapper_calls_the_handler_the_route_dispatches() -> None:
    source = inspect.getsource(_probe()._build_paths()[EXPORT])
    assert "from app.api.v1.users import export_account as export_account_route" in source, (
        "the export row prices a private re-assembly of the twelve section reads instead of the "
        f"handler the route dispatches: {source}"
    )
    assert 'current_user=ctx["viewer_user"]' in source, (
        "the export wrapper resolves its reader inside its own window: stage 76 and stage 77 each "
        f"published a number that belonged to the auth dependency: {source}"
    )
    assert 'ctx["export_session_id"]' in source, (
        "the row this token stands on is taken from somewhere inside the measured call rather than "
        "from the context: the sessions section says which device the file was gathered from, and "
        f"that is the state the door is priced on — {source}"
    )


def test_the_export_door_is_timed_after_every_row_whose_state_it_gathers() -> None:
    order = list(_probe()._build_paths())
    assert EXPORT in order, f"`{EXPORT}` is not in the registry"
    assert order.index(EXPORT) == len(order) - 1, (
        "the export is not last: its preparation is the first thing on the stand that puts "
        "photographs, complaints and blocks under the viewer, and any older row that reads those "
        f"tables would then publish a page length nobody shot — {order}"
    )
    for name in ("liked", "plans", "plan_detail", "passed"):
        assert order.index(name) < order.index(EXPORT), (
            f"`{name}` is timed after the export: the document gathers exactly the rows that door's "
            f"seed writes, so its page length would depend on a seed that had not run yet — {order}"
        )


def test_the_export_setup_gives_the_sections_rows_to_read() -> None:
    setups = _probe()._build_setups()
    assert EXPORT in setups, (
        "the export row has a path and no preparation: the stand's viewer holds no photograph, no "
        "complaint and no block, so those three sections would price an empty box and the row would "
        "publish the price of an account nobody has this on"
    )
    source = inspect.getsource(setups[EXPORT])
    assert re.search(r"EXPORT_(PHOTOS|COMPLAINTS|BLOCKS)", source), (
        "the seed does not name how many rows it puts behind each section: a page length that is not "
        f"a rule of the scale is a page length nobody can reproduce — {source[:600]}"
    )
    assert "password_hash" not in source and "refresh" not in source.lower(), (
        f"the preparation reaches for a secret or for token material: {source[:600]}"
    )


async def test_the_setup_second_call_writes_nothing_new(client: AsyncClient) -> None:
    a, ctx = await _account(client, "twice")
    setup = _probe()._build_setups()[EXPORT]
    async with AsyncSessionLocal() as session:
        ctx["viewer_user"] = await _viewer_row(a["user_id"])
        await setup(session, ctx)
        again = _probe()._build_paths()  # noqa: F841 — the registry must stay loaded for the window
        before = {
            table: await session.scalar(
                text(f"SELECT count(*) FROM {table} WHERE "  # noqa: S608 — fixed table names below
                     + {"photos": "user_id", "reports": "reporter_id",
                        "blocks": "blocker_id"}[table]
                     + " = :v"),
                {"v": ctx["viewer_id"]},
            )
            for table in ("photos", "reports", "blocks")
        }
        await setup(session, ctx)
        after = {
            table: await session.scalar(
                text(f"SELECT count(*) FROM {table} WHERE "
                     + {"photos": "user_id", "reports": "reporter_id",
                        "blocks": "blocker_id"}[table]
                     + " = :v"),
                {"v": ctx["viewer_id"]},
            )
            for table in ("photos", "reports", "blocks")
        }
    assert after == before, (
        "the second call of one scale put a fresh page of rows on top of the first: stage 118 "
        f"learned this on the taps — {before} against {after}"
    )


async def test_the_priced_window_writes_nothing_and_marks_nothing_read(
    client: AsyncClient, session: AsyncSession
) -> None:
    a, ctx = await _account(client, "quiet")
    async with AsyncSessionLocal() as fresh:
        ctx["viewer_user"] = await _viewer_row(a["user_id"])
        await _probe()._build_setups()[EXPORT](fresh, ctx)
        match_id = await fresh.scalar(
            text("SELECT id FROM matches WHERE user_a_id = :v OR user_b_id = :v "
                 "ORDER BY created_at LIMIT 1"),
            {"v": ctx["viewer_id"]},
        )
        partner = await fresh.scalar(
            text("SELECT CASE WHEN user_a_id = :v THEN user_b_id ELSE user_a_id END "
                 "FROM matches WHERE id = :m"),
            {"v": ctx["viewer_id"], "m": match_id},
        )
        reads_before = await _unread(session, match_id, ctx["viewer_id"])
        partner_unread_before = await _unread(session, match_id, partner)
        rows_before = int(await session.scalar(text("SELECT count(*) FROM message_reads")))

        statements, _ = await _window(session, ctx)
        writes = [s for s in statements if s.lstrip().startswith(("insert", "update", "delete"))]
        assert writes == [], (
            "the priced export wrote inside its own window — a person taking their file must not "
            f"change their account: {' | '.join(writes)[:600]}"
        )
        assert await _unread(session, match_id, ctx["viewer_id"]) == reads_before, (
            "the export marked the viewer's own backlog read: `ChatService.history` does that on the "
            "way out, and the door reads through plain statements precisely so that it cannot"
        )
        assert int(await session.scalar(text("SELECT count(*) FROM message_reads"))) == rows_before, (
            "the export added read marks to the table"
        )
        assert await _unread(session, match_id, partner) == partner_unread_before, (
            "reading one's own file cost the partner an unread line: the badge is the other "
            "person's state"
        )


async def test_the_priced_answer_is_a_file_and_carries_no_secret(
    client: AsyncClient, session: AsyncSession
) -> None:
    a, ctx = await _account(client, "secret")
    async with AsyncSessionLocal() as fresh:
        ctx["viewer_user"] = await _viewer_row(a["user_id"])
        await _probe()._build_setups()[EXPORT](fresh, ctx)
    _statements, response = await _window(session, ctx)
    disposition = dict(getattr(response, "headers", {}) or {}).get("content-disposition", "")
    assert disposition.startswith("attachment; filename=\"befos-account-"), (
        f"the priced answer is a page, not a file: {disposition}"
    )
    document = _body(response)
    assert document["format"] == "befos.account-export/1", document.get("format")
    assert document["counts"]["photos"] > 0 and document["counts"]["complaints"] > 0, (
        "the export is priced over an account with no photographs and no complaints: its row would "
        f"publish the price of an empty box — {document['counts']}"
    )
    blob = json.dumps(document, ensure_ascii=False, default=str)
    for secret in ("password_hash", "$2b$", "moderator_id", "moderator_comment", "token"):
        assert secret not in blob, (
            f"the priced document carries `{secret}`: nothing secret travels out of this door"
        )


async def test_a_section_longer_than_the_ceiling_is_named_and_still_counted(
    client: AsyncClient, session: AsyncSession
) -> None:
    a, ctx = await _account(client, "ceiling")
    async with AsyncSessionLocal() as fresh:
        ctx["viewer_user"] = await _viewer_row(a["user_id"])
        await _probe()._build_setups()[EXPORT](fresh, ctx)
        match_id = await fresh.scalar(
            text("SELECT id FROM matches WHERE user_a_id = :v OR user_b_id = :v "
                 "ORDER BY created_at LIMIT 1"),
            {"v": ctx["viewer_id"]},
        )
        await fresh.execute(
            text(
                "INSERT INTO messages (id, match_id, sender_id, body, is_deleted, created_at, "
                "updated_at) SELECT gen_random_uuid(), :m, :v, 'Строка ' || g, false, "
                "now() - make_interval(mins => g), now() FROM generate_series(1, :n) g"
            ),
            {"m": match_id, "v": ctx["viewer_id"], "n": CEILING + 7},
        )
        await fresh.commit()

    _statements, response = await _window(session, ctx)
    document = _body(response)
    assert "chats" in document["limits"]["truncated"], (
        f"a transcript of {CEILING + 7} lines was cut without saying so: {document['limits']}"
    )
    assert document["limits"]["rows_per_section"] == CEILING
    assert document["counts"]["chats"] == CEILING + 7, (
        "the file agreed with its own cut: `counts` owes the number of lines that stand in the "
        f"database, not the number the ceiling let through — {document['counts']['chats']}"
    )
    held = max(len(entry["lines"]) for entry in document["chats"])
    assert held == CEILING, (
        f"the section itself carried other than the ceiling of lines: {held}"
    )


async def test_the_second_export_costs_what_the_first_cost(
    client: AsyncClient, session: AsyncSession
) -> None:
    a, ctx = await _account(client, "repeat")
    async with AsyncSessionLocal() as fresh:
        ctx["viewer_user"] = await _viewer_row(a["user_id"])
        await _probe()._build_setups()[EXPORT](fresh, ctx)

    first, _ = await _window(session, ctx)
    second, _ = await _window(session, ctx)
    assert len(second) == len(first), (
        "the repeat of one export costs other than its first call: the row of the table is a median "
        f"over repeats, so a door whose price moves between them publishes a median of nothing — "
        f"{len(first)} against {len(second)}"
    )
    assert len([s for s in second if s.lstrip().startswith("select")]) == len(second), (
        "the window paid for something besides reading twice in a row"
    )


def test_the_published_latency_table_carries_the_export_row() -> None:
    doc = _SCALE_DOC.read_text(encoding="utf-8")
    assert re.search(r"^### Стадия 122[^\n]*$", doc, re.MULTILINE), (
        "docs/SCALE_PLAN.md has no section for the stage that priced the export door: the document "
        "is where the open end of stage 121 was named, and it has to say what closed it"
    )
    parts = doc.split("## Задержки горячих путей", 1)
    assert len(parts) == 2, "docs/SCALE_PLAN.md no longer carries the hot-path table"
    table = parts[1].split("\n### ", 1)[0]
    row = re.search(rf"^\|\s*`{EXPORT}`\s*\|(.+)$", table, re.MULTILINE)
    assert row, (
        "the harness prices the export door but the published table has no row for it — the document "
        "cannot publish a number the instrument does not take"
    )
    cells = [cell.strip() for cell in row.group(1).split("|") if cell.strip()]
    assert len(cells) == 3, f"a latency row carries one cell per scale, this one carries {cells}"
    for cell in cells:
        assert re.fullmatch(r"\d+(?:[.,]\d+)? / \d+(?:[.,]\d+)? / \d+(?:\.\d+)?", cell), (
            f"`{cell}` is not the published shape медиана / максимум / число запросов"
        )
