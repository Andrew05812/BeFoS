"""The map a pair opens by tap is the one screen of the pair's flow this repository never priced.

`docs/SCALE_PLAN.md` §«Задержки горячих путей» publishes a row per hot path — медиана / максимум /
число запросов за вызов — and since stage 74 the screen «Открыть карту пары» reads
`GET /api/v1/matches/{match_id}/universe` on every open. That route is not a thin wrapper: it reads
the match to check membership, loads both profiles and both answer vectors through
`CompatibilityService.pair_inputs`, scores the pair, assembles seven layers of nodes, reads the
interest catalogue to title them, and builds the `UniverseOut`. Stage 75 recorded the consequence in
the changelog: «задержка и число round-trip'ов у `/universe` не измерены», and the hot-path table
carried no row for it.

An unpriced route is where a screen quietly grows. The map recomputes the whole engine per open, and
whether that costs tens of milliseconds or the several hundred that `login` costs is only knowable on
the same stand the other thirteen rows came from.

Six checks, in the order the risk sits:

* the harness has a path for the map;
* that path calls the handler the API dispatches, not a re-assembly of the steps its author believed
  the route takes — stage 75 is the argument, because the explanation line changed inside the handler
  and a copied harness would have gone on pricing yesterday's route with today's number;
* the membership check is inside the measured window, so the row describes the call a member pays and
  a stranger's call is not silently cheaper;
* the window really carries the reads the screen pays for — the match, both profiles, both answer
  vectors and the interest titles;
* the published table carries the row, because a document reporting a number the instrument cannot
  reproduce is the defect stage 72-9 already caught in the release checklist;
* and the table describes the sampling it was shot with: stage 76 re-derived all thirty-nine cells of
  the stage-67 table from that run's own artifact and every one of them equalled the warmed
  `median_ms` / `max_ms`, while the caption above them promised a sample that folded the first call
  back in — a sentence about the instrument that the instrument contradicts, so it is now checked
  against the section rather than trusted.
"""

from __future__ import annotations

import importlib.util
import inspect
import pathlib
import re
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

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


def test_the_stand_carries_a_path_for_the_pair_map() -> None:
    paths = _probe()._build_paths()
    assert "universe_map" in paths, (
        "the hot-path harness has no row for `GET /matches/{match_id}/universe`, so the map a pair "
        "opens by tap is priced by nobody, while the screen next to it in the same flow — "
        "compatibility — has carried a row in the same table"
    )


def test_the_map_path_calls_the_handler_the_api_dispatches() -> None:
    from app.api.v1.matches import match_universe
    from app.main import app

    mounted = [
        route.endpoint
        for route in app.routes
        if getattr(route, "path", "").endswith("/matches/{match_id}/universe")
    ]
    assert mounted, "the map route is not mounted, so there is nothing for the harness to price"
    assert mounted[0] is match_universe, (
        "the mounted endpoint is not the function the harness calls: the published number would "
        "belong to a different handler than the one the app answers with"
    )

    body = inspect.getsource(_probe()._build_paths()["universe_map"])
    assert "match_universe(" in body, (
        "the harness prices a copy of the route's steps rather than the route, so a change inside "
        f"the handler moves the product without moving the number: {body}"
    )


async def _pair(client: AsyncClient) -> tuple[uuid.UUID, uuid.UUID]:
    """A real pair on this database: the map is only readable by the two people in it."""
    anya = await register_and_auth(client, "price_a@befos.app")
    await complete_onboarding(client, anya["token"], name="Аня", gender="female",
                              goal="relationship", interests=None)
    borya = await register_and_auth(client, "price_b@befos.app")
    await complete_onboarding(client, borya["token"], name="Боря", gender="male",
                              goal="relationship", interests=None)
    await answer_all_questions(client, anya["token"])
    await answer_all_questions(client, borya["token"])
    await client.post(f"/api/v1/users/{borya['user_id']}/like", json={},
                      headers=auth_headers(anya["token"]))
    back = await client.post(f"/api/v1/users/{anya['user_id']}/like", json={},
                             headers=auth_headers(borya["token"]))
    assert back.status_code == 200, back.text
    return uuid.UUID(back.json()["match_id"]), uuid.UUID(anya["user_id"])


async def _viewer_row(user_id) -> "User":
    """The viewer as `_context()` holds it: read once, outside the measured window, then detached.

    Stage 78 moved this read out of the harness's call: on the wire `get_current_user` resolves the
    account from the token before the handler runs, so the wrapper prices the handler and is handed
    the row the dependency would have handed over. A test that gives the wrapper no such row is not
    testing the harness's contract — it is testing a context the stand never builds.
    """
    from app.core.database import AsyncSessionLocal
    from app.models import User

    async with AsyncSessionLocal() as fresh:
        row = await fresh.get(User, uuid.UUID(str(user_id)))
    assert row is not None, f"no account {user_id} to price the map for"
    return row


async def test_measuring_the_map_sends_the_reads_the_screen_pays(client: AsyncClient,
                                                                 session: AsyncSession) -> None:
    """The measured window carries the match check, both profiles, both vectors and the titles."""
    match_id, viewer = await _pair(client)
    viewer_user = await _viewer_row(viewer)
    statements: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip()[:1].lower() in ("s", "w"):
            statements.append(" ".join(statement.split()))

    engine = session.sync_session.get_bind()
    event.listen(engine, "before_cursor_execute", before)
    try:
        out = await _probe()._build_paths()["universe_map"](
            session, {"match_id": match_id, "viewer_id": viewer, "viewer_user": viewer_user}
        )
    finally:
        event.remove(engine, "before_cursor_execute", before)

    assert out.layers, "the measured call returned a map with nothing to draw"
    assert out.a_user_id == str(viewer) or out.b_user_id == str(viewer), (
        "the map the harness measured is not the pair the harness asked about"
    )
    reads = "\n".join(statements)
    for table in ("matches", "profiles", "compatibility_profiles", "interests"):
        assert table in reads, (
            f"the measured call never read `{table}`, so the published row would price a cheaper "
            f"call than the screen pays. Reads in the window:\n{reads}"
        )


async def test_the_membership_check_sits_inside_the_measured_window(client: AsyncClient,
                                                                   session: AsyncSession) -> None:
    """A stranger cannot be priced as if the pair's guard had not run."""
    from app.core.exceptions import NotFoundError

    match_id, _ = await _pair(client)
    stranger = await register_and_auth(client, "price_c@befos.app")
    await complete_onboarding(client, stranger["token"], name="Вера", gender="female",
                              goal="relationship", interests=None)

    with pytest.raises(NotFoundError):
        await _probe()._build_paths()["universe_map"](
            session,
            {
                "match_id": match_id,
                "viewer_id": uuid.UUID(stranger["user_id"]),
                "viewer_user": await _viewer_row(stranger["user_id"]),
            },
        )


def test_the_published_latency_table_carries_a_row_for_the_map() -> None:
    doc = _SCALE_DOC.read_text(encoding="utf-8")
    parts = doc.split("## Задержки горячих путей", 1)
    assert len(parts) == 2, "docs/SCALE_PLAN.md no longer carries the hot-path table"
    table = parts[1].split("\n### ", 1)[0]
    row = re.search(r"^\|\s*`universe_map`\s*\|(.+)$", table, re.MULTILINE)
    assert row, (
        "the harness prices the map but the published table has no row for it: the document is the "
        "half of the rule that turns a run into a claim, and without the row the claim this stage "
        "exists to make — that opening the map costs a measurable, known amount — is still missing"
    )
    cells = [cell.strip() for cell in row.group(1).split("|") if cell.strip()]
    assert len(cells) == 3, f"a latency row carries one cell per scale, this one carries {cells}"
    for cell in cells:
        assert re.fullmatch(r"\d+(?:[.,]\d+)? / \d+(?:[.,]\d+)? / \d+(?:\.\d+)?", cell), (
            f"`{cell}` is not the published shape медиана / максимум / число запросов"
        )


def test_the_table_promises_the_sampling_the_instrument_implements() -> None:
    """Раздел о задержках описывает прогретую выборку, потому что `_row` отдаёт прогретую выборку."""
    raw = _SCALE_DOC.read_text(encoding="utf-8").split("## Задержки горячих путей", 1)[1]
    section = " ".join(raw.split("\n## ", 1)[0].split())

    for lie in ("включая первый замеряемый вызов", "складывает первый вызов"):
        assert lie not in section, (
            f"раздел утверждает `{lie}`, тогда как `_row` считает медиану и максимум по прогретым "
            "повторам и отдаёт первый вызов отдельным числом — это проверено пересчётом всех 39 "
            "ячеек таблицы стадии 67 по её артефакту s67_full_3scales.json: каждая сошлась с "
            "median_ms / max_ms прогона. Правило как поведение прибора держит "
            "test_scale_probe_sampling.py; здесь держится то, что документ о нём говорит."
        )
    assert "первый замеряемый вызов публикуется отдельным числом" in section, (
        "преамбула к таблице больше не называет правило агрегирования, и следующая пересъёмка "
        "сможет опубликовать смешанную выборку под видом прогретой, не будя ни одной проверки"
    )
