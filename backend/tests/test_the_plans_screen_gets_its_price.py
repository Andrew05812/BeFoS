"""The screen of «Наши планы» has had a route since stage 95 and a card since stage 106, and the
stand has never priced either.

`docs/SCALE_PLAN.md` carries twenty-one rows and `CHANGELOG.md` records the doors that got them: the
deck's read (stage 28), the pair's list (stage 33), the tap (stage 26), the map (stage 76), the
sessions (stage 77), the inbox (stage 113), the passed list and its return (stage 115), the account's
own taps and their withdrawal (stage 117). `backend/app/api/v1/plans.py` mounts fourteen routes and
none of them is among those rows. The probe of this stage's first shoot said why a row could not
simply be written down (`s119_gap.json`): on a stand of 1 000 the harness seeds 400 passes, 20 pairs
of the viewer, 120 messages and 100 pairs of the crowd, and the counters of the plan side come back
`shared_plans = 0`, `shared_plan_members = 0`, `activity_preferences = 0`. Pointed at the door today,
the instrument would publish the price of an empty screen — which it measured at 150.4 мс and 41
statements, because the read is priced in pairs, not in rows: the service walks every pair the viewer
is in and runs the projection once per pair (`PlanService.list_for_viewer`), and no route of this
family has a ceiling.

The same probe measured the other half of the state, and it is the reason this file checks the window
for writes: with the two preference rows of 20 pairs present and no plan rows, the first GET sent 146
statements including `insert into shared_plans` and `update shared_plans` and cost 632.1 мс — the
screen writes the arrangement it is showing. A row published over that window would be the price of a
first open, not the price of the screen, and the table has always published screens.

Ten checks, in the order the risk sits:

* the harness has a path for the screen and a path for its card, and each owns a setup besides its
  row — the rule stage 113 and stage 117 each had to learn twice;
* both wrappers call the handlers the route dispatches and take the reader from the context, the way
  `get_current_user` hands it over (stage 76, stage 77);
* the seed writes the rows a pair actually leaves behind: the idea named by one half and agreed to by
  the other, the plan, and the two answer rows — not a plan nobody proposed;
* the seed stops at the arrangements its pairs already hold, so its second call of a scale writes
  nothing (the rule stage 118 put on the tap seed);
* the priced screen names only the plans of the viewer's own pairs;
* the priced card answers the plan it was addressed by, and the address is taken outside the window;
* the measured window of the screen carries the projection's three reads per pair and writes nothing,
  because the row published is the steady open, not the first one;
* the measured window of the card carries its own plan once and its journal once;
* and the published table carries both rows, because a document reporting a number the instrument
  cannot reproduce is the defect stage 72-9 already caught in the release checklist.
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

from .test_a_pair_can_agree_on_when_to_meet import (
    _accept,
    _offer,
    _page,
    _pair,
    _ready,
    _send,
    _whole_hour,
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


async def _viewer_row(user_id: str) -> User:
    async with AsyncSessionLocal() as session:
        return await session.get(User, uuid.UUID(user_id))


def _ctx(viewer: dict, **extra) -> dict:
    return {"viewer_id": uuid.UUID(viewer["user_id"]), "viewer_user": None, **extra}


async def _count(session: AsyncSession, table: str, viewer: dict) -> int:
    """Rows of this viewer's pairs: the plan table hangs off the pair, its answers off the plan."""
    if table == "shared_plan_members":
        return await session.scalar(
            text(
                "SELECT count(*) FROM shared_plan_members sm JOIN shared_plans p ON p.id = sm.plan_id "
                "JOIN matches m ON m.id = p.match_id WHERE m.user_a_id = :v OR m.user_b_id = :v"
            ),
            {"v": uuid.UUID(viewer["user_id"])},
        )
    return await session.scalar(
        text(
            f"SELECT count(*) FROM {table} p JOIN matches m ON m.id = p.match_id "
            "WHERE m.user_a_id = :v OR m.user_b_id = :v"
        ),
        {"v": uuid.UUID(viewer["user_id"])},
    )


async def _seed(viewer: dict, ctx: dict | None = None) -> dict:
    """Run the harness's own setup for the screen, against the viewer's live pairs."""
    ctx = ctx or _ctx(viewer)
    ctx["viewer_user"] = await _viewer_row(viewer["user_id"])
    async with AsyncSessionLocal() as session:
        await _probe()._build_setups()["plans"](session, ctx)
    return ctx


async def _pair_with_one_arrangement(client: AsyncClient, tag: str) -> tuple[dict, dict, str, int]:
    """Two accounts, one pair, and one idea the pair has taken up with an hour they both stand on."""
    a = await _ready(client, f"s119_{tag}_a@befos.app", "Аня")
    b = await _ready(client, f"s119_{tag}_b@befos.app", "Боря")
    match_id = await _pair(client, a, b)
    cards = await _page(client, a["token"], match_id, force=True)
    idea = cards[0]["activity"]["id"]
    assert await _send(client, a["token"], match_id, idea) in (200, 204)
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204
    return a, b, match_id, idea


def test_the_harness_has_a_path_for_the_screen_and_one_for_its_card() -> None:
    paths = _probe()._build_paths()
    for name in ("plans", "plan_detail"):
        assert name in paths, (
            f"the harness prices {len(paths)} paths and `{name}` is not one of them: the screen of "
            "«Наши планы» and its card have been reachable since stage 95 and stage 106, and the "
            "latency table has never named either"
        )


def test_both_plan_doors_own_a_setup_besides_their_row() -> None:
    setups = _probe()._build_setups()
    for name in ("plans", "plan_detail"):
        assert name in setups, (
            f"`{name}` has a row and no preparation: the stand writes no `shared_plans`, no "
            "`shared_plan_members` and no `activity_preferences` rows at all (`s119_gap.json` counts "
            "0 / 0 / 0 on a scale of 1 000), so its row would price the empty screen the probe "
            "measured at 150.4 мс rather than the page the app shows"
        )


def test_the_plan_wrappers_call_the_dispatched_handlers() -> None:
    paths = _probe()._build_paths()
    screen = inspect.getsource(paths["plans"])
    assert "from app.api.v1.plans import list_plans as list_plans_route" in screen, (
        "the `plans` row prices a private re-assembly of the service steps instead of the handler "
        f"the route dispatches: {screen}"
    )
    assert 'current_user=ctx["viewer_user"]' in screen, (
        "the screen's wrapper resolves its reader inside its own window: stage 76 and stage 77 each "
        f"published a number that belonged to the auth dependency: {screen}"
    )
    card = inspect.getsource(paths["plan_detail"])
    assert "from app.api.v1.plans import get_plan as get_plan_route" in card, (
        f"the `plan_detail` row does not open the card the route opens: {card}"
    )
    assert 'ctx["plan_id"]' in card, (
        "the card takes its plan id from somewhere inside the measured call: the address belongs to "
        f"the setup, outside the window, the way `unlike` takes its pool: {card}"
    )


def test_the_seed_writes_the_rows_a_pair_actually_leaves_behind() -> None:
    source = inspect.getsource(_probe()._build_setups()["plans"])
    for marker in (
        "INSERT INTO activity_preferences",
        "INSERT INTO shared_plans",
        "INSERT INTO shared_plan_members",
    ):
        assert marker in source, (
            f"the seed of the plan screen writes no `{marker}`, so the priced page is not the page "
            f"the pair leaves behind after two taps: {source[:400]}"
        )
    assert "meeting_time" in source and "accepted_time" in source, (
        "the seeded hour is not an agreement: the arrangement a pair stands on is one row naming "
        "the instant and the other row accepting exactly that instant — `agreed_instant` answers "
        f"nothing to two rows that each only named one: {source[:400]}"
    )
    assert re.search(r"WHERE NOT EXISTS \(\s*SELECT 1 FROM shared_plans", source), (
        "the seed writes a plan beside a plan the pair already has: `uq_shared_plan_pair_activity` "
        "makes the second an error and the first open of the screen would then be priced over a "
        f"state the product cannot reach: {source[:400]}"
    )


async def test_the_second_call_of_the_seed_writes_no_new_rows(client: AsyncClient) -> None:
    a, _b, _match_id, _idea = await _pair_with_one_arrangement(client, "twice")
    ctx = await _seed(a)
    async with AsyncSessionLocal() as session:
        plans = await _count(session, "shared_plans", a)
        members = await _count(session, "shared_plan_members", a)
    assert plans > 0, "the seed wrote no arrangement for a pair the viewer is in"

    again = await _seed(a, ctx)
    async with AsyncSessionLocal() as session:
        assert await _count(session, "shared_plans", a) == plans, (
            "the second call of one scale wrote a fresh page of arrangements on top of the first, "
            "which is the defect stage 118 closed on the tap seed: two rows of one door pair would "
            f"price two page lengths — first call left {plans} plans"
        )
        assert await _count(session, "shared_plan_members", a) == members, (
            "the answers of the pair doubled while the plans did not: every plan owes exactly two "
            f"member rows, one per half — expected {members}, the second call left "
            f"{await _count(session, 'shared_plan_members', a)}"
        )
    assert again["plan_id"] is not None, "the card door has no address after the seed"


async def test_the_priced_screen_reads_only_the_viewers_own_plans(client: AsyncClient) -> None:
    a, _b, match_id, _idea = await _pair_with_one_arrangement(client, "mine")
    other = await _ready(client, "s119_mine_other@befos.app", "Оля")
    third = await _ready(client, "s119_mine_third@befos.app", "Пётр")
    other_match = await _pair(client, other, third)
    cards = await _page(client, other["token"], other_match, force=True)
    assert await _send(client, other["token"], other_match, cards[0]["activity"]["id"]) in (200, 204)
    ctx = await _seed(a)

    async with AsyncSessionLocal() as session:
        out = await _probe()._build_paths()["plans"](session, ctx)
    ids = {plan.match_id for plan in out.plans}
    assert ids, "the priced screen came back with no plan over a stand the seed just arranged"
    assert other_match not in ids, (
        "the priced screen read a pair the viewer is not in: the address of this door is the "
        f"viewer's own list of pairs, not the plan table: {ids}"
    )
    assert match_id in ids, (
        f"the pair the seed was asked for is missing from its own page: {ids}"
    )


async def test_the_priced_card_answers_the_plan_it_was_addressed_by(client: AsyncClient) -> None:
    a, _b, match_id, _idea = await _pair_with_one_arrangement(client, "card")
    ctx = await _seed(a)
    plan_id = ctx["plan_id"]

    async with AsyncSessionLocal() as session:
        out = await _probe()._build_paths()["plan_detail"](session, ctx)
    assert out.plan.id == str(plan_id), (
        "the card opened a plan other than the one it was addressed by — the price published would "
        f"belong to a different read: {out.plan.id} against {plan_id}"
    )
    assert out.plan.match_id == match_id, (
        f"the card's plan belongs to another pair than the reader's: {out.plan.match_id}"
    )

    async with AsyncSessionLocal() as session:
        rows = list((await session.execute(
            text(
                "SELECT p.id FROM shared_plans p JOIN matches m ON m.id = p.match_id "
                "WHERE p.id <> :p AND (m.user_a_id = :v OR m.user_b_id = :v) LIMIT 1"
            ),
            {"p": plan_id, "v": uuid.UUID(a["user_id"])},
        )).scalars())
    if rows:
        other_ctx = dict(ctx, plan_id=rows[0])
        async with AsyncSessionLocal() as session:
            second = await _probe()._build_paths()["plan_detail"](session, other_ctx)
        assert second.plan.id == str(rows[0]), (
            "the card ignores the id it was given and re-opens the newest plan: the address is part "
            "of the measured door"
        )


async def test_the_screen_window_carries_the_projection_and_writes_nothing(
    client: AsyncClient, session: AsyncSession
) -> None:
    a, _b, _match_id, _idea = await _pair_with_one_arrangement(client, "window")
    ctx = await _seed(a)

    statements: list[str] = []

    def before(conn, cursor, stmt, parameters, context, executemany):
        statements.append(" ".join(stmt.lower().split()))

    engine = session.sync_session.get_bind()
    event.listen(engine, "before_cursor_execute", before)
    try:
        out = await _probe()._build_paths()["plans"](session, ctx)
    finally:
        event.remove(engine, "before_cursor_execute", before)

    joined = "\n".join(statements)
    for marker in ("from activity_preferences", "from shared_plans", "from shared_plan_members"):
        assert marker in joined, (
            f"the measured screen never paid `{marker}`, so its row prices a page the pair's "
            f"projection does not read. Statements in the window:\n{joined}"
        )
    assert out.plans, "the priced screen answered empty over a stand the seed arranged"
    writes = [s for s in statements if s.lstrip().startswith(("insert", "update", "delete"))]
    assert not writes, (
        "the priced screen writes inside its own window: with a plan row per pair already standing, "
        "the projection has nothing to add, and the first open — which does write, 146 statements "
        "and 632.1 мс in `s119_gap.json` — is not the row the table publishes. Writes in the "
        f"window:\n{writes}"
    )
    pairs = await session.scalar(
        text("SELECT count(*) FROM matches WHERE user_a_id = :v OR user_b_id = :v"),
        {"v": uuid.UUID(a["user_id"])},
    )
    projection = [s for s in statements if "from activity_preferences" in s]
    assert len(projection) == pairs, (
        "the screen reads the pair's rows a number of times other than its pairs: the projection is "
        f"asked once per pair, which is the shape this row exists to publish — {pairs} pairs, "
        f"{len(projection)} reads"
    )


async def test_the_card_window_reads_its_plan_once_and_its_journal_once(
    client: AsyncClient, session: AsyncSession
) -> None:
    a, _b, _match_id, _idea = await _pair_with_one_arrangement(client, "cardwindow")
    ctx = await _seed(a)

    statements: list[str] = []

    def before(conn, cursor, stmt, parameters, context, executemany):
        statements.append(" ".join(stmt.lower().split()))

    engine = session.sync_session.get_bind()
    event.listen(engine, "before_cursor_execute", before)
    try:
        out = await _probe()._build_paths()["plan_detail"](session, ctx)
    finally:
        event.remove(engine, "before_cursor_execute", before)

    joined = "\n".join(statements)
    for marker in ("from shared_plans", "from shared_plan_members", "from messages", "from profiles"):
        assert marker in joined, (
            f"the measured card never paid `{marker}`: the detail is the plan, this person's own "
            f"remark, the partner's card and the history the chat holds. Statements:\n{joined}"
        )
    plans_read = [s for s in statements if "from shared_plans" in s]
    assert len(plans_read) <= 3, (
        "the card read the plan table more than three times: it is addressed by one id, opened once, "
        f"and projected for the pair it belongs to — {len(plans_read)} reads of `shared_plans`"
    )
    assert not [s for s in statements if s.lstrip().startswith(("insert", "update", "delete"))], (
        "the card wrote inside its own window: " + "\n".join(statements)
    )
    assert out.plan.id == str(ctx["plan_id"])


def test_the_published_latency_table_carries_rows_for_both_doors() -> None:
    doc = _SCALE_DOC.read_text(encoding="utf-8")
    parts = doc.split("## Задержки горячих путей", 1)
    assert len(parts) == 2, "docs/SCALE_PLAN.md no longer carries the hot-path table"
    table = parts[1].split("\n### ", 1)[0]
    for name in ("plans", "plan_detail"):
        row = re.search(rf"^\|\s*`{name}`\s*\|(.+)$", table, re.MULTILINE)
        assert row, (
            f"the harness prices `{name}` but the published table has no row for it: the document is "
            "the half of the rule that turns a run into a claim, and stage 72-9 already caught a "
            "checklist that expected a number the instrument could not reproduce"
        )
        cells = [cell.strip() for cell in row.group(1).split("|") if cell.strip()]
        assert len(cells) == 3, f"a latency row carries one cell per scale, this one carries {cells}"
        for cell in cells:
            assert re.fullmatch(r"\d+(?:[.,]\d+)? / \d+(?:[.,]\d+)? / \d+(?:\.\d+)?", cell), (
                f"`{cell}` is not the published shape медиана / максимум / число запросов"
            )
