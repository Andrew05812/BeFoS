"""A pair reading itself should cost one read of the pair, not one read per question.

The couple profile is the surface this stage adds: who is in the pair, since when, how the two fit
and how much of that fit is actually measured, what is agreed for the next meeting, and how many
plans the pair has. Every piece of it already exists — the match row, the pair's compatibility
explanation, the plan list — but reaching them from the phone means one request per section, which
is the shape the deck and the pair pages used to pay for twice.

So the checks are about the aggregate and its price: both halves get the same answer from the same
batched reads, an outsider gets the 404 the pair pages already give (a pair that is none of yours
does not exist), the read issues no write statement, and the number of statements is pinned to what
this row measures rather than to what would have sounded cheap.
"""

from __future__ import annotations

from collections import Counter
from typing import Callable

from httpx import AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models import Match, Message, SharedPlan, SharedPlanMember, User

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

# Pinned by measurement, not by wish: this row counted 8 selects and 0 writes for one read of a
# pair (the caller's session, the pair's own row, the two profiles with their interests and answer
# vectors, the interest titles of what they share, the two names, the pair's plans). The stand
# publishes the same count in the `pair_profile` row, and a change here must be a change there.
EXPECTED_SELECTS = 8


def _listener(seen: list[str]) -> Callable[..., None]:
    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    return _record


async def _ready(client: AsyncClient, email: str, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def _pair(client: AsyncClient, prefix: str) -> tuple[dict, dict, str]:
    """Two onboarded accounts that answered the questionnaire, and the match between them."""
    a = await _ready(client, f"{prefix}_a@befos.app", "Аня", "female")
    b = await _ready(client, f"{prefix}_b@befos.app", "Боря", "male")
    await client.post(f"/api/v1/users/{b['user_id']}/like", headers=auth_headers(a["token"]))
    back = await client.post(
        f"/api/v1/users/{a['user_id']}/like", headers=auth_headers(b["token"])
    )
    return a, b, back.json()["match_id"]


async def _counted(client: AsyncClient, coro):
    seen: list[str] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        resp = await coro
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    kinds: Counter[str] = Counter()
    for statement in seen:
        if statement.startswith(("select", "insert", "update", "delete", "with")):
            kinds[statement.split()[0]] += 1
    return resp, kinds


async def test_the_profile_reads_the_pair_in_one_batched_pass(client: AsyncClient) -> None:
    a, b, match_id = await _pair(client, "s125_onepass")
    resp, kinds = await _counted(
        client, client.get(f"/api/v1/matches/{match_id}/profile", headers=auth_headers(a["token"]))
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert kinds["insert"] == kinds["update"] == kinds["delete"] == 0, dict(kinds)
    assert kinds["select"] == EXPECTED_SELECTS, (
        f"наблюдено {kinds['select']} обращений: {dict(kinds)} — ряд требует перепинить по замеру"
    )

    assert body["match_id"] == match_id
    assert body["since"]
    assert len(body["people"]) == 2
    assert {p["name"] for p in body["people"]} == {"Аня", "Боря"}
    assert body["plans_total"] == 0
    assert body["plan"] is None

    digest = body["compatibility"]
    assert digest["engine_version"] >= 1
    assert digest["bands_total"] == 7
    assert 0 <= digest["bands_measured"] <= 7
    assert digest["measured_weight"] == round(
        sum(c["weight"] for c in digest["categories"] if c["has_data"]), 4
    )
    assert digest["starter"]

    theirs, _ = await _counted(
        client, client.get(f"/api/v1/matches/{match_id}/profile", headers=auth_headers(b["token"]))
    )
    # A pair is one object: which half opens it must not change what the other half would read.
    assert theirs.json()["people"] == body["people"]
    assert theirs.json()["compatibility"]["overall"] == digest["overall"]


async def test_a_stranger_never_sees_a_pair_they_are_not_in(client: AsyncClient) -> None:
    _, _, match_id = await _pair(client, "s125_stranger")
    outsider = await _ready(client, "s125_stranger_c@befos.app", "Вика", "female")
    refusal, _ = await _counted(
        client, client.get(f"/api/v1/matches/{match_id}/profile", headers=auth_headers(outsider["token"]))
    )
    assert refusal.status_code == 404, refusal.text


async def test_reading_the_profile_leaves_no_trace(
    client: AsyncClient, session: AsyncSession
) -> None:
    a, _, match_id = await _pair(client, "s125_notrace")
    await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": "привет"},
        headers=auth_headers(a["token"]),
    )

    async def snapshot() -> tuple[int, int, int, int, int]:
        return (
            (await session.scalar(select(func.count()).select_from(User))) or 0,
            (await session.scalar(select(func.count()).select_from(Match))) or 0,
            (await session.scalar(select(func.count()).select_from(SharedPlan))) or 0,
            (await session.scalar(select(func.count()).select_from(SharedPlanMember))) or 0,
            (await session.scalar(select(func.count()).select_from(Message))) or 0,
        )

    before = await snapshot()
    resp, kinds = await _counted(
        client, client.get(f"/api/v1/matches/{match_id}/profile", headers=auth_headers(a["token"]))
    )
    assert resp.status_code == 200, resp.text
    assert await snapshot() == before
    assert sum(kinds[k] for k in ("insert", "update", "delete")) == 0, dict(kinds)
