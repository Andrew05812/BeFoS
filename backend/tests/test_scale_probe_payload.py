"""The stand must not time the read it performs to build the request it times.

`backend/ops/scale_probe.py` runs each path's wrapper inside the measured window and counts every
statement that window sends, so the row describes what the wrapper did, not what the screen does.
`answers_submit` assembled its own payload there: it read the whole catalogue with
`TestRepository.list_active_questions()` and posted one answer per question. A client does not pay
for that read — it fetched the catalogue one screen earlier from `GET /api/v1/tests`, and the
submission route reads back only the questions its body names. Measured 2026-10-09 on the 50 000
stand with a capture grouped by statement text and parameters, the path sent
`SELECT test_options.… WHERE test_options.question_id IN ($1, …, $21)` twice inside one call: once
as the harness's own catalogue read, once as the request's, and the published row said 13 statements
per call for a request that costs 11.

Stage 42 moved the stand's own `INSERT` out of the measured window for the exhausted deck. This is
the same defect class on a different path: preparation that belongs beside `_build_setups()`.
"""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
import uuid
from collections import Counter
from pathlib import Path
from typing import Iterator

from httpx import AsyncClient
import pytest
from sqlalchemy import event

from app.core.database import AsyncSessionLocal, engine
from app.core.exceptions import NotFoundError
from app.repositories.test_repo import TestRepository
from app.services.match_service import MatchService
from app.services.test_service import TestService

from .conftest import auth_headers, complete_onboarding, register_and_auth

_PROBE_PATH = Path(__file__).resolve().parents[1] / "ops" / "scale_probe.py"


def _probe():
    """Load the stand as a module: it is a script, so it is not on the import path."""
    spec = importlib.util.spec_from_file_location("scale_probe", _PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalize(statement: str) -> str:
    return " ".join(statement.split())


@contextlib.contextmanager
def _listening() -> Iterator[list[str]]:
    """Every statement the block sends, in the order it sends it."""
    seen: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _record)
    try:
        yield seen
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _record)


async def _payload() -> list[dict]:
    """The body a client sends after it has seen the catalogue: ids, not a fresh read."""
    async with AsyncSessionLocal() as session:
        catalog = await TestRepository(session).list_active_questions()
    return [{"question_id": q.id, "option_id": q.options[0].id} for q in catalog]


def test_no_measured_path_reads_the_catalogue_the_client_already_holds() -> None:
    """A wrapper that reads the catalogue itself puts a screen's work into another screen's row."""
    probe = _probe()
    offenders = [
        name
        for name, wrapper in probe._build_paths().items()
        if "list_active_questions" in inspect.getsource(wrapper)
    ]
    assert not offenders, (
        f"{offenders} reads the question catalogue inside the call the stand times: the client "
        "posted ids it had taken from `GET /api/v1/tests`, so those statements are the harness's "
        "own and they inflate the path's row (13 запросов за вызов against the 11 the route pays)"
    )


def test_the_payload_is_prepared_outside_the_measured_window() -> None:
    """The catalogue read belongs in the setup registry, where the timing loop calls it early."""
    probe = _probe()
    assert "answers_submit" in probe._build_setups(), (
        "answers_submit has no setup, so the read that assembles its body still runs inside the "
        "window the stand measures and captures"
    )


async def test_the_setup_hands_the_path_a_whole_map_of_answers(session) -> None:
    probe = _probe()
    ctx: dict = {}
    await probe._answer_payload(session, ctx)
    catalog = await TestRepository(session).list_active_questions()
    expected = [{"question_id": q.id, "option_id": q.options[0].id} for q in catalog]
    assert ctx["answer_rows"] == expected, (
        "the payload the stand submits is not one answer per active question, so the path times a "
        "submission the screen never sends"
    )


async def test_the_timed_call_sends_the_statements_the_request_sends(client: AsyncClient) -> None:
    creds = await register_and_auth(client, "s44_viewer@befos.app")
    await complete_onboarding(client, creds["token"], name="Нина", gender="female")
    viewer = uuid.UUID(creds["user_id"])
    ctx = {"viewer_id": viewer, "answer_rows": await _payload()}
    probe = _probe()

    with _listening() as during_probe:
        async with AsyncSessionLocal() as session:
            await probe._build_paths()["answers_submit"](session, ctx)
            await session.commit()

    with _listening() as during_request:
        async with AsyncSessionLocal() as session:
            await TestService(session).save_answers(viewer, ctx["answer_rows"])

    probe_calls = Counter(_normalize(statement) for statement in during_probe)
    request_calls = Counter(_normalize(statement) for statement in during_request)
    extra = probe_calls - request_calls
    assert not extra, (
        f"the timed call sends {sum(extra.values())} statement(s) the submission route does not: "
        f"{[sql[:110] for sql in extra]}. The row the stand publishes for this path is the price "
        "of that read as well, and no client pays it"
    )
    assert len(during_probe) == len(during_request), (
        f"{len(during_probe)} запросов за вызов against the {len(during_request)} the route sends"
    )


async def test_the_likes_two_block_reads_have_two_different_jobs(client: AsyncClient) -> None:
    """The other repeat the same sweep found is deliberate, and this check is what keeps it that way.

    `like` asks `is_blocked_either` twice with one and the same parameters inside one call. The
    first ask answers before the pair lock, so a like aimed at somebody who blocked the viewer
    refuses without ever taking it; the second is the re-read under `pg_advisory_xact_lock` that
    stage 13 holds against a block committing while the like waited. Removing either half of the
    pair to satisfy the sweep would remove one of those two guarantees, so this file names the
    difference instead of folding the case: a blocked pair sends no lock statement at all.
    """
    viewer = await register_and_auth(client, "s44_liker@befos.app")
    await complete_onboarding(client, viewer["token"], name="Нина", gender="female")
    peer = await register_and_auth(client, "s44_liked@befos.app")
    await complete_onboarding(client, peer["token"], name="Пётр", gender="male")

    blocked = await client.post(
        f"/api/v1/users/{peer['user_id']}/block", headers=auth_headers(viewer["token"])
    )
    assert blocked.status_code == 200, blocked.text

    with _listening() as seen:
        with pytest.raises(NotFoundError):
            async with AsyncSessionLocal() as session:
                await MatchService(session).like(
                    uuid.UUID(viewer["user_id"]), uuid.UUID(peer["user_id"])
                )

    locks = [statement for statement in seen if "pg_advisory_xact_lock" in statement]
    assert not locks, (
        f"the refusal let {len(locks)} pair lock(s) through for a blocked target: the first block "
        "read exists so a like aimed outside the deck never queues on that lock"
    )
