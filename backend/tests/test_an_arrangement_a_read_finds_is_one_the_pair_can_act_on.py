"""An arrangement a screen found is one the pair can still act on.

`shared_plans` began as an empty table on purpose: migration `f2b7c90ad341` rewrote nothing and copied
nothing in, because a backfill would have been a second implementation of the hour rule — one able to
disagree with the live one — and would have had to decide `was_planned` from outside, which is the one
fact the pair's old rows cannot tell. The table was to fill itself from the rows the pair's taps had
already written, on that pair's first read, by `PlanService.sync_pair`. The rule is right; the code
only carried half of it. A read has no commit of its own: `get_session` closes the session, and the
row the projection had just built went back with it. So the arrangement the screen printed had never
existed in the database, the name it printed was minted again for every visit, and any tap carrying
that name was refused as `Plan not found`.

Measured before the repair (script `s124_probe_plan_birth.py`, throwaway database `befos_s124`, tree
`0fb2fe2`, 12:37:26…12:37:39 UTC): three calls to `/plans` from one person answered
`827b8f2a…`, `27568ce1…`, `d99c6dc4…` for one arrangement, and `shared_plans` held 0 rows before and
after the visits. Acting on the name the screen had just printed failed on all three doors:
`GET /plans/{id}` 404, `POST /plans/{id}/accept` 404, `POST /plans/{id}/hour` 404. A pair that had
agreed before this table existed therefore got a page of cards nothing could answer, and the link out
of their chat — which names a plan by its id — arrived at a list where that id was already gone.

The same half-write was also a crash waiting to happen, and the guard below found it unasked: the row
the read builds is a child of `matches`, so a dissolve committing its DELETE between the read of the
pair's rows and the INSERT made the read answer HTTP 500 on `shared_plans_match_id_fkey`. That is the
genre stages 109…112 closed five times over, and this route had never been asked.

The repair keeps the boundary this family already draws: a reader that has to birth a row takes the
pair advisory lock and re-checks the pair under it — the lock and the re-check `GET /matches/{id}
/recommendations` already uses for the deck it writes — inserts `ON CONFLICT DO NOTHING` against the
pair-and-idea key, and commits before its answer goes out. The verbs are untouched: they commit their
own transaction, and committing a birth earlier would have taken their atomicity away, leaving a
preference row standing behind a journal line that was refused.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text

from app.core.database import AsyncSessionLocal
from app.models import Match, SharedPlan, SharedPlanMember
from app.repositories.activity_repo import ActivityRepository
from app.services.plan_service import PlanService
from .conftest import auth_headers
from .test_a_pair_can_agree_on_when_to_meet import _page, _pair, _ready, _whole_hour
from .test_a_pairs_plan_is_one_thing_that_every_screen_moves import (
    _detail,
    _my_plans,
    _plans_of,
    _tap,
)


async def _took_idea_up_offline(client: AsyncClient, a: dict, b: dict) -> tuple[str, int]:
    """A pair whose rows carry an idea and whose plan table has never seen it.

    Exactly the state migration `f2b7c90ad341` leaves an upgraded database in: `set_preference` is the
    primitive the card page writes a choice with, and no plan verb has been run over the pair since.
    """
    match_id = await _pair(client, a, b)
    cards = await _page(client, a["token"], match_id, force=True)
    idea = cards[0]["activity"]["id"]
    async with AsyncSessionLocal() as db:
        repo = ActivityRepository(db)
        for person in (a, b):
            await repo.set_preference(person["user_id"], idea, 1.0, uuid.UUID(match_id))
        await db.commit()
    return match_id, idea


async def _plan_rows(match_id: str) -> list[SharedPlan]:
    async with AsyncSessionLocal() as db:
        return list(
            (
                await db.execute(
                    select(SharedPlan).where(SharedPlan.match_id == uuid.UUID(match_id))
                )
            )
            .scalars()
            .all()
        )


async def _member_rows(plan_id: str) -> int:
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                select(func.count()).select_from(SharedPlanMember).where(
                    SharedPlanMember.plan_id == uuid.UUID(plan_id)
                )
            )
        ).scalar_one()


async def _journal_lines(plan_id: str) -> int:
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                text("select count(*) from messages where plan_id = :plan_id"),
                {"plan_id": plan_id},
            )
        ).scalar_one()


async def test_an_arrangement_a_read_finds_is_kept_and_keeps_one_name(
    client: AsyncClient,
) -> None:
    a = await _ready(client, "s124_keep_a@befos.app", "Аня")
    b = await _ready(client, "s124_keep_b@befos.app", "Боря")
    match_id, _idea = await _took_idea_up_offline(client, a, b)

    visits = [await _my_plans(client, a["token"]) for _ in range(3)]
    ids = [plans[0]["id"] if plans else None for plans in visits]

    assert ids[0] is not None, "the screen printed no card for an idea the pair took up"
    assert len(set(ids)) == 1, f"one arrangement arrives as {len(set(ids))} names: {ids}"
    partner_ids = [plan["id"] for plan in await _plans_of(client, b["token"], match_id)]
    assert partner_ids == [ids[0]], f"the two halves read different arrangements: {partner_ids}"

    rows = await _plan_rows(match_id)
    assert len(rows) == 1, f"{len(rows)} plan rows for a pair that arranged one idea"
    assert await _member_rows(ids[0]) == 2, "the pair's two answers did not survive the read"


async def test_a_verb_on_the_id_the_screen_printed_lands(client: AsyncClient) -> None:
    a = await _ready(client, "s124_act_a@befos.app", "Вера")
    b = await _ready(client, "s124_act_b@befos.app", "Глеб")
    match_id, _idea = await _took_idea_up_offline(client, a, b)
    plan_id = (await _my_plans(client, a["token"]))[0]["id"]

    detail = await _detail(client, a["token"], plan_id)
    assert detail["plan"]["status"] == "accepted", detail["plan"]

    accepted, refused = await _tap(client, b["token"], "POST", plan_id, "accept")
    assert accepted == 204, refused

    offered, refused = await _tap(
        client, a["token"], "POST", plan_id, "hour", body={"when": _whole_hour(24).isoformat()}
    )
    assert offered == 204, refused
    after = (await _plans_of(client, b["token"], match_id))[0]
    assert after["pending_hour"] is not None, after
    agreed, refused = await _tap(
        client, b["token"], "POST", plan_id, "hour/confirm", body={"when": after["pending_hour"]}
    )
    assert agreed == 204, refused
    assert (await _plans_of(client, a["token"], match_id))[0]["status"] == "planned"


async def test_reading_an_arrangement_does_not_announce_it(client: AsyncClient) -> None:
    """Birthing a row is a fact about the pair, not an announcement: a visit writes no journal line.

    Lines belong to the verbs that moved a state. A reader that announced would fill the pair's chat
    with proposals of one idea, once per visit, and the journal would stop being a record of moves.
    """
    a = await _ready(client, "s124_silent_a@befos.app", "Дина")
    b = await _ready(client, "s124_silent_b@befos.app", "Егор")
    match_id, _idea = await _took_idea_up_offline(client, a, b)

    for _ in range(3):
        await _my_plans(client, a["token"])
        await _plans_of(client, b["token"], match_id)

    plan_id = (await _plan_rows(match_id))[0].id
    assert await _journal_lines(str(plan_id)) == 0, "the screen re-announced the idea to the chat"


async def test_two_halves_opening_their_plans_at_once_make_one_arrangement(
    client: AsyncClient,
) -> None:
    a = await _ready(client, "s124_race_a@befos.app", "Женя")
    b = await _ready(client, "s124_race_b@befos.app", "Захар")
    match_id, _idea = await _took_idea_up_offline(client, a, b)

    async def read(token: str) -> list[str]:
        return [plan["id"] for plan in await _plans_of(client, token, match_id)]

    first, second = await asyncio.gather(
        read(a["token"]), read(b["token"]), return_exceptions=True
    )
    for side in (first, second):
        assert not isinstance(side, BaseException), repr(side)

    rows = await _plan_rows(match_id)
    assert len(rows) == 1, f"{len(rows)} arrangements born from one idea"
    assert first == second, (first, second)


async def test_an_idea_the_pair_only_pushed_away_makes_no_arrangement(
    client: AsyncClient,
) -> None:
    """The repair must not widen the rule: a read births what the pair took up, not what it refused.

    A row that only pushed a card away names no arrangement, and a page of plans that listed refusals
    would be a list of things one of them did not want.
    """
    a = await _ready(client, "s124_gone_a@befos.app", "Ина")
    b = await _ready(client, "s124_gone_b@befos.app", "Филипп")
    match_id = await _pair(client, a, b)
    cards = await _page(client, a["token"], match_id, force=True)
    idea = cards[0]["activity"]["id"]

    async with AsyncSessionLocal() as db:
        repo = ActivityRepository(db)
        for person in (a, b):
            await repo.set_declined(person["user_id"], idea, uuid.UUID(match_id), True)
        await db.commit()

    assert await _my_plans(client, a["token"]) == []
    assert await _plan_rows(match_id) == []


async def test_a_birth_racing_the_dissolve_of_its_pair_is_refused_not_crashed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The window between reading the pair's rows and birthing its plan is closed by the pair lock.

    `pair_decisions` is the last read before the INSERT, so the gate goes there: the dissolve gets to
    commit its `DELETE FROM matches` inside exactly the window the lock closes. Without the lock this
    was an HTTP 500 on `shared_plans_match_id_fkey` — measured, not reasoned, in the first red run of
    this file.
    """
    a = await _ready(client, "s124_birth_a@befos.app", "Кира")
    b = await _ready(client, "s124_birth_b@befos.app", "Лёва")
    match_id, _idea = await _took_idea_up_offline(client, a, b)

    read_reached = asyncio.Event()
    dissolved = asyncio.Event()
    original = ActivityRepository.pair_decisions
    state = {"fired": False}

    async def gated(self, mid):  # type: ignore[no-untyped-def]
        result = await original(self, mid)
        if not state["fired"]:
            state["fired"] = True
            read_reached.set()
            try:
                await asyncio.wait_for(dissolved.wait(), timeout=1.5)
            except asyncio.TimeoutError:
                pass
        return result

    monkeypatch.setattr(ActivityRepository, "pair_decisions", gated)

    responses: dict[str, object] = {}

    async def do_read() -> None:
        responses["read"] = await client.get(
            f"/api/v1/matches/{match_id}/plans", headers=auth_headers(a["token"])
        )

    async def do_dissolve() -> None:
        await asyncio.wait_for(read_reached.wait(), timeout=6.0)
        responses["dissolve"] = await client.delete(
            f"/api/v1/matches/{match_id}", headers=auth_headers(a["token"])
        )
        dissolved.set()

    await asyncio.wait_for(asyncio.gather(do_read(), do_dissolve()), timeout=30.0)

    read = responses["read"]
    assert read.status_code in (200, 404), getattr(read, "text", read)  # type: ignore[union-attr]
    assert responses["dissolve"].status_code in (200, 204, 404)  # type: ignore[union-attr]

    async with AsyncSessionLocal() as db:
        orphans = (
            await db.execute(
                text(
                    "select count(*) from shared_plans sp where not exists "
                    "(select 1 from matches m where m.id = sp.match_id)"
                )
            )
        ).scalar_one()
        pair_still_there = (
            await db.execute(
                select(func.count()).select_from(Match).where(Match.id == uuid.UUID(match_id))
            )
        ).scalar_one()
    assert orphans == 0, f"{orphans} arrangements outlived the pair they belong to"
    if read.status_code == 200 and pair_still_there == 0:  # type: ignore[union-attr]
        assert await _plan_rows(match_id) == [], "a plan was kept for a pair that is gone"


async def test_the_birth_is_the_reads_own_door_not_a_second_rule(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keeping the row is a reader's ask, not a pair's verb: the verbs must go on committing once.

    The check is on the call signature rather than on the text: a verb that began keeping would
    commit its preference row before the journal line it writes beside it.
    """
    calls: list[dict] = []
    original = PlanService.sync_pair

    async def watched(self, match, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(dict(kwargs))
        return await original(self, match, **kwargs)

    monkeypatch.setattr(PlanService, "sync_pair", watched)
    a = await _ready(client, "s124_door_a@befos.app", "Милана")
    b = await _ready(client, "s124_door_b@befos.app", "Никита")
    match_id, _idea = await _took_idea_up_offline(client, a, b)
    await _my_plans(client, a["token"])
    plan_id = (await _plan_rows(match_id))[0].id
    await _tap(client, b["token"], "POST", plan_id, "accept")

    assert any(c.get("keep") is True for c in calls), "the plans screen does not keep what it prints"
    assert any(c.get("keep") is not True for c in calls), "the pair's own verbs began keeping twice"
