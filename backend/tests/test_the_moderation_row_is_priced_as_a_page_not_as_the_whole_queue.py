"""What one pass over the moderation queue costs, and what it must not grow with.

The queue is the one route in the product whose input is other people's complaints, so its price is
set by how many complaints there are. `GET /discover` was priced against 50 000 profiles by
`backend/ops/scale_probe.py`; the moderation row has no such stand yet, and a latency number taken
on a table of four rows would say nothing about a table of forty thousand. What can be pinned
deterministically is the two properties the probe's own lesson is about:

* the number of statements a page costs does not grow with the queue — one read of the page and one
  batched read of the accounts it names, not one per card;
* the read that walks the queue is answered by `ix_reports_status_created_at`, the index the
  migration created for exactly that shape, rather than by reading `reports` and sorting it.

Both are asserted against the statements the mounted routes actually send: each is captured on the
engine's own `before_cursor_execute` hook and, for the plan, replayed verbatim through asyncpg, the
same way the probe replays what it captured. A hand-written copy of the queue query would prove
only that the query somebody typed is fast.

The third property belongs to the write half and is cheap to state: closing a complaint moves one
row and writes one history row, and a status that arrives shaped like SQL text is refused by the
validator before any statement is built.

Latency itself is measured separately, against the running container and its own window, and is
published in `docs/VERIFICATION.md` with the artifact named — not asserted as a threshold here,
because the same line of checks on this host has measured between 651 and 1332 seconds for one pass
over the suite.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, event, func, insert, select, text, update

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.models import Report, ReportReview, User
from .conftest import auth_headers, complete_onboarding, register_and_auth

QUEUE = "/api/v1/reports"
PROBE = Path(__file__).resolve().parents[1] / "ops" / "scale_probe.py"
INDEX = "ix_reports_status_created_at"

# Complaints in the short queue, and in the long one. The pair is what the flat-count check compares;
# an order of magnitude is the smallest difference a per-row loop cannot hide behind.
SHORT_QUEUE = 20
LONG_QUEUE = 1000

# The statements one call pays, measured rather than hoped for. A page is the account behind the
# token, the queue walk, and one read of the two accounts every card on that page names; a detail is
# the same account read, the complaint, its two accounts, its history and the names in that history.
# They are asserted as equality, not as a ceiling, because a second read of the same thing would
# otherwise pass a `<=` unnoticed.
PAGE_STATEMENTS = 3
DETAIL_STATEMENTS = 5

# Accounts the long queue is written over. `uq_report` allows one complaint per (pair, reason), so
# the volume a queue can reach on a stand is `n * (n - 1) * len(REASONS)` — twelve accounts is the
# smallest crowd that can hold a thousand distinct ones.
POPULATION = 12

REASONS = ["spam", "harassment", "inappropriate", "fake", "minor", "impersonation", "threats", "other"]


def _probe():
    """The stand harness as a module: it is a script, so it is not on the import path.

    Reused rather than re-implemented because both of its rules are the ones under test — which
    statements a call is charged for (`_captured_by_harness`) and how a captured statement is turned
    back into an asyncpg DSN (`_asyncpg_dsn`). A second copy of either would drift from the harness
    that writes `docs/SCALE_PLAN.md` and the two would then be measuring different things.
    """
    spec = importlib.util.spec_from_file_location("scale_probe", PROBE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def _captured():
    """Every statement the window sends, in the order the server heard it."""
    calls: list[tuple[str, tuple]] = []

    def _listen(conn, cursor, statement, parameters, context, executemany):
        calls.append((" ".join(statement.split()), tuple(parameters or ())))

    event.listen(engine.sync_engine, "before_cursor_execute", _listen)
    try:
        yield calls
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _listen)


def _paid(calls: list[tuple[str, tuple]]) -> list[tuple[str, tuple]]:
    return [entry for entry in calls if _probe()._captured_by_harness(entry[0])]


def _reads_touching(calls: list[tuple[str, tuple]], relation: str) -> list[tuple[str, tuple]]:
    probe = _probe()
    return [
        entry
        for entry in calls
        if probe._read_only(entry[0]) and re.search(rf"\bfrom {relation}\b", entry[0], re.IGNORECASE)
    ]


def _writes(calls: list[tuple[str, tuple]]) -> list[tuple[str, tuple]]:
    """The statements that change a row, by their first word.

    A keyword search would count the `SELECT … FOR UPDATE` that takes the lock on the complaint as a
    write, because the phrase ends in the word — and the lock is the one statement in the call that
    must not be charged twice, since reading it is exactly what makes the second moderator wait.
    """
    return [entry for entry in calls if entry[0].split(None, 1)[0].upper() in ("INSERT", "UPDATE", "DELETE")]


async def _account(client: AsyncClient, email: str, name: str = "Тест") -> dict:
    account = await register_and_auth(client, email)
    await complete_onboarding(client, account["token"], name=name)
    return account


async def _crowd(client: AsyncClient, prefix: str, size: int = POPULATION) -> list[str]:
    """Accounts enough to hold the volume the queue is grown to."""
    return [
        (await _account(client, f"{prefix}{i}@befos.app", f"П{i}"))["user_id"]
        for i in range(size)
    ]


async def _moderator(client: AsyncClient, email: str = "perf.mod@befos.app") -> dict:
    account = await _account(client, email)
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(User).where(User.id == uuid.UUID(account["user_id"])).values(is_moderator=True)
        )
        await session.commit()
    return account


async def _seed_queue(population: list[str], count: int, *, opened: int) -> int:
    """Make the queue hold exactly `count` complaints over the given accounts, `opened` still open.

    The table is emptied first because the two sizes this file compares are two different tables: a
    second seed that appended to the first would price the long queue at a thousand and twenty rows
    and call the difference the shape of the query.

    Inserted, not POSTed: the route is bounded by `uq_report` to one complaint per (pair, reason),
    so a queue of a thousand would need a crowd that can hold a thousand distinct pairs, and the
    point of the volume is the size of `reports`, not the number of accounts that had a bad evening.
    `created_at` is staggered by one second per row because the queue orders on it and a page of
    identical timestamps would let the tiebreak decide which rows the test is looking at.
    """
    pairs = [(a, b) for a in population for b in population if a != b]
    capacity = len(pairs) * len(REASONS)
    if count > capacity:
        raise RuntimeError(
            f"{len(pairs)} pairs and {len(REASONS)} reasons hold {capacity} distinct complaints, "
            f"not {count}: grow POPULATION rather than drop the constraint"
        )
    rows = []
    base = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    for index in range(count):
        reporter, reported = pairs[index % len(pairs)]
        reason = REASONS[(index // len(pairs)) % len(REASONS)]
        written = base + timedelta(seconds=index)
        rows.append(
            {
                "id": uuid.uuid4(),
                "reporter_id": uuid.UUID(reporter),
                "reported_id": uuid.UUID(reported),
                "reason": reason,
                "details": f"queue volume probe {index}",
                "status": "open" if index < opened else "resolved",
                "created_at": written,
                "updated_at": written,
            }
        )
    async with AsyncSessionLocal() as session:
        # `report_id` carries ON DELETE CASCADE, so the history of a complaint goes with it and an
        # emptied queue never leaves a move pointing at a row that is no longer there.
        await session.execute(delete(Report))
        await session.commit()
        await session.execute(insert(Report), rows)
        await session.commit()
    return count


async def _settle() -> None:
    """Let the planner's estimates describe the rows that are actually there.

    The lesson `ops/scale_probe.py` wrote down after `deck_exhausted` published 323.4 ms against a
    plan for a queue its own setup had just filled: the choice of plan reads `pg_class.reltuples`,
    not the table. A bulk insert of a thousand rows leaves the same lie in place.
    """
    async with AsyncSessionLocal() as session:
        await session.execute(text("ANALYZE reports"))
        await session.commit()


async def _plan_for(statement: str, params: tuple) -> dict:
    """EXPLAIN the statement a route sent, with the parameters the route sent it with.

    The sequential scan is taken away on the connection that answers, because `enable_seqscan` is a
    session setting — setting it on the pool connection the route used would not be a setting the
    replay ever sees.
    """
    import asyncpg

    probe = _probe()
    database = settings.database_url.rsplit("/", 1)[-1]
    conn = await asyncpg.connect(dsn=probe._asyncpg_dsn(database))
    try:
        await conn.execute("SET enable_seqscan = off")
        rows = await conn.fetch(f"EXPLAIN (FORMAT JSON) {statement}", *params)
    finally:
        await conn.close()
    return json.loads(rows[0][0])[0]["Plan"]


def _walk(node: dict):
    yield node
    for child in node.get("Plans", ()):
        yield from _walk(child)


@pytest_asyncio.fixture
async def clean_reports():
    """`reports` emptied for the length of one test, and only for that test.

    The `client` fixture deletes the domain models between tests, so a leak into a later file is not
    the worry; the worry is a leftover inside this one, where the short queue and the long queue are
    two different row counts and have to be counted one after the other.
    """
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Report))
        await session.commit()
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Report))
        await session.commit()


async def test_a_page_of_the_queue_costs_the_same_however_long_the_queue_is(
    client: AsyncClient, clean_reports
) -> None:
    """One page, one batched account read — and no term that carries the size of the queue.

    The shape this rules out is the one `GET /discover` had before it was batched: a loop that reads
    the accused account per complaint. On a five-row queue that loop is invisible in the wall clock
    and obvious in the statement count, which is the number this test can pin without a sized stand.
    """
    moderator = await _moderator(client)
    population = await _crowd(client, "perf.pair")
    headers = auth_headers(moderator["token"])

    counts: dict[int, int] = {}
    for target in (SHORT_QUEUE, LONG_QUEUE):
        await _seed_queue(population, target, opened=target)
        await _settle()
        with _captured() as calls:
            answer = await client.get(f"{QUEUE}?status=open&limit=50", headers=headers)
        assert answer.status_code == 200, answer.text
        assert len(answer.json()["reports"]) == min(target, 50), answer.json()
        counts[target] = len(_paid(calls))

    assert counts[SHORT_QUEUE] == counts[LONG_QUEUE], (
        f"a page grew with the queue: {counts[SHORT_QUEUE]} statements at {SHORT_QUEUE} rows, "
        f"{counts[LONG_QUEUE]} at {LONG_QUEUE}"
    )
    # Priced, not just flat: the page is the account behind the token, the queue walk, and one
    # account read for both halves of every card on it. A fourth statement would be a per-row pass.
    assert counts[LONG_QUEUE] == PAGE_STATEMENTS, (
        f"a page costs {counts[LONG_QUEUE]} statements, not the measured {PAGE_STATEMENTS}: {counts}"
    )


async def test_the_queue_page_is_answered_by_the_index_that_orders_it(
    client: AsyncClient, clean_reports
) -> None:
    """The migration's key is the one the queue walk uses.

    `ix_reports_status_created_at` covers (status, created_at, id), which is the predicate and the
    ordering of `ModerationRepository.page` in that order. On a table this size the planner is free
    to decide a full read plus a sort is cheaper, and that decision is not the property under test —
    so the sequential scan is taken away and the assertion is that an index-backed path exists and
    reaches this index. `tests/test_db_reliability.py` argues the same way about the mail lookup.
    """
    moderator = await _moderator(client)
    population = await _crowd(client, "perf.key")
    await _seed_queue(population, LONG_QUEUE, opened=LONG_QUEUE // 2)
    await _settle()

    with _captured() as calls:
        answer = await client.get(f"{QUEUE}?status=open&limit=50", headers=auth_headers(moderator["token"]))
    assert answer.status_code == 200, answer.text
    page = [entry for entry in _reads_touching(calls, "reports")]
    assert page, f"the queue sent no read of `reports`: {[sql for sql, _ in calls]}"

    plan = await _plan_for(page[0][0], page[0][1])
    walked = list(_walk(plan))
    uses_index = any(node.get("Index Name") == INDEX for node in walked)
    scans_reports = any(
        node.get("Node Type") == "Seq Scan" and node.get("Relation Name") == "reports"
        for node in walked
    )
    assert uses_index and not scans_reports, f"nothing indexes this walk: {plan}"


async def test_the_history_of_a_complaint_is_read_with_it_and_not_row_by_row(
    client: AsyncClient, clean_reports
) -> None:
    """Detail plus history: the complaint, its moves, the names behind them, the two accounts.

    A reviewer's page is one complaint, so a per-history-row read would still be cheap here. What is
    pinned is that the count is a constant of the page shape rather than of how many times a
    complaint was moved — a complaint decided three times must not cost three account reads.
    """
    moderator = await _moderator(client)
    accuser = await _account(client, "perf.hist.a@befos.app", "А")
    accused = await _account(client, "perf.hist.b@befos.app", "Б")
    written = await client.post(
        f"/api/v1/users/{accused['user_id']}/report",
        json={"reason": "harassment", "details": "one line"},
        headers=auth_headers(accuser["token"]),
    )
    assert written.status_code == 200, written.text
    report_id = (
        await client.get(f"{QUEUE}?status=open", headers=auth_headers(moderator["token"]))
    ).json()["reports"][0]["id"]

    headers = auth_headers(moderator["token"])
    moves = [("reviewed", None), ("resolved", "the account was reviewed and closed")]
    for status, comment in moves:
        moved = await client.post(
            f"{QUEUE}/{report_id}/review",
            json={"status": status, "comment": comment},
            headers=headers,
        )
        assert moved.status_code == 200, moved.text

    with _captured() as calls:
        answer = await client.get(f"{QUEUE}/{report_id}", headers=headers)
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert [(row["from_status"], row["to_status"]) for row in body["reviews"]] == [
        ("open", "reviewed"),
        ("reviewed", "resolved"),
    ]
    paid = _paid(calls)
    assert len(paid) == DETAIL_STATEMENTS, (
        f"a detail with two moves costs {len(paid)} statements, "
        f"not the measured {DETAIL_STATEMENTS}: {paid}"
    )
    reviews = _reads_touching(calls, "report_reviews")
    assert len(reviews) == 1, f"the history was read {len(reviews)} times"


async def test_closing_a_complaint_moves_one_row_and_writes_one_history_row(
    client: AsyncClient, clean_reports
) -> None:
    """The write half, priced: the row under the lock, the status UPDATE, the history INSERT.

    The count matters because this is the one moderation call that changes anything, and the pair of
    statements it pays is what makes the promise in `ModerationService.review` checkable — one
    commit, both rows inside it. A reader that found a third write here would be looking at a
    decision recorded twice.
    """
    moderator = await _moderator(client)
    accuser = await _account(client, "perf.write.a@befos.app", "А")
    accused = await _account(client, "perf.write.b@befos.app", "Б")
    written = await client.post(
        f"/api/v1/users/{accused['user_id']}/report",
        json={"reason": "spam", "details": "one line"},
        headers=auth_headers(accuser["token"]),
    )
    assert written.status_code == 200, written.text
    headers = auth_headers(moderator["token"])
    report_id = (
        await client.get(f"{QUEUE}?status=open", headers=headers)
    ).json()["reports"][0]["id"]

    before = await _review_count()
    with _captured() as calls:
        answer = await client.post(
            f"{QUEUE}/{report_id}/review",
            json={"status": "resolved", "comment": "closed after a read"},
            headers=headers,
        )
    assert answer.status_code == 200, answer.text
    writes = _writes(calls)
    assert len(writes) == 2, f"a close wrote {len(writes)} rows: {writes}"
    assert await _review_count() == before + 1


async def test_a_status_shaped_like_sql_is_refused_before_it_reaches_the_table(
    client: AsyncClient, clean_reports
) -> None:
    """The queue filter takes a status from the query string, and the status is not SQL.

    `list_reports` compares the value against the four names `ReportStatus` holds and raises before
    the repository is asked for anything, so the text never reaches a bound parameter — but the
    property worth pinning is that the parameter would not have carried a second statement either:
    the rows the stand holds are still the rows it held.
    """
    moderator = await _moderator(client)
    population = [
        (await _account(client, f"perf.inj{i}@befos.app", f"И{i}"))["user_id"] for i in range(3)
    ]
    await _seed_queue(population, 12, opened=12)

    held = await _report_count()
    answer = await client.get(
        f"{QUEUE}?status=open%27%20or%20%271%27%3D%271", headers=auth_headers(moderator["token"])
    )
    assert answer.status_code == 422, answer.text
    assert "Invalid report status" in answer.json()["error"]["message"]
    assert await _report_count() == held, "the refused read changed the queue"


async def _report_count() -> int:
    async with AsyncSessionLocal() as session:
        return await session.scalar(select(func.count()).select_from(Report))


async def _review_count() -> int:
    async with AsyncSessionLocal() as session:
        return await session.scalar(select(func.count()).select_from(ReportReview))
