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
# pair that shares an interest (the caller's session, the pair's own row, the two profiles with their
# interests and answer vectors, the interest titles of what they share, the two names, the pair's
# plans). The stand's pair shares nothing — its profiles draw interests independently — and the
# seventh read is exactly the title lookup, which `explain_pair` skips when there is no slug to
# resolve; `test_the_eighth_read_buys_the_titles_of_what_the_pair_shares` measures that pair too, so
# both numbers are published ones: 7 in the `pair_profile` row of `docs/SCALE_PLAN.md`, 8 here.
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


async def _apart(client: AsyncClient, prefix: str) -> tuple[dict, dict, str]:
    """The same pair, built with two interest sets that do not overlap.

    The stand seeds exactly this: its profiles draw interests independently, so the pair it measures
    usually shares nothing. The count below is the proof of what the eighth read of
    [EXPECTED_SELECTS] is: the titles of the interests the pair shares, which `explain_pair` asks for
    only when there is a slug to look up.
    """
    a = await register_and_auth(client, f"{prefix}_a@befos.app")
    items = (await client.get("/api/v1/users/interests", headers=auth_headers(a["token"]))).json()
    catalog = items if isinstance(items, list) else items.get("interests", [])
    slugs = [i["slug"] for i in catalog]
    assert len(slugs) >= 4, f"каталог интересов не даёт двух непересекающихся наборов: {slugs}"
    await complete_onboarding(client, a["token"], name="Аня", gender="female", interests=slugs[:2])
    await answer_all_questions(client, a["token"])
    b = await register_and_auth(client, f"{prefix}_b@befos.app")
    await complete_onboarding(
        client, b["token"], name="Боря", gender="male", interests=slugs[2:4]
    )
    await answer_all_questions(client, b["token"])
    await client.post(f"/api/v1/users/{b['user_id']}/like", headers=auth_headers(a["token"]))
    back = await client.post(
        f"/api/v1/users/{a['user_id']}/like", headers=auth_headers(b["token"])
    )
    return a, b, back.json()["match_id"]


async def test_the_eighth_read_buys_the_titles_of_what_the_pair_shares(
    client: AsyncClient,
) -> None:
    """A pair with nothing shared costs one read less — and the row in `docs/SCALE_PLAN.md` says 7.

    Both numbers are published, so both are measured here: eight over a pair that shares an interest
    ([EXPECTED_SELECTS]), seven over a pair that shares none. The gap is the one conditional read in
    `CompatibilityService.explain_pair`, and it is not a leak or an accident — asking the catalogue
    for titles nobody will read would be a statement paid for by a sentence the screen never prints.
    """
    a, _, match_id = await _apart(client, "s125_apart")
    resp, kinds = await _counted(
        client, client.get(f"/api/v1/matches/{match_id}/profile", headers=auth_headers(a["token"]))
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["compatibility"]["shared_interests"] == [], body["compatibility"]
    assert kinds["select"] == EXPECTED_SELECTS - 1, (
        f"наблюдено {kinds['select']} обращений: {dict(kinds)} — разрыв между рядом прибора "
        f"и караулом держит одна условная читка названий общих интересов"
    )
    assert kinds["insert"] == kinds["update"] == kinds["delete"] == 0, dict(kinds)
    # The starter survives the empty list: it names a band instead, and the screen still has a place
    # to begin — a pair with nothing shared is not a pair with nothing to say.
    assert body["compatibility"]["starter"]


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
