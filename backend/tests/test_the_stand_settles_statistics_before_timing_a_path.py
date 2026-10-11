"""The stand has to plan its timing against statistics that count the rows its setup wrote.

`backend/ops/scale_probe.py` writes the hot-path latency table in `docs/SCALE_PLAN.md`, and a
row of that table is read as what one call of the path costs. The `deck_exhausted` path prepares its
own state before being timed: the drain gives the viewer a queue row for every other account on the
stand. That preparation was taken out of the measured window in stage 42, but the run's only `ANALYZE`
still sat before it — right after the population was seeded — so the planner chose the widest read of
the product's page from a `pg_class.reltuples` of zero over a table holding fifty thousand rows.

Measured on a freshly built `befos_s67fresh` (50 000 profiles, 20 000 viewer passes, run
16:31:49…16:34:13 UTC): `deck_exhausted` median 323.4 ms, worst read 317.5 ms, 223 169 shared-buffer
hits, an `Index Only Scan` of the queue run 30 000 times; read straight after the run the table held
`reltuples = 0`, `relpages = 0`, with `last_analyze` 16:33:55 against a queue written at 16:34:0x, and
the server's own autoanalyze reaching it only at 16:34:54 — after every published number. The same
statement text with the same parameters, on a queue that had been counted, cost 68.1…76.5 ms with
1 760 hits and a hash anti join, and the whole call 102.2 ms. The one thing separating the two
states is the moment the stand reconciles its statistics with its rows. Re-run end to end after the
fix (16:41:22…16:43:48 UTC) on the same stand: `deck_exhausted` first 159.7 / median 107.2 / max
108.3 ms over 7 reads per call, `discovery_rebuild` 118.2 / 108.7 / 109.2 ms; worst reads 81.73 and
74.32 ms, 1 766 and 1 760 hits, and the scan is a `Seq Scan profiles` of 50 000 rows in one loop at
31.12 and 26.91 ms instead of 120.0 ms across 30 000 loops of the queue.

Three checks hold the separation: the settle step sits in the timing loop after the path's setup and
before the timed calls; `ANALYZE` is executed exactly once in the harness and lives in that one step,
because a second one can only be mistimed; and after the settle step the planner's row estimate equals
the rows the setup really wrote. The witness is `pg_class.reltuples` rather than `n_mod_since_analyze`,
because the latter was measured reporting the writer's delta *after* the reset — on `befos_test`, a
table holding one queue row still showed `n_mod_since_analyze = 1` and `n_live_tup = 2` immediately
after `ANALYZE`, while `n_tup_ins` had not moved at all even though the reconciliation had already
counted the row. The estimate in `pg_class` is what the planner reads to pick a plan, so the defect
shows up in it.
"""

from __future__ import annotations

import importlib.util
import inspect
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg
from httpx import AsyncClient
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal

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


async def _queue_estimate() -> tuple[float, int]:
    """What the planner believes about `discovery_queue`, with the rows it has to describe."""
    async with AsyncSessionLocal() as session:
        reltuples = (await session.execute(
            text("SELECT c.reltuples FROM pg_class c WHERE c.relname = 'discovery_queue'")
        )).scalar_one()
        rows = (await session.execute(text("SELECT count(*) FROM discovery_queue"))).scalar_one()
    return float(reltuples), int(rows)


async def _drained_rows(viewer: uuid.UUID) -> int:
    """The rows the exhausted-deck setup put in the queue for this viewer."""
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text("SELECT count(*) FROM discovery_queue WHERE viewer_id = :viewer"),
                {"viewer": viewer},
            )
        ).scalar_one()


async def test_the_timing_loop_settles_statistics_after_the_setup_and_before_the_calls() -> None:
    """The path's own preparation writes rows; the estimates have to count them before timing."""
    loop = inspect.getsource(_probe()._measure_size)

    assert "_settle_statistics(" in loop, (
        "the timing loop no longer settles statistics for the path it is about to measure: the "
        "exhausted deck was timed at 323.4 ms on a queue the planner had as `reltuples = 0`, while "
        "the same statement on the counted queue costs 68.1…76.5 ms"
    )
    settles = loop.index("_settle_statistics(")
    setup = loop.index("await setup(session, ctx)")
    timed = loop.index("for _ in range(runs)")
    assert settles > setup, (
        "statistics are settled before the path's setup runs, so the rows the setup writes — a "
        "queue row per account on the stand — are again outside the estimates the plan is chosen "
        f"from (settle at offset {settles}, setup at {setup})"
    )
    assert settles < timed, (
        "the settle step sits inside the timed calls, so the wall-clock median would start "
        f"carrying a ~2 200 ms ANALYZE (settle at offset {settles}, timing loop at {timed})"
    )


def test_analyze_lives_in_one_step_of_the_harness() -> None:
    """One place decides when the estimates are refreshed; a second one can only be mistimed."""
    probe = _probe()
    source = inspect.getsource(probe)
    calls = [line for line in source.splitlines() if "ANALYZE" in line.upper() and "execute" in line]

    assert len(calls) == 1, (
        f"`ANALYZE` is executed in {len(calls)} places ({calls}): the run then has two moments that "
        "claim to describe the stand, and the one that comes first wins the plan"
    )
    settle = getattr(probe, "_settle_statistics", None)
    assert settle is not None, (
        "the harness has no `_settle_statistics` step, so the ANALYZE it does keep sits wherever it "
        "was left — before the setup whose rows it then cannot count, which is what this stage "
        "measured as 323.4 ms against 107.2 ms"
    )
    assert "ANALYZE" in inspect.getsource(settle).upper(), (
        "the single ANALYZE is not the one inside `_settle_statistics`, so the step the timing loop "
        "calls per path is not the step that refreshes the estimates"
    )


async def test_the_settled_estimate_counts_the_rows_the_setup_wrote(client: AsyncClient) -> None:
    """After the harness's settle step the planner's number equals the rows the drain inserted."""
    probe = _probe()
    viewer = await _account(client, "s67_viewer@befos.app", name="Вера", gender="female")
    await _account(client, "s67_peer@befos.app", name="Пётр", gender="male")
    database = urlsplit(settings.database_url).path.lstrip("/")

    # Settled before the setup, so the first estimate describes the queue as it was without the
    # path's rows — the same stale-against-new-rows relation the stand leaves its page in.
    await probe._settle_statistics(asyncpg, database)
    quiet_estimate, quiet_rows = await _queue_estimate()

    async with AsyncSessionLocal() as session:
        await probe._drain_deck(session, {"viewer_id": viewer})
        await session.commit()
    drained = await _drained_rows(viewer)
    stale_estimate, rows_after_setup = await _queue_estimate()

    await probe._settle_statistics(asyncpg, database)
    estimate, rows = await _queue_estimate()

    async with AsyncSessionLocal() as session:
        await session.execute(
            text("DELETE FROM discovery_queue WHERE viewer_id = :viewer"), {"viewer": viewer}
        )
        await session.commit()

    assert drained > 0, (
        f"the setup left the viewer {drained} queue rows: without rows the statistics do not count "
        "yet there is nothing for the settle step to reconcile, and the red state of this stage has "
        "to be re-shot on a stand that has them"
    )
    assert rows_after_setup == quiet_rows + drained, (
        f"the queue held {quiet_rows} rows before the setup, the setup added {drained}, and together "
        f"they read {rows_after_setup}: somebody other than the path touched the table between the "
        "two settles, so what is compared below are not the rows the setup wrote"
    )
    assert rows == rows_after_setup, (
        f"the settle step changed the rows it counted ({rows_after_setup} → {rows}): ANALYZE is "
        "supposed to read the stand, not to write it"
    )
    assert estimate == rows, (
        f"the settle step left an estimate of {estimate:.1f} rows over {rows} real ones; before the "
        f"setup the planner expected {quiet_estimate:.1f} and right after the drain "
        f"{stale_estimate:.1f}. On the 50 000 stand the same pair of numbers (0 over 50 000) cost "
        "the published row 323.4 ms instead of 107.2 ms. A small table is counted exactly by "
        "ANALYZE, so a disagreement here is the same defect the stand publishes at scale"
    )
