"""A pair's plan is one thing, and the screens move that one thing.

The card page, the conversation and the pair's list of plans used to hold three readings of the same
arrangement: a card answered «вы договорились на …» from two preference rows, the chat carried a
journal line about an idea and an instant, and nothing could be asked about either afterwards — no
place, no cancellation, no word that the meeting actually happened. §95 of the sprint calls that
state out: «Все компоненты должны работать с одной сущностью плана. Не создавай независимые копии
одного и того же плана в разных подсистемах.»

So the plan is a row now, and every door writes through one service. What this file pins is the
consequence a pair can actually see:

One idea, one plan, whichever screen the tap came from. The card's «выбрать» and the plan's
«подтвердить» are the same act, and two taps from the two doors leave one row and one chat line —
not an arrangement per screen that a later read would have to reconcile.

A state the pair did not reach is not reported as reached. A retried tap that changed nothing says
nothing; a plan is `completed` only when both halves have said the meeting happened, and the hour
passing on its own completes nothing, because a timestamp is not evidence about the physical world.

A called-off plan is off on every screen at once, and the way back is the one act that says the pair
took it up again — by whoever called it off, not by the other half.

A remark about one's own plan stays that person's. It is read by its author and by nobody else, and
it never enters the conversation, because it is not a statement about the other half.

And a stranger holding a valid token has no plan to act on: naming somebody else's real plan id
answers the way an id that does not exist answers.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.services import plan_time
from .conftest import auth_headers
from .test_a_pair_can_agree_on_when_to_meet import (
    _accept,
    _offer,
    _page,
    _pair,
    _ready,
    _send,
    _whole_hour,
)
from .test_the_hour_a_pair_agreed_on_is_said_in_their_chat import _chat, _plan_lines


async def _plans_of(client: AsyncClient, token: str, match_id: str) -> list[dict]:
    resp = await client.get(f"/api/v1/matches/{match_id}/plans", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["plans"]


async def _my_plans(client: AsyncClient, token: str) -> list[dict]:
    resp = await client.get("/api/v1/plans", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["plans"]


async def _detail(client: AsyncClient, token: str, plan_id: str) -> dict:
    resp = await client.get(f"/api/v1/plans/{plan_id}", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _tap(
    client: AsyncClient, token: str, method: str, plan_id: str, verb: str, *, body: dict | None = None
) -> tuple[int, str]:
    resp = await client.request(
        method, f"/api/v1/plans/{plan_id}/{verb}", json=body, headers=auth_headers(token)
    )
    return resp.status_code, resp.text


async def _edit(
    client: AsyncClient, token: str, plan_id: str, body: dict
) -> tuple[int, str]:
    """The plan's own door, which changes the arrangement rather than moving one state of it."""
    resp = await client.patch(f"/api/v1/plans/{plan_id}", json=body, headers=auth_headers(token))
    return resp.status_code, resp.text


async def _plan_status(client: AsyncClient, token: str, plan_id: str) -> int:
    resp = await client.get(f"/api/v1/plans/{plan_id}", headers=auth_headers(token))
    return resp.status_code


@pytest.fixture
async def pair_with_one_idea(client: AsyncClient):
    """A pair whose plan exists: one half has put an idea to the other and said nothing more."""
    a = await _ready(client, "entity_a@befos.app", "Аня")
    b = await _ready(client, "entity_b@befos.app", "Боря")
    match_id = await _pair(client, a, b)
    cards = await _page(client, a["token"], match_id, force=True)
    idea = cards[0]["activity"]["id"]
    assert await _send(client, a["token"], match_id, idea) in (200, 204)
    plans = await _plans_of(client, a["token"], match_id)
    assert len(plans) == 1 and plans[0]["status"] == "proposed", plans
    return a, b, match_id, idea, plans[0]["id"]


async def _hour_behind_them(
    client: AsyncClient, a: dict, b: dict, match_id: str, idea: int,
    monkeypatch: pytest.MonkeyPatch,
) -> datetime:
    """Put the pair on an hour the real clock has already walked past.

    The taps are made under a clock two days behind, so the moment they name is legal when they name
    it and spent by the time the real clock answers the next read — which is the only way to ask
    whether the product completes a meeting on its own.
    """
    monkeypatch.setattr(
        plan_time, "utcnow", lambda: datetime.now(timezone.utc) - timedelta(days=2)
    )
    when = _whole_hour(-24)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204
    monkeypatch.undo()
    assert when < datetime.now(timezone.utc), "the hour the pair arranged is not behind them yet"
    return when


async def test_the_plan_screen_and_the_card_move_one_arrangement(
    client: AsyncClient, pair_with_one_idea
):
    """Two doors, one row. The plan screen answers the same arrangement the card page writes.

    The pair's list carries one plan after a tap from either door, and the answer each half reads is
    the same id — which is the difference between a plan and two screens that each remember an idea
    in their own copy of it.
    """
    a, b, match_id, idea, plan_id = pair_with_one_idea
    assert (await _tap(client, b["token"], "POST", plan_id, "accept"))[0] == 204
    when = _whole_hour(48)
    assert (await _tap(client, a["token"], "POST", plan_id, "hour", body={"when": when.isoformat()}))[
        0
    ] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204

    for token in (a["token"], b["token"]):
        plans = await _plans_of(client, token, match_id)
        assert len(plans) == 1 and plans[0]["id"] == plan_id, plans
        assert plans[0]["status"] == "planned", plans[0]
        assert datetime.fromisoformat(plans[0]["starts_at"]) == when.astimezone(timezone.utc)
    lines = await _chat(client, a["token"], match_id)
    assert [line["kind"] for line in _plan_lines(lines)] == [
        "plan_proposed",
        "plan_accepted",
        "plan_agreed",
    ], lines


async def test_a_tap_that_changed_nothing_says_nothing(
    client: AsyncClient, pair_with_one_idea
):
    """The retry of a send whose answer was lost is the same answer, not a second one.

    A person taps «подтвердить» twice because their phone showed a spinner too long. The plan already
    says what the pair has said, so the second tap moves no state and the conversation gains no line.
    """
    a, _b, match_id, _idea, plan_id = pair_with_one_idea
    assert (await _tap(client, _b["token"], "POST", plan_id, "accept"))[0] == 204
    after_first = await _chat(client, a["token"], match_id)
    assert (await _tap(client, _b["token"], "POST", plan_id, "accept"))[0] == 204

    lines = await _chat(client, a["token"], match_id)
    assert [line["id"] for line in lines] == [line["id"] for line in after_first], lines
    assert len(await _plans_of(client, a["token"], match_id)) == 1


async def test_a_meeting_is_over_only_when_both_halves_say_it(
    client: AsyncClient, pair_with_one_idea, monkeypatch: pytest.MonkeyPatch
):
    """One half's word is a third of the fact; the plan reads «состоялось» when both have said it.

    The first tap leaves the plan planned and the chat silent, because nothing yet says the meeting
    happened to both of them. That the second tap writes one line — and a third writes none — is what
    keeps a retried request from counting one evening twice.
    """
    a, b, match_id, idea, plan_id = pair_with_one_idea
    await _hour_behind_them(client, a, b, match_id, idea, monkeypatch)

    assert (await _tap(client, a["token"], "POST", plan_id, "complete"))[0] == 204
    mine = (await _detail(client, a["token"], plan_id))["plan"]
    assert mine["status"] == "planned" and mine["i_attended"] is True
    assert mine["partner_attended"] is False, "one half's word was shown as both of them meeting"
    assert "plan_completed" not in [
        line["kind"] for line in _plan_lines(await _chat(client, a["token"], match_id))
    ]

    assert (await _tap(client, b["token"], "POST", plan_id, "complete"))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "complete"))[0] == 204
    kinds = [line["kind"] for line in _plan_lines(await _chat(client, a["token"], match_id))]
    assert kinds.count("plan_completed") == 1 and kinds[-1] == "plan_completed", kinds
    done = (await _detail(client, a["token"], plan_id))["plan"]
    assert done["status"] == "completed" and done["can_cancel"] is False, done


async def test_an_hour_that_passed_completes_nothing_by_itself(
    client: AsyncClient, pair_with_one_idea, monkeypatch: pytest.MonkeyPatch
):
    """The clock going past a moment is not evidence the pair met, so no line says that it did.

    A plan whose hour is spent reads `planned` with `hour_passed` set: the screen may ask the pair
    what happened, and only their answer moves the state. An automatic `completed` would put a
    meeting into the record that nobody confirmed.
    """
    a, b, match_id, idea, plan_id = pair_with_one_idea
    await _hour_behind_them(client, a, b, match_id, idea, monkeypatch)

    plan = (await _detail(client, a["token"], plan_id))["plan"]
    assert plan["status"] == "planned", plan
    assert plan["hour_passed"] is True and plan["i_attended"] is False, plan
    assert [line["kind"] for line in _plan_lines(await _chat(client, a["token"], match_id))] == [
        "plan_proposed",
        "plan_agreed",
    ], "the conversation was told about a meeting nobody confirmed"


async def test_either_half_can_call_a_plan_off_and_the_pair_reads_it_off_everywhere(
    client: AsyncClient, pair_with_one_idea
):
    """A promise two people made is one either of them may take back — and both must see it taken.

    The cancellation names the hour it ended inside its own line, so the chat that said «вы
    договорились» becomes the chat that says it is off about the same moment. After it, the hour
    doors refuse: an hour landed on a called-off plan would leave the pair's list saying
    «отменённые» while their conversation says «договорились».
    """
    a, b, match_id, idea, plan_id = pair_with_one_idea
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204

    assert (await _tap(client, b["token"], "POST", plan_id, "cancel"))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "cancel"))[0] == 204

    for token in (a["token"], b["token"]):
        plan = await _plans_of(client, token, match_id)
        assert plan[0]["status"] == "cancelled" and plan[0]["can_cancel"] is False, plan[0]
        assert plan[0]["cancelled_at"] is not None, plan[0]
    lines = _plan_lines(await _chat(client, a["token"], match_id))
    assert [line["kind"] for line in lines] == [
        "plan_proposed",
        "plan_agreed",
        "plan_cancelled",
    ], lines
    assert lines[-1]["is_own"] is False, "the half who cancelled was shown their own line as theirs"
    assert datetime.fromisoformat(lines[-1]["plan"]["when"]) == when.astimezone(timezone.utc)
    assert (await _tap(client, a["token"], "POST", plan_id, "hour",
                       body={"when": _whole_hour(96).isoformat()}))[0] == 409


async def test_only_the_half_that_called_a_plan_off_takes_it_back(
    client: AsyncClient, pair_with_one_idea
):
    """Reopening an arrangement the other person just ended is their answer to give, not yours.

    The hour the pair stood on is still in their rows, so the plan comes back with it rather than
    having to be negotiated again — and the chat says it as the agreement it now is again.
    """
    a, b, match_id, idea, plan_id = pair_with_one_idea
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "cancel"))[0] == 204

    code, text = await _tap(client, a["token"], "DELETE", plan_id, "cancel")
    assert code == 409, text
    assert (await _plans_of(client, a["token"], match_id))[0]["status"] == "cancelled"

    assert (await _tap(client, b["token"], "DELETE", plan_id, "cancel"))[0] == 204
    plan = (await _detail(client, a["token"], plan_id))["plan"]
    assert plan["status"] == "planned" and plan["cancelled_at"] is None, plan
    assert datetime.fromisoformat(plan["starts_at"]) == when.astimezone(timezone.utc)
    lines = _plan_lines(await _chat(client, a["token"], match_id))
    assert [line["kind"] for line in lines] == [
        "plan_proposed",
        "plan_agreed",
        "plan_cancelled",
        "plan_agreed",
    ], lines
    assert [line["plan"]["is_latest"] for line in lines] == [False, False, False, True]


async def test_an_idea_the_other_half_pushes_away_is_said_as_the_pairs_answer(
    client: AsyncClient, pair_with_one_idea
):
    """A refusal from the half who did not make the plan is an answer to it, not a private edit.

    It reaches the plan's state and their conversation. Taking the refusal back is said as the plan
    changing rather than as a new proposal — the idea was in front of the pair already.
    """
    a, b, match_id, _idea, plan_id = pair_with_one_idea
    assert (await _tap(client, b["token"], "POST", plan_id, "decline"))[0] == 204

    plan = (await _detail(client, a["token"], plan_id))["plan"]
    assert plan["status"] == "declined" and plan["partner_decision"] == "declined", plan
    lines = _plan_lines(await _chat(client, a["token"], match_id))
    assert [line["kind"] for line in lines] == ["plan_proposed", "plan_declined"], lines

    assert (await _tap(client, b["token"], "DELETE", plan_id, "decline"))[0] == 204
    back = (await _detail(client, a["token"], plan_id))["plan"]
    assert back["status"] == "proposed" and back["partner_decision"] == "pending", back
    assert [line["kind"] for line in _plan_lines(await _chat(client, a["token"], match_id))][-1] == (
        "plan_changed"
    )


async def test_a_remark_about_ones_own_plan_does_not_reach_the_other_half(
    client: AsyncClient, pair_with_one_idea
):
    """A note about one's own plan is not a fact about the pair, so nothing carries it to them.

    It lives on the author's member row and is returned by their own detail read alone; the partner
    reading the same plan gets their own absent note and a shared card that never held the text. And
    because it says nothing about the other half, it writes nothing into their conversation.
    """
    a, b, match_id, _idea, plan_id = pair_with_one_idea
    before = await _chat(client, a["token"], match_id)

    assert (await client.put(
        f"/api/v1/plans/{plan_id}/note",
        json={"note": "Возьму билеты на две"},
        headers=auth_headers(a["token"]),
    )).status_code == 204

    assert (await _detail(client, a["token"], plan_id))["my_note"] == "Возьму билеты на две"
    theirs = await _detail(client, b["token"], plan_id)
    assert theirs["my_note"] is None, theirs
    assert "билеты" not in str(theirs["plan"]), "a private remark reached the pair's shared card"
    after = await _chat(client, a["token"], match_id)
    assert [line["id"] for line in after] == [line["id"] for line in before], after


async def test_the_place_the_pair_wrote_is_shared_and_moves_no_hour(
    client: AsyncClient, pair_with_one_idea
):
    """Editing a plan is said as its own line rather than by rewriting a message already read.

    The hour stays where the pair left it — the place is not the other half's answer — and both of
    them read the same words, because a place and a note belong to the arrangement, not to whoever
    typed them. Clearing is a change too, and says so.
    """
    a, b, match_id, idea, plan_id = pair_with_one_idea
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204

    edited = await client.patch(
        f"/api/v1/plans/{plan_id}", json={"place": "Кинотеатр на Петровке"},
        headers=auth_headers(a["token"]),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["starts_at"] is not None

    shared = (await _plans_of(client, b["token"], match_id))[0]
    assert shared["place"] == "Кинотеатр на Петровке" and shared["note"] is None, shared
    lines = _plan_lines(await _chat(client, b["token"], match_id))
    assert [line["kind"] for line in lines] == [
        "plan_proposed",
        "plan_agreed",
        "plan_changed",
    ], lines
    assert datetime.fromisoformat(lines[-1]["plan"]["when"]) == when.astimezone(timezone.utc)

    await client.patch(
        f"/api/v1/plans/{plan_id}", json={"clear_place": True}, headers=auth_headers(a["token"])
    )
    assert (await _plans_of(client, b["token"], match_id))[0]["place"] is None


async def test_a_stranger_naming_a_real_plan_has_no_plan_to_act_on(
    client: AsyncClient, pair_with_one_idea
):
    """The plan id arrives from the url, so it is a claim about somebody's plans, not a fact.

    Membership is read off the pair behind the plan, and the refusal is the one a plan that does not
    exist gets: telling an outsider «not yours» would confirm the arrangement is real and would say
    which pair holds it.
    """
    a, _b, match_id, _idea, plan_id = pair_with_one_idea
    stranger = await _ready(client, "entity_c@befos.app", "Вика")
    before = await _chat(client, a["token"], match_id)

    codes = [
        await _plan_status(client, stranger["token"], plan_id),
        (await _tap(client, stranger["token"], "POST", plan_id, "cancel"))[0],
        (await _edit(client, stranger["token"], plan_id, {"note": "чужая"}))[0],
        (await client.put(
            f"/api/v1/plans/{plan_id}/note", json={"note": "чужая"},
            headers=auth_headers(stranger["token"]),
        )).status_code,
    ]
    assert codes == [404, 404, 404, 404], codes
    assert await _my_plans(client, stranger["token"]) == []

    after = await _chat(client, a["token"], match_id)
    assert [line["id"] for line in after] == [line["id"] for line in before], after
    plan = (await _plans_of(client, a["token"], match_id))[0]
    assert plan["status"] == "proposed" and plan["note"] is None, plan
