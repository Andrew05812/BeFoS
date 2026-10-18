"""Each half owns their own answer about a plan, and the pair stands on two of them.

A plan has been confirmable by one person and by both, and the difference between those two states was
not readable: `activity_preferences` carried a person's answer in two booleans, and nothing kept the
plan from reading them in the wrong order. Somebody who had put an idea to the pair and then refused it
left a row holding both, and every reader of that row — the plan card, the pair's chat, the bucket the
screen files the plan under — answered from `proposed` first. The refusal was written, committed, and
read back by nobody: the plan went on saying «подтверждена обоими» under a person who had already said
they were not coming. The live probe against `f0121eb` measured exactly that — five of its ten checks
failed, and three of them named this rule (`PREMISE 1`: the half that confirmed could not say no,
`PREMISE 2`: the refusal read `accepted` for both, `PREMISE 3`: a refusal given after an agreed hour
left the plan `planned`). The same run showed two more gaps: the plan asked the wrong person (the card
of the half whose word was missing said that somebody else was being asked), and a called-off plan
answered 204 to a new answer.

What this file pins is the shape §107 asks for, held by the mechanism the plans already have rather
than by a second one:

A person's answer about an idea is the last one they gave. Refusing clears the confirmation for the
plan, and standing behind the idea again clears a refusal — while the card page keeps both of its own
facts, because the mark that the sentence went into the chat is what stops it going a second time.
This is the same rule `set_meeting_time` has carried since the pair's hour: an engagement written
later is the answer, and the chat's own record is not rewritten by it.

A confirmation is not the pair's confirmation. `accepted` needs both rows, and each half reads their
own answer as theirs and the other's as the other's — one tap never moves the answer it does not own.

The question goes to the person who owes the answer, and to nobody else.

An answer may be changed by its author, in both directions, as many times as they like, and the same
answer sent twice is one answer: no second state, no second line in the pair's chat.

A refusal outranks the hour it came after, because an hour the pair stood on is not a promise once one
of them has said they are not coming — and the hour itself is kept, so taking the refusal back returns
the arrangement rather than starting the negotiation again.

A plan that is closed is not open for a new answer, and pushing a card away stays this person's own
door. An outsider naming a real plan has no plan to answer.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from .conftest import auth_headers
from .test_a_pairs_plan_is_one_thing_that_every_screen_moves import (
    _detail,
    _hour_behind_them,
    _plans_of,
    _tap,
)
from .test_a_pair_can_agree_on_when_to_meet import (
    _accept,
    _offer,
    _page,
    _pair,
    _push,
    _ready,
    _send,
    _whole_hour,
)
from .test_an_idea_a_person_pushes_away_is_theirs_to_take_back import _card
from .test_the_hour_a_pair_agreed_on_is_said_in_their_chat import _chat, _plan_lines


@pytest.fixture
async def idea_between_two(client: AsyncClient):
    """A pair with one idea in their chat, put there by A and answered by nobody yet."""
    a = await _ready(client, "answer_a@befos.app", "Аня")
    b = await _ready(client, "answer_b@befos.app", "Боря")
    match_id = await _pair(client, a, b)
    cards = await _page(client, a["token"], match_id, force=True)
    idea = cards[0]["activity"]["id"]
    assert await _send(client, a["token"], match_id, idea) in (200, 204)
    plans = await _plans_of(client, a["token"], match_id)
    assert len(plans) == 1 and plans[0]["status"] == "proposed", plans
    return a, b, match_id, idea, plans[0]["id"]


async def _both_read(client: AsyncClient, a: dict, b: dict, plan_id: str) -> tuple[dict, dict]:
    """The same plan as each of them sees it — the pair's two cards, read in one place."""
    return (
        (await _detail(client, a["token"], plan_id))["plan"],
        (await _detail(client, b["token"], plan_id))["plan"],
    )


async def _detail_status(client: AsyncClient, token: str, plan_id: str) -> int:
    return (await client.get(f"/api/v1/plans/{plan_id}", headers=auth_headers(token))).status_code


async def test_the_plan_asks_the_half_whose_word_is_missing(
    client: AsyncClient, idea_between_two
):
    """The question «ждёт ответа» is asked of one named person, and the card says which.

    A put the idea, so A owes nothing and reads nobody being asked. B owes the plan their answer, and
    their own card says so. That the two reads differ on this one field is the whole product
    difference between «ждёт вашего ответа» and «ждёт ответа партнёра» — and before this rule both
    cards said the second, so the half who had not answered was told by their own screen that nothing
    was waiting for them.
    """
    a, b, _match_id, _idea, plan_id = idea_between_two
    mine, theirs = await _both_read(client, a, b, plan_id)

    assert mine["my_decision"] == "joined" and mine["partner_decision"] == "pending", mine
    assert mine["needs_my_answer"] is False, mine
    assert theirs["my_decision"] == "pending" and theirs["partner_decision"] == "joined", theirs
    assert theirs["needs_my_answer"] is True, theirs
    assert theirs["status"] == "proposed", "one half's idea was reported as the pair's agreement"


async def test_one_halves_confirmation_leaves_the_plan_asked_of_the_other(
    client: AsyncClient, idea_between_two
):
    """Two confirmations make `accepted`; one makes a plan that still waits, and says who it waits on.

    The tap that arrives from B's door moves B's row and nothing else: A keeps the answer A gave, and
    the pair's chat gains one line about both of them standing behind the idea.
    """
    a, b, _match_id, _idea, plan_id = idea_between_two
    assert (await _tap(client, b["token"], "POST", plan_id, "accept"))[0] == 204

    mine, theirs = await _both_read(client, a, b, plan_id)
    assert (mine["status"], theirs["status"]) == ("accepted", "accepted"), (mine, theirs)
    assert mine["my_decision"] == "joined" and theirs["my_decision"] == "joined", (mine, theirs)
    assert mine["needs_my_answer"] is False and theirs["needs_my_answer"] is False, (mine, theirs)
    kinds = [line["kind"] for line in _plan_lines(await _chat(client, a["token"], _match_id))]
    assert kinds == ["plan_proposed", "plan_accepted"], kinds


async def test_the_half_that_confirmed_can_still_say_no(client: AsyncClient, idea_between_two):
    """A confirmation is not a door closing behind it.

    B stands behind the idea, then refuses it. The row now says refusal rather than both, so the plan
    reads `declined` to the pair — A's card included — and A's own answer is exactly what A left it.
    One line is written for the change, and it is written once.
    """
    a, b, match_id, _idea, plan_id = idea_between_two
    assert (await _tap(client, b["token"], "POST", plan_id, "accept"))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "decline"))[0] == 204

    mine, theirs = await _both_read(client, a, b, plan_id)
    assert theirs["my_decision"] == "declined", theirs
    assert mine["status"] == "declined" and mine["partner_decision"] == "declined", mine
    assert mine["my_decision"] == "joined", "the other half's refusal moved this person's answer"
    kinds = [line["kind"] for line in _plan_lines(await _chat(client, a["token"], match_id))]
    assert kinds == ["plan_proposed", "plan_accepted", "plan_declined"], kinds


async def test_a_refusal_outranks_the_hour_it_came_after(client: AsyncClient, idea_between_two):
    """«Не приду», said after «в семь», is the pair's state — whatever the hour column still holds.

    The hour stays on the row: it is the pair's record of what they arranged, and a screen that had to
    forget it in order to show the refusal would have nothing left to go back to. What changes is the
    reading, and it changes for both halves at once.
    """
    a, b, match_id, idea, plan_id = idea_between_two
    assert (await _tap(client, b["token"], "POST", plan_id, "accept"))[0] == 204
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204
    mine, theirs = await _both_read(client, a, b, plan_id)
    assert (mine["status"], theirs["status"]) == ("planned", "planned"), (mine, theirs)

    assert (await _tap(client, b["token"], "POST", plan_id, "decline"))[0] == 204
    mine, theirs = await _both_read(client, a, b, plan_id)
    assert mine["status"] == "declined" and theirs["status"] == "declined", (mine, theirs)
    assert theirs["my_decision"] == "declined" and mine["my_decision"] == "joined", (mine, theirs)
    for plan in (mine, theirs):
        assert datetime.fromisoformat(plan["starts_at"]) == when.astimezone(timezone.utc), plan
    kinds = [line["kind"] for line in _plan_lines(await _chat(client, a["token"], match_id))]
    assert kinds[-1] == "plan_declined", kinds


async def test_each_half_changes_only_their_own_answer(client: AsyncClient, idea_between_two):
    """Four taps, two rows: nobody can write the answer that is not theirs to give.

    A confirms, B refuses, A refuses too, B takes theirs back — and each read answers the pair with
    what the two of them last said about their own idea, never with what the other one did.
    """
    a, b, _match_id, _idea, plan_id = idea_between_two
    assert (await _tap(client, a["token"], "POST", plan_id, "accept"))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "decline"))[0] == 204
    mine, theirs = await _both_read(client, a, b, plan_id)
    assert (mine["my_decision"], theirs["my_decision"]) == ("joined", "declined"), (mine, theirs)

    assert (await _tap(client, a["token"], "POST", plan_id, "decline"))[0] == 204
    assert (await _tap(client, b["token"], "DELETE", plan_id, "decline"))[0] == 204
    mine, theirs = await _both_read(client, a, b, plan_id)
    assert (mine["my_decision"], theirs["my_decision"]) == ("declined", "pending"), (mine, theirs)
    assert theirs["partner_decision"] == "declined", theirs


async def test_a_plan_neither_half_still_stands_behind_is_read_as_the_pairs_answer(
    client: AsyncClient, idea_between_two
):
    """The pair's card keeps reading their rows after the last confirmation is taken back.

    Both halves confirm, then both refuse — A first, B second. The second refusal is the one that
    leaves nobody standing behind the idea, and a projection that stopped reading the rows at that
    moment would go on answering the plan with the state the pair had left behind: B's own card would
    say «вы подтвердили» about a tap B had already taken back, and the arrangement would read as still
    waiting on A. The rows still say what the two of them said last, so the plan says it too.
    """
    a, b, match_id, _idea, plan_id = idea_between_two
    assert (await _tap(client, b["token"], "POST", plan_id, "accept"))[0] == 204
    assert (await _tap(client, a["token"], "POST", plan_id, "decline"))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "decline"))[0] == 204

    mine, theirs = await _both_read(client, a, b, plan_id)
    assert mine["status"] == "declined" and theirs["status"] == "declined", (mine, theirs)
    assert (mine["my_decision"], mine["partner_decision"]) == ("declined", "declined"), mine
    assert theirs["needs_my_answer"] is False, theirs
    kinds = [line["kind"] for line in _plan_lines(await _chat(client, a["token"], match_id))]
    assert kinds == ["plan_proposed", "plan_accepted", "plan_declined"], kinds


async def test_the_same_answer_sent_twice_is_one_answer(client: AsyncClient, idea_between_two):
    """The retry of a send whose answer was lost moves no state and adds no line.

    A phone that showed a spinner too long sends the tap again. `declined` twice is the same refusal,
    so the pair's chat keeps the one sentence about it — the duplicate the brief refuses is a
    notification for a change that did not happen.
    """
    a, b, match_id, _idea, plan_id = idea_between_two
    assert (await _tap(client, b["token"], "POST", plan_id, "decline"))[0] == 204
    after_first = await _chat(client, a["token"], match_id)
    assert (await _tap(client, b["token"], "POST", plan_id, "decline"))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "accept"))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "accept"))[0] == 204

    latest = await _chat(client, a["token"], match_id)
    kinds = [line["kind"] for line in _plan_lines(latest)]
    assert kinds == ["plan_proposed", "plan_declined", "plan_accepted"], kinds
    # Two of the four taps after the first refusal were repeats, and the pair's chat is one line
    # longer than it was after that refusal — the one that says B stood behind the idea again.
    assert len(latest) == len(after_first) + 1, (after_first, latest)
    mine, theirs = await _both_read(client, a, b, plan_id)
    assert theirs["my_decision"] == "joined" and theirs["status"] == "accepted", theirs
    assert mine["my_decision"] == "joined" and mine["needs_my_answer"] is False, mine


async def test_taking_a_refusal_back_returns_the_hour_the_pair_stood_on(
    client: AsyncClient, idea_between_two
):
    """Refusing an arrangement is not erasing it, and the way back is the person's own tap.

    The hour the pair agreed to lives in `accepted_time`, which a refusal leaves alone; taking the
    refusal off therefore puts the plan back where it was, and the chat says the plan changed rather
    than announcing an idea the pair already had.
    """
    a, b, match_id, idea, plan_id = idea_between_two
    assert (await _tap(client, b["token"], "POST", plan_id, "accept"))[0] == 204
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "decline"))[0] == 204

    assert (await _tap(client, b["token"], "DELETE", plan_id, "decline"))[0] == 204
    mine, theirs = await _both_read(client, a, b, plan_id)
    assert mine["status"] == "planned", mine
    assert datetime.fromisoformat(mine["starts_at"]) == when.astimezone(timezone.utc), mine
    kinds = [line["kind"] for line in _plan_lines(await _chat(client, a["token"], match_id))]
    assert kinds[-2:] == ["plan_declined", "plan_changed"], kinds


async def test_an_hour_being_moved_is_asked_of_the_half_who_did_not_name_it(
    client: AsyncClient, idea_between_two
):
    """A reschedule is a question, and the question goes to the one who was not asked before.

    Both halves had confirmed the idea, so neither owes an answer about it; the hour A has just put up
    is what B is being asked about. `needs_my_answer` covers both kinds of question because the card
    has one button for «подтвердить» and does not know which question it is answering.
    """
    a, b, match_id, idea, plan_id = idea_between_two
    assert (await _tap(client, b["token"], "POST", plan_id, "accept"))[0] == 204
    old = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, old))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, old))[0] == 204
    assert (await _offer(client, a["token"], match_id, idea, _whole_hour(96)))[0] == 204

    mine, theirs = await _both_read(client, a, b, plan_id)
    assert mine["status"] == "rescheduled" and theirs["status"] == "rescheduled", (mine, theirs)
    assert mine["my_decision"] == "joined" and theirs["my_decision"] == "joined", (mine, theirs)
    assert mine["needs_my_answer"] is False, "the half who named the hour was asked to confirm it"
    assert theirs["needs_my_answer"] is True, theirs


async def test_a_closed_plan_takes_no_new_answer_and_keeps_the_one_it_holds(
    client: AsyncClient, idea_between_two, monkeypatch: pytest.MonkeyPatch
):
    """An answer written while the pair held nothing would come back as one nobody was waiting for.

    The cancellation is the pair's own, the meeting is confirmed by both halves, and after either of
    those the accept door refuses and the row does not move — the same shape the hour doors and the
    pair's words already had. The card of a person whose phone was slow is what this answers, and the
    refusal is written in the one sentence the screen can show.
    """
    a, b, match_id, idea, plan_id = idea_between_two
    assert (await _tap(client, b["token"], "POST", plan_id, "accept"))[0] == 204
    assert (await _tap(client, a["token"], "POST", plan_id, "cancel"))[0] == 204

    before = await _chat(client, a["token"], match_id)
    codes = [
        (await _tap(client, b["token"], "POST", plan_id, "accept"))[0],
        (await _tap(client, b["token"], "DELETE", plan_id, "decline"))[0],
    ]
    assert codes == [409, 409], codes
    plan = (await _detail(client, b["token"], plan_id))["plan"]
    assert plan["status"] == "cancelled" and plan["my_decision"] == "joined", plan
    after = await _chat(client, a["token"], match_id)
    assert [line["id"] for line in after] == [line["id"] for line in before], after

    # The pair took the plan up again, and the answer door opened with it.
    assert (await _tap(client, a["token"], "DELETE", plan_id, "cancel"))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "decline"))[0] == 204

    # A meeting both halves confirmed is history: nothing about it is left to answer.
    assert (await _tap(client, a["token"], "POST", plan_id, "accept"))[0] == 204
    assert (await _tap(client, b["token"], "DELETE", plan_id, "decline"))[0] == 204
    await _hour_behind_them(client, a, b, match_id, idea, monkeypatch)
    assert (await _tap(client, a["token"], "POST", plan_id, "complete"))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "complete"))[0] == 204
    done = (await _detail(client, a["token"], plan_id))["plan"]
    assert done["status"] == "completed", done
    assert (await _tap(client, b["token"], "POST", plan_id, "accept"))[0] == 409
    # The refusal B took back leaves the confirmation B had given standing: a row keeps the mark that
    # its sentence went into the chat, so closing the plan closes an answer nobody has to re-give.
    assert (await _detail(client, b["token"], plan_id))["plan"]["my_decision"] == "joined"


async def test_pushing_a_closed_idea_away_stays_this_persons_own_door(
    client: AsyncClient, idea_between_two
):
    """The two directions of one verb are not equally closed, because one of them is a private page.

    Taking an answer back joins a pair's plan that is no longer there; pushing the card away is this
    person's own list, and a door locked there would leave them holding an idea they cannot move — the
    deck would offer it and their own tap would be refused. The plan underneath stays exactly as it was.
    """
    a, b, match_id, idea, plan_id = idea_between_two
    assert (await _tap(client, a["token"], "POST", plan_id, "cancel"))[0] == 204
    before = await _chat(client, a["token"], match_id)

    assert (await _tap(client, b["token"], "POST", plan_id, "decline"))[0] == 204
    assert await _push(client, b["token"], match_id, idea) in (200, 204)
    plan = (await _detail(client, a["token"], plan_id))["plan"]
    assert plan["status"] == "cancelled" and plan["my_decision"] == "joined", plan
    after = await _chat(client, a["token"], match_id)
    assert [line["id"] for line in after] == [line["id"] for line in before], after


async def test_a_stranger_has_no_answer_to_give(client: AsyncClient, idea_between_two):
    """A plan id from a url is a claim about somebody's plans, so an outsider gets the 404.

    The three answer doors, and the read: none of them says «not yours», because that would confirm the
    arrangement is real. The pair's rows and their chat are left exactly as the stranger found them.
    """
    a, _b, match_id, _idea, plan_id = idea_between_two
    stranger = await _ready(client, "answer_c@befos.app", "Вика")
    before = await _chat(client, a["token"], match_id)

    codes = [
        (await _detail_status(client, stranger["token"], plan_id)),
        (await _tap(client, stranger["token"], "POST", plan_id, "accept"))[0],
        (await _tap(client, stranger["token"], "POST", plan_id, "decline"))[0],
        (await _tap(client, stranger["token"], "DELETE", plan_id, "decline"))[0],
    ]
    assert codes == [404, 404, 404, 404], codes
    plan = (await _detail(client, a["token"], plan_id))["plan"]
    assert plan["status"] == "proposed" and plan["partner_decision"] == "pending", plan
    after = await _chat(client, a["token"], match_id)
    assert [line["id"] for line in after] == [line["id"] for line in before], after


async def test_the_card_page_and_the_plan_answer_one_row_by_two_rules(
    client: AsyncClient, idea_between_two
):
    """The row keeps both of its facts, and each screen takes from it the one it asks about.

    A put the idea into the pair's chat and then pushed the card away. The page still marks the idea as
    one the chat already has — that mark is what stops the same sentence going a second time, the
    defect stage 63 closed — while the plan reads the standing refusal as A's answer about the
    arrangement. Taking the refusal off therefore leaves the proposal behind it, and the plan has A
    standing behind the idea again without a new message and without a new negotiation.

    This is the pair of rules the collapse of the two flags into one would have had to give up: one
    column can answer either «did this sentence go?» or «does this person still stand behind it?», and
    never both, whatever the taps say afterwards.
    """
    a, _b, match_id, idea, plan_id = idea_between_two
    assert await _push(client, a["token"], match_id, idea) in (200, 204)

    card = _card(await _page(client, a["token"], match_id), idea)
    assert card["selected"] is True and card["declined"] is True, card
    declined = (await _detail(client, a["token"], plan_id))["plan"]
    assert declined["my_decision"] == "declined", declined

    assert (await _tap(client, a["token"], "DELETE", plan_id, "decline"))[0] == 204
    card = _card(await _page(client, a["token"], match_id), idea)
    assert card["selected"] is True and card["declined"] is False, card
    restored = (await _detail(client, a["token"], plan_id))["plan"]
    assert restored["my_decision"] == "joined" and restored["status"] == "proposed", restored
