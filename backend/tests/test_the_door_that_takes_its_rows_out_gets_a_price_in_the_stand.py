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

Fifteen checks, in the order the risk sits:

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
  stand, and the repeat of the same export costs the same as the first call did;
* the two page-sized reads that replaced the per-pair and per-plan loops answer the same rows the
  loops answered — the transcript line by line, the plan's journal against the card that owns it,
  and a journal longer than the card's page ending where the card ends;
* what the row is allowed to cost: four statements per pair — the slope the screen of «Наши планы»
  already publishes — plus the constant the two shoots measured, and four reads of `messages` for
  the whole page instead of one per group.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import pathlib
import re
import uuid

from httpx import AsyncClient
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models import Message, User
from app.repositories.plan_repo import PlanRepository
from app.services.export_service import JOURNAL_LINES
from app.services.plan_service import PlanService

from .test_a_pair_can_agree_on_when_to_meet import _pair, _ready

_PROBE_PATH = pathlib.Path(__file__).resolve().parents[1] / "ops" / "scale_probe.py"
_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCALE_DOC = _ROOT / "docs" / "SCALE_PLAN.md"

EXPORT = "account_export"
CEILING = 500

# Three ceilings read off the stand rather than invented. `s122_scale_a.json` and
# `s122_scale_b.json` agree on the row of this door at 113 statements over twenty pairs and 276 over
# sixty, which is a slope of four statements per pair — the same four the screen of «Наши планы»
# carries in the published table (85 over twenty, 245 over sixty) — and an intercept of 33 on the
# short scale against 36 on the long one, 32 on the six pairs this file itself seeds, so the
# constant below carries the four between the smallest and the largest of them. The ceiling on reads
# of `messages` is the four the batched page pays: one for the last line the pair list shows, one
# count and one windowed read for the transcript, one windowed read for the plan journals. The shape
# these three hold is the one `s122_shape.json` measured before the fix: 41 statements for forty
# pairs and 649 for forty arrangements.
STATEMENTS_PER_PAIR = 4
FILE_OVERHEAD_CEILING = 40
MESSAGES_READS_CEILING = 4


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


async def _account(client: AsyncClient, tag: str, pairs: int = 2, alone: int = 7) -> tuple[dict, dict]:
    """An account with the state the stand's viewer holds: pairs, arrangements, taps, a session.

    The pairs are formed by the two taps that form a pair in the app, the arrangements are written by
    the harness's own seed, and the reader object is lifted the way `_context` lifts it — outside
    every measured window, as `get_current_user` hands it over. The `alone` accounts are people this
    one never paired with, which is exactly the pool the export seed blocks and complains about: a
    block on a paired account would take a pair out of the page the rows above published.
    """
    a = await _ready(client, f"s122_{tag}_a@befos.app", "Аня")
    for index in range(alone):
        await _ready(client, f"s122_{tag}_alone_{index}@befos.app", f"Знакомый {index + 1}")
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
                "AND r.reader_id = :r)"
            ),
            {"m": match_id, "r": reader_id},
        )
    )


async def _lengthen_journal(
    session: AsyncSession, plan_id: uuid.UUID, lines: int
) -> None:
    """Give one arrangement a history longer than the card's page, each line a minute later.

    Lines are written as the plan writes them — one row of `messages` carrying `plan_id` — because
    the two reads under test are a read of that table and nothing else.
    """
    await session.execute(
        text(
            """
            INSERT INTO messages (id, match_id, sender_id, body, is_deleted, kind,
                                  plan_activity_id, plan_id, created_at, updated_at)
            SELECT gen_random_uuid(), p.match_id, p.created_by,
                   'Строка ' || g || ' о том же вечере.', false, 'plan_changed',
                   p.activity_id, p.id,
                   now() + make_interval(mins => g), now() + make_interval(mins => g)
            FROM shared_plans p, generate_series(1, :n) g
            WHERE p.id = :plan
            """
        ),
        {"plan": plan_id, "n": lines},
    )
    await session.commit()


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
    assert "password_hash" not in source and "create_token" not in source, (
        "the preparation reaches for a password or mints token material: the file it prices must "
        f"carry neither, and a seed that writes them invites a section that reads them — {source[:600]}"
    )


async def _own_rows(session: AsyncSession, viewer_id: uuid.UUID) -> dict[str, int]:
    """The rows the export's own seed puts under the viewer, counted one by one.

    The history row is in here too: a complaint the queue has looked at carries a `report_reviews`
    row, so a seed that decided a second complaint on its second call would leave the row of one
    scale standing on two statuses while another scale's row stands on one.
    """
    found = await session.execute(
        text(
            "SELECT (SELECT count(*) FROM photos WHERE user_id = :v) AS photos, "
            "       (SELECT count(*) FROM blocks WHERE blocker_id = :v) AS blocks, "
            "       (SELECT count(*) FROM reports WHERE reporter_id = :v) AS reports, "
            "       (SELECT count(*) FROM reports WHERE reporter_id = :v "
            "        AND status <> 'open') AS decided, "
            "       (SELECT count(*) FROM report_reviews rr JOIN reports r ON r.id = rr.report_id "
            "        WHERE r.reporter_id = :v) AS reviews, "
            "       (SELECT count(*) FROM refresh_tokens WHERE user_id = :v "
            "        AND revoked IS FALSE) AS sessions"
        ),
        {"v": viewer_id},
    )
    return {name: int(value) for name, value in found.mappings().first().items()}


async def test_the_setup_second_call_writes_nothing_new(client: AsyncClient) -> None:
    a, ctx = await _account(client, "twice")
    setup = _probe()._build_setups()[EXPORT]
    async with AsyncSessionLocal() as session:
        ctx["viewer_user"] = await _viewer_row(a["user_id"])
        await setup(session, ctx)
        before = await _own_rows(session, ctx["viewer_id"])
        await setup(session, ctx)
        after = await _own_rows(session, ctx["viewer_id"])
    assert after == before, (
        "the second call of one scale put a fresh page of rows on top of the first: stage 118 "
        f"learned this on the taps — {before} against {after}"
    )
    assert before["photos"] and before["blocks"] and before["reports"], (
        f"the seed left a section of the file with nothing to read: {before}"
    )
    assert before["reviews"] == before["decided"] == 1, (
        "the number of decided complaints is not one rule of the scale: the row of the complaints "
        f"section would then stand on a different history at every scale — {before}"
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


async def test_the_priced_window_holds_the_screens_slope_and_pays_its_reads_once(
    client: AsyncClient, session: AsyncSession
) -> None:
    """What the door may cost, written as the two numbers the stand measured rather than as prose.

    The slope belongs to the screen of «Наши планы», and the file is allowed no more than the screen
    charges for a pair; the reads of `messages` belong to the page and must stay one count and two
    windows however many pairs and arrangements the account holds. Before stage 122 the same window
    paid one read per pair for its transcript and a card's worth of reads per arrangement
    (`s122_shape.json`: 41 statements on forty pairs, 649 on forty arrangements).
    """
    a, ctx = await _account(client, "slope", pairs=6)
    async with AsyncSessionLocal() as fresh:
        ctx["viewer_user"] = await _viewer_row(a["user_id"])
        await _probe()._build_setups()[EXPORT](fresh, ctx)

    statements, _ = await _window(session, ctx)
    pairs = int(await session.scalar(
        text("SELECT count(*) FROM matches WHERE user_a_id = :v OR user_b_id = :v"),
        {"v": ctx["viewer_id"]},
    ))
    assert pairs >= 6, f"the account this check runs on holds {pairs} pairs, not six"
    windows = [s for s in statements if "row_number() over" in s]
    assert len(windows) == 2, (
        "the page did not ask its two capped questions once each: the transcript and the plan "
        f"journals are two windowed reads for the whole account, not a read per group — {windows}"
    )
    messages = [s for s in statements if "from messages" in s]
    assert len(messages) <= MESSAGES_READS_CEILING, (
        f"the window paid {len(messages)} reads of `messages` on {pairs} pairs: a count that moves "
        "with the number of groups is the loop this stage removed — "
        + "\n".join(messages[:8])[:800]
    )
    assert len(statements) <= STATEMENTS_PER_PAIR * pairs + FILE_OVERHEAD_CEILING, (
        f"the file costs {len(statements)} statements on {pairs} pairs, which is more than the four "
        "the screen charges per pair plus the constant the stand measured: the row of "
        f"`docs/SCALE_PLAN.md` is this door read at the screen's price, not at a card per "
        f"arrangement — {statements[:4]}"
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


async def test_the_batched_chats_hold_every_line_the_loop_wrote(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The page-sized read answers the same pairs, in the same order, with the same cut.

    Written as a loop beside the batched section rather than as a snapshot of it: what has to stay
    true after a refactor is the answer, and the answer is stated here in the shape the door had
    before stage 122 priced it — one capped read per pair, oldest line first.
    """
    a, ctx = await _account(client, "chatloop")
    async with AsyncSessionLocal() as fresh:
        ctx["viewer_user"] = await _viewer_row(a["user_id"])
        await _probe()._build_setups()[EXPORT](fresh, ctx)

    document = _body((await _window(session, ctx))[1])
    pairs = document["pairs"]
    assert pairs, "the account this check runs on has no pair to read a transcript of"

    for entry in document["chats"]:
        match_id = uuid.UUID(entry["match_id"])
        rows = list(
            (
                await session.execute(
                    select(Message)
                    .where(Message.match_id == match_id)
                    .order_by(Message.created_at, Message.id)
                    .limit(CEILING + 1)
                )
            )
            .scalars()
            .all()
        )
        expected = [str(row.id) for row in rows[:CEILING]]
        assert [line["id"] for line in entry["lines"]] == expected, (
            f"the batched transcript of pair {match_id} is not the loop's: {expected} against "
            f"{[line['id'] for line in entry['lines']]}"
        )


async def test_the_file_holds_the_journal_the_plan_card_answers(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Every plan in the file carries the card's own answer for the same arrangement.

    The file used to ask the card once per plan; now it asks two questions for the page. This check
    is the reason the two cannot drift: for each arrangement in the document the card is opened
    again, and its remark and its lines have to be the ones the file printed.
    """
    a, ctx = await _account(client, "card")
    viewer_id = ctx["viewer_id"]
    async with AsyncSessionLocal() as fresh:
        ctx["viewer_user"] = await _viewer_row(a["user_id"])
        await _probe()._build_setups()[EXPORT](fresh, ctx)

    document = _body((await _window(session, ctx))[1])
    plans = document["plans"]
    assert plans, "the account this check runs on holds no arrangement to compare"
    service = PlanService(session)
    for row in plans:
        detail = await service.detail(uuid.UUID(row["id"]), viewer_id)
        assert row["my_note"] == detail["my_note"], (
            f"the file prints another remark than the card answers for plan {row['id']}"
        )
        assert row["journal"] == [
            {
                "id": str(event["id"]),
                "sender_id": str(event["sender_id"]),
                "kind": event["kind"],
                "body": event["body"],
                "created_at": event["created_at"],
            }
            for event in detail["events"]
        ], f"the file's journal of plan {row['id']} is not the card's history"


async def test_a_journal_longer_than_the_cards_page_ends_where_the_card_ends(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Thirty-five lines of one plan answer the card's thirty, and not the window's thirty-one.

    The batched read asks for one line more than it keeps, because that line is what names a cut
    where a transcript is concerned. A plan's history has never been named as cut — the card simply
    shows its page — so the wider window is the one place where the two reads could part without
    anybody saying so, and the file would carry a line the screen does not.
    """
    a, ctx = await _account(client, "longjournal")
    viewer_id = ctx["viewer_id"]
    async with AsyncSessionLocal() as fresh:
        ctx["viewer_user"] = await _viewer_row(a["user_id"])
        await _probe()._build_setups()[EXPORT](fresh, ctx)

    before = _body((await _window(session, ctx))[1])
    assert before["plans"], "the account this check runs on holds no arrangement"
    plan_id = uuid.UUID(before["plans"][0]["id"])
    await _lengthen_journal(session, plan_id, JOURNAL_LINES + 5)

    document = _body((await _window(session, ctx))[1])
    row = next(plan for plan in document["plans"] if plan["id"] == str(plan_id))
    detail = await PlanService(session).detail(plan_id, viewer_id)
    assert len(row["journal"]) == JOURNAL_LINES, (
        f"the file carries {len(row['journal'])} lines of a plan whose history outgrew the card's "
        f"page of {JOURNAL_LINES}: the extra row the window found is its way of noticing a cut, not "
        "a line to print"
    )
    assert [line["id"] for line in row["journal"]] == [
        str(event["id"]) for event in detail["events"]
    ], "the newest lines the file keeps are not the newest lines the card keeps"


def test_the_journal_of_the_file_is_the_page_the_card_reads() -> None:
    """The two ceilings of one history are one number, and nothing else gets to move it alone."""
    default = inspect.signature(PlanRepository.events).parameters["limit"].default
    assert default == JOURNAL_LINES, (
        f"the card reads {default} lines of a plan's history while the file keeps {JOURNAL_LINES}: "
        "two ceilings of the same journal are two stories about one arrangement"
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
