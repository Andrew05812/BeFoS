"""The scale stand must not time the setup that prepares it.

`backend/ops/scale_probe.py` times each path several times and reports the median of the repeats
that came after the first call. The exhausted-deck path built its own stand inside the first of
those calls: an `INSERT … SELECT` writing a queue row
for every account on the stand and marking it seen. Measured on 2026-10-09 at 50 000 profiles that
path reported `медиана 11426.8 мс, max 54852.6 мс`, while the `INSERT` alone measured 11 327.9 ms
and the same call, taken once the stand was quiet again, cost 95.5…99.1 ms over seven statements.
The published number described the setup rather than the screen, and the trigger built on it
(`>1500 мс` for this path in `docs/SCALE_PLAN.md`) could only ever be crossed by the drain growing,
never by the page getting slower.

These checks hold both halves of the separation: the stand's setup lives in a registry the timing
loop calls outside the measured window, and the measured call of an exhausted deck writes nothing.
"""

from __future__ import annotations

import importlib.util
import inspect
import uuid
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import event, text

from app.core.database import AsyncSessionLocal, engine
from app.repositories.social_repo import DiscoveryRepository

from .conftest import answer_all_questions, complete_onboarding, register_and_auth

_PROBE_PATH = Path(__file__).resolve().parents[1] / "ops" / "scale_probe.py"


def _probe():
    """Load the stand as a module: it is a script, so it is not on the import path."""
    spec = importlib.util.spec_from_file_location("scale_probe", _PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _account(client: AsyncClient, email: str, *, name: str, gender: str) -> uuid.UUID:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return uuid.UUID(creds["user_id"])


def _write_statements(seen: list[str]) -> list[str]:
    return [
        statement
        for statement in seen
        if statement.lstrip().lower().startswith(("insert", "update", "delete"))
    ]


def test_no_measured_path_builds_the_stand_it_is_measured_on() -> None:
    """A path that prepares its own state puts that preparation inside the timed window."""
    probe = _probe()
    offenders = [
        name
        for name, wrapper in probe._build_paths().items()
        if "insert into discovery_queue" in inspect.getsource(wrapper).lower()
    ]
    assert not offenders, (
        f"{offenders} assembles its queue inside the call the probe times: at 50 000 profiles "
        "the drain alone measured 11 327.9 ms, so the path's median is that INSERT and not the "
        "page (11426.8 мс against 95.5…99.1 мс once the stand is quiet)"
    )


def test_every_setup_belong_to_a_measured_path() -> None:
    probe = _probe()
    paths = probe._build_paths()
    setups = probe._build_setups()
    assert set(setups) <= set(paths), f"setup for a path the stand does not time: {set(setups) - set(paths)}"
    assert "deck_exhausted" in setups, "the exhausted deck needs its queue written before timing"


async def test_the_setup_leaves_the_deck_with_nothing_ready(client: AsyncClient) -> None:
    viewer = await _account(client, "s42_viewer@befos.app", name="Вера", gender="female")
    peer = await _account(client, "s42_peer@befos.app", name="Пётр", gender="male")
    probe = _probe()
    ctx = {"viewer_id": viewer}

    async with AsyncSessionLocal() as session:
        assert await DiscoveryRepository(session).deck_ready_count(viewer, cap=200) == 0
        await probe._drain_deck(session, ctx)

    async with AsyncSessionLocal() as session:
        assert await DiscoveryRepository(session).deck_ready_count(viewer, cap=200) == 0
        rows = (
            await session.execute(
                text("SELECT candidate_id, status FROM discovery_queue WHERE viewer_id = :viewer"),
                {"viewer": viewer},
            )
        ).all()
    assert {row[0] for row in rows} == {peer}, "the drain queues everyone but the viewer"
    assert {row[1] for row in rows} == {"seen"}, "a ready row left behind is a card the page could show"


async def test_the_measured_call_of_an_exhausted_deck_writes_nothing(client: AsyncClient) -> None:
    viewer = await _account(client, "s42_viewer2@befos.app", name="Вера", gender="female")
    await _account(client, "s42_peer2@befos.app", name="Пётр", gender="male")
    probe = _probe()
    ctx = {"viewer_id": viewer}

    async with AsyncSessionLocal() as session:
        await probe._drain_deck(session, ctx)

    seen: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    try:
        async with AsyncSessionLocal() as session:
            await probe._build_paths()["deck_exhausted"](session, ctx)
            await session.commit()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)

    writes = _write_statements(seen)
    assert not writes, (
        "the page the stand times for an exhausted deck still writes: "
        f"{[w[:80] for w in writes]} — that write is setup, and it belongs in `_build_setups()`"
    )
