"""The door stage 112 opened is the one read this repository ships without a price.

`CHANGELOG.md` recorded the gap in its own open end: «Цена и задержка этой двери прибором не
меряны». `docs/SCALE_PLAN.md` carried no row for `GET /api/v1/discover/liked-me`, so the newest
tap-first page of the app had no latency number the way every other hot screen does. The instrument
cannot simply be pointed at the door: its stand seeds passes, matches and messages for the viewer,
and the only `likes` rows it ever writes point *out of* the viewer (the `like` path taps fresh
peers), so a row shot as-is would price an empty inbox — a real page for an account nobody chose,
not the page the screen pays when taps stand behind it.

Six checks, in the order the risk sits:

* the harness has a path for the inbox;
* the path is fed by a setup outside the measured window — and does not build its own crowd inside
  the timed call, the defect stage 42 caught for the deck — because nothing else on the stand ever
  points a tap at the viewer;
* the wrapper calls the handler the API dispatches, the rule stage 76 and stage 77 each had to
  re-learn, and takes the viewer from the context the way the auth dependency hands it over;
* that setup seeds exactly the taps the door will read: showable people get rows, the viewer and
  their already-formed pairs do not;
* the measured window carries the three reads the page pays — taps, cards, leading photos — and
  writes nothing, the same promise `SECURITY.md` makes about the view;
* and the published table carries the row, because a document reporting a number the instrument
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


async def _account(client: AsyncClient, tag: str, *, name: str = "Вера") -> dict:
    creds = await register_and_auth(client, f"s113_{tag}@befos.app")
    await complete_onboarding(client, creds["token"], name=name)
    await answer_all_questions(client, creds["token"])
    return creds


async def _viewer_row(user_id) -> "User":
    """The viewer as `_context()` holds it: read once, outside the measured window."""
    row = None
    async with AsyncSessionLocal() as fresh:
        row = await fresh.get(User, uuid.UUID(str(user_id)))
    assert row is not None, f"no account {user_id} to price the inbox for"
    return row


def test_the_stand_carries_a_path_for_the_inbox() -> None:
    paths = _probe()._build_paths()
    assert "liked_me" in paths, (
        "the hot-path harness has no row for `GET /discover/liked-me`, so the door stage 112 "
        "opened is priced by nobody, while the screen next to it in the same flow — the deck — "
        "has carried a row in the same table since stage 27"
    )


def test_the_inbox_is_fed_outside_the_measured_window() -> None:
    probe = _probe()
    assert "liked_me" in probe._build_setups(), (
        "the stand seeds no tap pointing at the viewer — `_seed_activity` writes passes, matches "
        "and messages, and the `like` path's taps point out of the viewer — so a path with no "
        "setup would publish the price of an empty inbox as the price of the page"
    )
    body = inspect.getsource(probe._build_paths()["liked_me"]).lower()
    assert "insert into likes" not in body, (
        "the inbox path builds its own crowd inside the timed call: stage 42 already caught this "
        f"for the deck, and at 50 000 the seed dwarfs everything the page itself does: {body}"
    )


def test_the_inbox_path_calls_the_handler_the_api_dispatches() -> None:
    from app.api.v1 import discover as discover_module
    from app.main import app

    mounted = [
        route.endpoint
        for route in app.routes
        if getattr(route, "path", "").endswith("/discover/liked-me")
    ]
    assert mounted, "the inbox route is not mounted, so there is nothing for the harness to price"
    assert mounted[0] is discover_module.liked_me, (
        "the mounted endpoint is not the function the harness calls: the published number would "
        "belong to a different handler than the one the app answers with"
    )

    body = inspect.getsource(_probe()._build_paths()["liked_me"])
    assert "liked_me_route(" in body and 'from app.api.v1.discover import liked_me' in body, (
        "the harness prices a copy of the route's steps rather than the route, so a change inside "
        f"the handler moves the product without moving the number: {body}"
    )
    assert 'ctx["viewer_user"]' in body, (
        "the wrapper resolves the reader inside its own window: stage 78 moved this read out — "
        "the dependency hands the row over before the handler runs, and pricing the token's "
        f"owner as part of the screen repeats that mistake: {body}"
    )


async def test_the_setup_seeds_the_taps_the_door_will_read(client: AsyncClient) -> None:
    viewer = await _account(client, "s113_viewer", name="Женя")
    tap_one = await _account(client, "s113_tap1", name="Аня")
    tap_two = await _account(client, "s113_tap2", name="Боря")

    # A formed pair that already tapped: its row is in `likes` before the setup runs, and the
    # door's own rule drops it — the setup must neither reseed it nor count it as readable.
    await client.post(
        f"/api/v1/users/{viewer['user_id']}/like",
        headers=auth_headers(tap_one["token"]),
    )
    paired = await client.post(
        f"/api/v1/users/{tap_one['user_id']}/like",
        headers=auth_headers(viewer["token"]),
    )
    assert paired.status_code == 200, paired.text

    probe = _probe()
    ctx = {"viewer_id": uuid.UUID(viewer["user_id"])}
    async with AsyncSessionLocal() as session:
        await probe._seed_incoming_taps(session, ctx)

    async with AsyncSessionLocal() as session:
        from_ids = set(
            (
                await session.execute(
                    text("SELECT from_user_id FROM likes WHERE to_user_id = :v"),
                    {"v": ctx["viewer_id"]},
                )
            ).scalars()
        )
        scores = (
            await session.execute(
                text(
                    "SELECT compatibility_score, created_at FROM likes "
                    "WHERE to_user_id = :v AND from_user_id = :t"
                ),
                {"v": ctx["viewer_id"], "t": uuid.UUID(tap_two["user_id"])},
            )
        ).all()
    assert uuid.UUID(tap_two["user_id"]) in from_ids, (
        "the setup skipped a showable account: the door would be priced on fewer rows than the "
        "document claims"
    )
    assert uuid.UUID(viewer["user_id"]) not in from_ids, (
        "the setup wrote the viewer a tap on themself — the table's own check forbids it and the "
        "door's conditions would drop it, so the seeded count would lie"
    )
    assert scores and scores[0][0] is not None, (
        "the seeded tap carries no written percent: the page reads `likes.compatibility_score` "
        "as it was stored (defect 72-1), and null-on-every-row would price a cheaper read than "
        "the number-carrying page the screen shows"
    )
    assert len(scores) == 1 and scores[0][1] is not None

    async with AsyncSessionLocal() as session:
        out = await probe._build_paths()["liked_me"](
            session, {"viewer_user": await _viewer_row(viewer["user_id"])}
        )
    named = {card.user_id for card in out.likes}
    assert named == {tap_two["user_id"]}, (
        "the priced page is not the door's page: tap_one is a formed pair and must read as a "
        f"pair, not a tap, and tap_two was seeded for exactly this moment: {named}"
    )
    assert out.has_more is False


async def test_measuring_the_inbox_reads_the_taps_cards_and_photos_writing_nothing(
    client: AsyncClient, session: AsyncSession
) -> None:
    viewer = await _account(client, "s113_window_viewer", name="Женя")
    tapper = await _account(client, "s113_window_tap", name="Аня")
    resp = await client.post(
        f"/api/v1/users/{viewer['user_id']}/like", headers=auth_headers(tapper["token"])
    )
    assert resp.status_code == 200, resp.text

    statements: list[str] = []

    def before(conn, cursor, stmt, parameters, context, executemany):
        statements.append(" ".join(stmt.lower().split()))

    engine = session.sync_session.get_bind()
    event.listen(engine, "before_cursor_execute", before)
    try:
        out = await _probe()._build_paths()["liked_me"](
            session, {"viewer_user": await _viewer_row(viewer["user_id"])}
        )
    finally:
        event.remove(engine, "before_cursor_execute", before)

    assert [card.user_id for card in out.likes] == [tapper["user_id"]]
    reads = "\n".join(statements)
    for marker in ("from likes", "from profiles", "from photos"):
        assert marker in reads, (
            f"the measured call never read `{marker}`, so the published row would price a cheaper "
            f"call than the screen pays. Reads in the window:\n{reads}"
        )
    writes = [s for s in statements if s.lstrip().startswith(("insert", "update", "delete"))]
    assert not writes, (
        "the inbox view wrote inside its own window: `SECURITY.md` promises the view itself "
        f"writes nothing, and a row that prices writes prices a different screen: {writes}"
    )


def test_the_published_latency_table_carries_a_row_for_the_inbox() -> None:
    doc = _SCALE_DOC.read_text(encoding="utf-8")
    parts = doc.split("## Задержки горячих путей", 1)
    assert len(parts) == 2, "docs/SCALE_PLAN.md no longer carries the hot-path table"
    table = parts[1].split("\n### ", 1)[0]
    row = re.search(r"^\|\s*`liked_me`\s*\|(.+)$", table, re.MULTILINE)
    assert row, (
        "the harness prices the inbox but the published table has no row for it: the document is "
        "the half of the rule that turns a run into a claim, and without the row the stage-112 "
        "open end — «Цена и задержка этой двери прибором не меряны» — stays open"
    )
    cells = [cell.strip() for cell in row.group(1).split("|") if cell.strip()]
    assert len(cells) == 3, f"a latency row carries one cell per scale, this one carries {cells}"
    for cell in cells:
        assert re.fullmatch(r"\d+(?:[.,]\d+)? / \d+(?:[.,]\d+)? / \d+(?:\.\d+)?", cell), (
            f"`{cell}` is not the published shape медиана / максимум / число запросов"
        )
