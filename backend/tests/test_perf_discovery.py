"""Discovery feed must issue a bounded number of SQL statements.

The original per-candidate loop produced ~5 queries per card (N+1); after
batching the feed stays flat regardless of pool size.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import event

from app.core.database import engine

from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)


async def _candidate(client: AsyncClient, idx: int) -> None:
    email = f"perf_c{idx}@befos.app"
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=f"П{idx}", gender="male")
    await answer_all_questions(client, creds["token"])


async def test_discovery_feed_query_count_is_bounded(client: AsyncClient):
    viewer = await register_and_auth(client, "perf_viewer@befos.app")
    await complete_onboarding(client, viewer["token"], name="Вера", gender="female")
    await answer_all_questions(client, viewer["token"])
    for i in range(6):
        await _candidate(client, i)

    counter: list[int] = [0]

    def _count(conn, cursor, statement, parameters, context, executemany):
        counter[0] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _count)
    try:
        resp = await client.get(
            "/api/v1/discover?limit=20", headers=auth_headers(viewer["token"])
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)

    assert resp.status_code == 200
    body = resp.json()
    items = body.get("items", body if isinstance(body, list) else [])
    assert len(items) >= 5
    # Fixed pipeline: excludes(~4) + pool + total + viewer(3) + 4 batch loads + margin.
    # The old per-candidate code would exceed 30 statements with 6+ candidates.
    assert counter[0] <= 25, f"query count regressed: {counter[0]}"
