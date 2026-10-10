"""The stand publishes the app's latencies, so it has to measure on a connection that plans like the app's.

`backend/ops/scale_probe.py` writes the table in `docs/SCALE_PLAN.md` that says what one call of each
hot path costs, and the table is read as the product's cost per call. Until stage 58 the harness built
its engine bare — `create_async_engine(url, pool_size=5)`, no server settings — while since stage 57
the app's engine sends `plan_cache_mode = force_custom_plan`. The two are not the same connection: a
bare one plans a named statement from the bound values for its first five executions and may then keep
one generic plan, and the harness borrows a single pooled connection across the whole run, so the deck's
selection rule — executed first as `discovery_rebuild` and `discovery_page`, then as the page under
measurement — is long past its fifth call before the exhausted-deck row is timed.

The first half of this check is the one that matters for the table: it asks the server, on the engine
the harness builds and on the engine the app builds, and requires the same answer. The second half keeps
the timing loop from growing an engine of its own again, which is how the two drifted apart in the first
place.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

_PROBE_PATH = Path(__file__).resolve().parents[1] / "ops" / "scale_probe.py"


def _probe():
    """Load the stand as a module: it is a script, so it is not on the import path."""
    spec = importlib.util.spec_from_file_location("scale_probe", _PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_the_stand_engine_plans_like_the_products_engine(session: AsyncSession) -> None:
    """The connection the latency table is measured on answers the same plan question the app's does."""
    module = _probe()
    database = urlsplit(settings.database_url).path.lstrip("/")
    stand = module._stand_engine(database)
    try:
        product_mode = (await session.execute(text("SHOW plan_cache_mode"))).scalar_one()
        async with AsyncSession(bind=stand, autoflush=False) as measured:
            stand_mode = (await measured.execute(text("SHOW plan_cache_mode"))).scalar_one()
    finally:
        await stand.dispose()

    assert stand_mode == product_mode, (
        f"the harness plans with `{stand_mode}` while the app's connections plan with "
        f"`{product_mode}`: the published table would then describe a configuration the product "
        "does not run, and a shift in one would be invisible in the other"
    )
    assert stand_mode == "force_custom_plan", (
        "both engines answering something other than force_custom_plan is a decision lost from "
        "one place rather than drifted apart between two — see "
        "test_the_engine_plans_from_the_values_it_is_given.py"
    )


def test_the_timing_loop_does_not_build_an_engine_of_its_own() -> None:
    """The measured engine comes from the builder that carries the product's plan decision."""
    source = inspect.getsource(_probe()._measure_size)

    assert "_stand_engine(" in source, (
        "the timing loop no longer takes its engine from `_stand_engine`, so whatever plan decision "
        "the app has made is not the decision the latency table was measured under"
    )
    assert "create_async_engine" not in source, (
        "an engine built inside the timing loop is a second place to decide the plan mode, and the "
        "first one drifting out of it is exactly the regression this check exists for"
    )
