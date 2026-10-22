"""The plan family has had two writing doors since stage 108, and the stand has never priced one.

Stage 119 put the screen of «Наши планы» and its card into the registry and named what was left: its
open end said the writing doors of the family are unmeasured. Two of those doors are the agreement
itself — `POST /api/v1/plans/{id}/hour` names an evening, `POST /api/v1/plans/{id}/hour/confirm`
agrees to the one the other half named. They are the only doors of the family that write a line into
the pair's chat, and they are the reason the card row of stage 119 had to be honest about its state:
the probe read the card over a journal with nothing in it (`s119_scale_a.json`: 12 statements per
call, its plan showing `Limit` over 0 rows at 1 000 and at 50 000).

Three measurements decided the shape of these rows, and each of them is a check below.

* `s120_gap.json` (db `befos_s120gap`, tree `9ea1e5e`) counted the tap that moves an evening: 25
  statements on an arrangement the pair still stands on, 22 when the plan had already been asked
  about, and 18 with nothing written when the tap named the hour the plan already holds — the journal
  of this family is a diff, not a tap counter. A refusal costs 11 statements and writes nothing.
* `s120_shape.log` (db `befos_s120shape`) made the answer door reply to a question that had been
  written with a raw UPDATE of the partner's row: the projection still read the old evening as
  agreed, so the answer wrote a `plan_voided` line and no `plan_agreed` one. A question is not a
  value in a column — it arrives through the other half's tap, and `_record_ask` is what puts it on
  the plan.
* `s120_shape2.json` (db `befos_s120shape2`) built the question the way the app does, by asking the
  partner through `PlanService.offer_hour`, and the two doors came back stable: 25 statements and two
  chat lines for the move, 22 statements and one `plan_agreed` line for the answer, and the card of a
  plan whose own evening was moved reads 13 statements instead of 12.

Ten checks, in the order the risk sits: both doors have a path and one shared setup; they sit between
the screen and its card, so the card is finally priced over a journal that is not empty; each wrapper
calls the handler its route dispatches and takes its reader and its queue from the context; the seed
asks the partner through the verb the partner actually taps and stops at the arrangements it already
asked about; the two windows carry the writes they owe; and the published table carries both rows.
"""

from __future__ import annotations

import importlib.util
import inspect
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

WRITING_DOORS = ("plan_hour", "plan_hour_confirm")


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


def _door_ctx(viewer: dict, **queue) -> dict:
    """The context a setup leaves behind: the reader's id and the queues of arrangements to tap."""
    return {"viewer_id": uuid.UUID(viewer["user_id"]), "viewer_user": None, **queue}


async def _stand_pairs(client: AsyncClient, tag: str, count: int = 2) -> tuple[dict, dict]:
    """The state the stand seeds: the viewer's pairs, one arrangement per pair, no chat line yet.

    The pairs are formed by the two taps that form a pair in the app, and the arrangements are written
    by the harness's own seed, so the journal these doors read and fill starts where the stand's does.
    Building an arrangement through the recommendation routes instead would leave `plan_proposed` and
    `plan_agreed` lines behind, and the card row this stage moves would no longer be the read stage 119
    published over an empty journal (12 statements, `s119_scale_a.json`).
    """
    a = await _ready(client, f"s120_{tag}_a@befos.app", "Аня")
    for index in range(count):
        peer = await _ready(client, f"s120_{tag}_peer_{index}@befos.app", f"Собеседник {index + 1}")
        await _pair(client, a, peer)
    ctx = _door_ctx(a)
    async with AsyncSessionLocal() as session:
        ctx["viewer_user"] = await _viewer_row(a["user_id"])
        await _probe()._build_setups()["plan_hour"](session, ctx)
    return a, ctx


async def _journal(session: AsyncSession, plan_id: uuid.UUID) -> list[str]:
    """The kinds this pair's chat holds about this arrangement, oldest first."""
    return list((await session.execute(
        text("SELECT m.kind FROM messages m JOIN shared_plans p ON p.match_id = m.match_id "
             "AND p.activity_id = m.plan_activity_id WHERE p.id = :p ORDER BY m.created_at, m.id"),
        {"p": plan_id},
    )).scalars())


async def _window(session: AsyncSession, path: str, ctx: dict):
    """Run one measured call of `path` and keep every statement its window sends."""
    statements: list[str] = []

    def before(conn, cursor, stmt, parameters, context, executemany):
        statements.append(" ".join(stmt.lower().split()))

    engine = session.sync_session.get_bind()
    event.listen(engine, "before_cursor_execute", before)
    try:
        out = await _probe()._build_paths()[path](session, ctx)
    finally:
        event.remove(engine, "before_cursor_execute", before)
    return statements, out


def _writes(statements: list[str]) -> list[str]:
    return [s for s in statements if s.lstrip().startswith(("insert", "update", "delete"))]


def test_the_harness_has_a_path_for_each_writing_door() -> None:
    paths = _probe()._build_paths()
    for name in WRITING_DOORS:
        assert name in paths, (
            f"the harness prices {len(paths)} paths and `{name}` is not one of them: this door has "
            "answered taps since stage 108, and the only rows of the plan family in "
            "`docs/SCALE_PLAN.md` are the two reads stage 119 put in"
        )


def test_both_writing_doors_share_one_setup_besides_their_row() -> None:
    setups = _probe()._build_setups()
    for name in WRITING_DOORS:
        assert name in setups, (
            f"`{name}` has a row and no preparation: the stand seeds arrangements the pair *stands* "
            "on, and a question the other half is asking arrives only through the other half's tap. "
            "Without a setup the answer door would price a refusal — `s120_gap.json` counted one at "
            "11 statements and no writes"
        )
    assert setups[WRITING_DOORS[0]] is setups[WRITING_DOORS[1]], (
        "the two doors are prepared by two different states: a tap and its answer have to be priced "
        "over one list of arrangements, the rule stage 118 put on the taps and stage 119 on the "
        "plan seed"
    )


def test_the_two_writes_sit_between_the_screen_and_its_card() -> None:
    order = list(_probe()._build_paths())
    for name in WRITING_DOORS:
        assert name in order, f"`{name}` is not in the registry"
    assert order.index("plans") < order.index(WRITING_DOORS[0]) < order.index(WRITING_DOORS[1]), (
        "the writing doors do not follow the screen: the screen row of stage 119 is published over "
        f"arrangements nobody has moved, and these taps would change it — {order}"
    )
    assert order.index(WRITING_DOORS[1]) < order.index("plan_detail"), (
        "the card is timed before anything wrote a line about its plan: stage 119 published it over "
        "an empty journal at 12 statements, and `s120_shape2.json` measures the same read at 13 over "
        f"a journal its own plan filled — the card owes the history, not an empty box: {order}"
    )


def test_the_move_wrapper_calls_the_dispatched_handler() -> None:
    source = inspect.getsource(_probe()._build_paths()["plan_hour"])
    assert "from app.api.v1.plans import offer_hour as offer_hour_route" in source, (
        "the move row prices a private re-assembly of the service steps instead of the handler the "
        f"route dispatches: {source}"
    )
    assert 'current_user=ctx["viewer_user"]' in source, (
        "the move wrapper resolves its reader inside its own window: stage 76 and stage 77 each "
        f"published a number that belonged to the auth dependency: {source}"
    )
    assert 'ctx["hour_moves"]' in source and "MeetingTimeIn(" in source, (
        "the instant this tap names comes from somewhere inside the measured call rather than from "
        "the queue the setup filled: the address and the hour are the state the door is priced on, "
        f"the way `unlike` takes its pool: {source}"
    )


def test_the_answer_wrapper_answers_the_hour_the_partner_named() -> None:
    source = inspect.getsource(_probe()._build_paths()["plan_hour_confirm"])
    assert "from app.api.v1.plans import confirm_hour as confirm_hour_route" in source, (
        f"the answer row does not close the door the route closes: {source}"
    )
    assert 'ctx["hour_questions"]' in source, (
        "the answer sends an hour it made up instead of the one the partner is asking about: this "
        "door refuses a value that moved («That time is no longer the one being offered»), so an "
        f"invented instant would price a 409: {source}"
    )
    assert 'current_user=ctx["viewer_user"]' in source, (
        f"the answer wrapper pays for reading its own user inside the window: {source}"
    )


def test_the_seed_asks_the_partner_through_the_verb_the_partner_taps() -> None:
    source = inspect.getsource(_probe()._build_setups()[WRITING_DOORS[0]])
    assert "PlanService" in source and re.search(r"\.offer_hour\(", source), (
        "the question this stage prices an answer to is written by hand instead of tapped: a raw "
        "UPDATE of the partner's row leaves the plan standing on the old evening, and the answer then "
        "writes `plan_voided` and no `plan_agreed` — the first take of `s120_shape.py` measured "
        f"exactly that: {source[:600]}"
    )
    assert "UPDATE activity_preferences" not in source, (
        "the seed touches the partner's preference row directly: the plan's question is a projection "
        f"of two rows plus `_record_ask`, and only the verb keeps them together: {source[:600]}"
    )
    assert "HOUR_ARRANGEMENTS" in source, (
        "the seed does not name how many arrangements it puts in front of the two doors: a door "
        "whose queue ran out mid-scale either repeats an arrangement and prices a different tap, or "
        f"fails: {source[:600]}"
    )


async def test_the_second_call_of_the_seed_asks_the_same_questions_again(
    client: AsyncClient,
) -> None:
    _a, ctx = await _stand_pairs(client, "twice")
    setup = _probe()._build_setups()[WRITING_DOORS[0]]
    moves, questions = list(ctx["hour_moves"]), list(ctx["hour_questions"])
    assert moves and questions, (
        f"one of the two doors got no arrangement to work on: {moves} against {questions}"
    )

    again = _door_ctx(_a)
    again["viewer_user"] = ctx["viewer_user"]
    async with AsyncSessionLocal() as session:
        before = await session.scalar(
            text("SELECT count(*) FROM messages WHERE plan_activity_id IS NOT NULL")
        )
        await setup(session, again)
        after = await session.scalar(
            text("SELECT count(*) FROM messages WHERE plan_activity_id IS NOT NULL")
        )
    assert after == before, (
        "the second call of one scale asked the partner again and wrote a fresh page of chat lines: "
        f"the seed owes the rule stage 118 put on the taps — {before} lines before, {after} after"
    )
    assert list(again["hour_moves"]) == moves and list(again["hour_questions"]) == questions, (
        "the two calls handed the doors different queues, so their rows would price different "
        f"arrangements: {moves} / {questions} against {again['hour_moves']} / "
        f"{again['hour_questions']}"
    )


async def test_the_move_window_writes_the_two_lines_a_moved_evening_owes(
    client: AsyncClient, session: AsyncSession
) -> None:
    a, ctx = await _stand_pairs(client, "move")
    plan_id, when = ctx["hour_moves"][0]
    before = await _journal(session, plan_id)

    statements, _ = await _window(session, "plan_hour", dict(ctx, hour_moves=[(plan_id, when)]))
    joined = "\n".join(statements)
    for marker in ("insert into activity_preferences", "update shared_plans", "insert into messages"):
        assert marker in joined, (
            f"the priced move never paid `{marker}`: naming another evening writes this half's row, "
            "projects the pair onto the plan, and says in the chat what the tap did. Window:\n"
            f"{joined}"
        )
    lines = [s for s in statements if s.lstrip().startswith("insert into messages")]
    assert len(lines) == 2, (
        "the move wrote a different number of chat lines than the probe measured: an evening the "
        f"pair stood on is ended and a new one is asked about — two lines and 25 statements in "
        f"`s120_shape2.json`. Window:\n{joined}"
    )
    assert [s for s in _writes(statements) if s.lstrip().startswith("delete")] == [], (
        f"the move deleted inside its own window: {joined}"
    )
    after = await _journal(session, plan_id)
    assert len(after) - len(before) == 2, (
        f"the chat of this arrangement grew by {len(after) - len(before)} lines, not two: {after}"
    )
    assert "plan_voided" in after and "plan_rescheduled" in after, (
        f"the two lines are not the ending and the question: {after}"
    )


async def test_the_answer_window_writes_the_agreed_line(
    client: AsyncClient, session: AsyncSession
) -> None:
    _a, ctx = await _stand_pairs(client, "answer")
    plan_id, asked = ctx["hour_questions"][0]
    before = await _journal(session, plan_id)

    statements, _ = await _window(
        session, "plan_hour_confirm", dict(ctx, hour_questions=[(plan_id, asked)])
    )
    joined = "\n".join(statements)
    lines = [s for s in statements if s.lstrip().startswith("insert into messages")]
    assert len(lines) == 1, (
        "the answer did not write exactly one chat line: the evening it agrees to is the one the "
        f"partner named, and the probe counted one `plan_agreed` line and 22 statements. "
        f"Window:\n{joined}"
    )
    assert "update shared_plans" in joined, (
        f"the answer left the plan standing on the hour it just replaced: {joined}"
    )
    after = await _journal(session, plan_id)
    assert after[-1] == "plan_agreed", (
        "the newest line about this arrangement is not the agreement — the first take of "
        f"`s120_shape.py` wrote `plan_voided` here and no agreement at all: {after}"
    )
    assert len(after) > len(before), (
        f"the chat holds no line for a pair that just agreed: {before} against {after}"
    )


async def test_the_priced_card_reads_the_journal_its_own_taps_filled(
    client: AsyncClient, session: AsyncSession
) -> None:
    _a, ctx = await _stand_pairs(client, "card")
    plan_id = ctx["plan_id"]
    card = {"viewer_id": ctx["viewer_id"], "viewer_user": ctx["viewer_user"], "plan_id": plan_id}
    assert await _journal(session, plan_id) == [], (
        "the seed left a chat line on the plan the card addresses: the row stage 119 published was "
        "taken over an empty journal, and this check exists to show what the taps change about it"
    )

    empty, _ = await _window(session, "plan_detail", dict(card))
    statements, _ = await _window(session, "plan_hour", dict(ctx))
    assert len([s for s in statements if s.lstrip().startswith("insert into messages")]) == 2, (
        f"the move that fills the card's journal wrote other than two lines: {statements}"
    )

    filled, _ = await _window(session, "plan_detail", dict(card))
    assert len(filled) > len(empty), (
        "the card costs the same over a journal and over an empty one: stage 119 published 12 "
        f"statements taken with nothing to read, {len(empty)} against {len(filled)} — the row the "
        "table prints has to be the card the pair actually opens"
    )
    assert "from messages" in "\n".join(filled), (
        f"the card read no journal at all over a plan that has lines: {' '.join(filled)[:400]}"
    )


def test_the_published_latency_table_carries_rows_for_both_writes() -> None:
    doc = _SCALE_DOC.read_text(encoding="utf-8")
    assert re.search(r"^### Стадия 120[^\n]*$", doc, re.MULTILINE), (
        "docs/SCALE_PLAN.md has no section for the stage that priced the two writing doors: the "
        "document is where the open end of stage 119 was named, and it has to say what closed it"
    )
    parts = doc.split("## Задержки горячих путей", 1)
    assert len(parts) == 2, "docs/SCALE_PLAN.md no longer carries the hot-path table"
    table = parts[1].split("\n### ", 1)[0]
    for name in WRITING_DOORS:
        row = re.search(rf"^\|\s*`{name}`\s*\|(.+)$", table, re.MULTILINE)
        assert row, (
            f"the harness prices `{name}` but the published table has no row for it — the document "
            "cannot publish a number the instrument does not take"
        )
        cells = [cell.strip() for cell in row.group(1).split("|") if cell.strip()]
        assert len(cells) == 3, f"a latency row carries one cell per scale, this one carries {cells}"
        for cell in cells:
            assert re.fullmatch(r"\d+(?:[.,]\d+)? / \d+(?:[.,]\d+)? / \d+(?:\.\d+)?", cell), (
                f"`{cell}` is not the published shape медиана / максимум / число запросов"
            )
