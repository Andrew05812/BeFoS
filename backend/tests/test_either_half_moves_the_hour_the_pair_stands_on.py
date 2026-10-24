"""A pair's hour moves from either side of the pair, and the other half is told before they look.

Stage 108 opened with a measurement, not a hypothesis. Against `28afb43` a pair standing on an evening
was moved to a different one by the half who had *only ever agreed* to it: the route answered 204 and
did nothing else. The plan went on reading `planned` on the hour it had just been asked to leave, the
partner's card said nothing had changed, and the conversation gained no line. What the tap had actually
written was a second instant into a row that still held its own acceptance of the first, and
`agreed_instant` — which reads two rows to find the promise in them — went on finding the old one. The
partner's next confirmation then destroyed the agreement instead of moving it.

The repair is two moves inside one verb, and this file holds both of them: the acceptance a new
instant replaces is withdrawn where it is written (`set_meeting_time`), and the question the new
instant asks is recorded on the plan that owns it (`_record_ask`) — because two rows naming two
different instants cannot tell a pair talking past each other from a pair one answer from a new
evening, and that difference is the plan's own history rather than a fact about the rows.

What is pinned here is what a pair can check:

The move works from the plan's own door and from whichever side it comes, and it is two facts in the
chat — the hour that ended, then the hour being asked about — never one folded into the other.

The answer to a moved hour lands the plan on the new one and closes the pair's open question.

A person moving the evening loses only their own stale acceptance of the instant. Every other answer
the pair has given, including their word that the idea is worth going to, stands.

A tap naming the hour the pair already stands on changes nothing and therefore says nothing, and a
confirmation of an hour that has since moved is refused rather than silently retargeted.

An hour in the past is refused before any row moves, and a plan the pair has closed stays closed to
both hour doors until the pair's own word reopens it — the restore after a cancellation, the withdrawn
word that a meeting happened after it was reported as one.

The partner with the chat open receives both frames in order, and the pair's state stays coherent
under the races the two doors make: a cancellation crossing a move, and both halves moving at once.

The two endings that are not the pair's last word: a plan called off and an idea the other half pushed away are both refused by the door that reports a meeting as having happened, and each refusal is undone by the very tap that ended it — which is what names the state that refused rather than the clock or an answer already given.

A stranger naming a real plan id has no plan to move.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from .conftest import auth_headers
from .test_a_pair_can_agree_on_when_to_meet import (
    _card,
    _page,
    _pair,
    _ready,
    _send,
    _whole_hour,
)
from .test_a_pairs_plan_is_one_thing_that_every_screen_moves import (
    _detail,
    _hour_behind_them,
    _plans_of,
    _tap,
)
from .test_chat_idempotency import FakeSocket, _close, _open, _wait_until
from .test_the_hour_a_pair_agreed_on_is_said_in_their_chat import (
    _chat,
    _plan_frames,
    _plan_lines,
)


@pytest.fixture
async def pair_on_a_standing_hour(client: AsyncClient):
    """A pair that took an idea up together and stands on an hour one of them named.

    A puts the idea into the chat and names the evening; B stands behind the idea and confirms the
    hour. Both of them have therefore answered the plan before anything is moved, which is the state
    the moved hour has to leave intact.
    """
    a = await _ready(client, "move_a@befos.app", "Аня")
    b = await _ready(client, "move_b@befos.app", "Боря")
    match_id = await _pair(client, a, b)
    cards = await _page(client, a["token"], match_id, force=True)
    idea = cards[0]["activity"]["id"]
    assert await _send(client, a["token"], match_id, idea) in (200, 204)
    plan_id = (await _plans_of(client, a["token"], match_id))[0]["id"]
    assert (await _tap(client, b["token"], "POST", plan_id, "accept"))[0] == 204

    first = _whole_hour(48)
    assert (await _tap(client, a["token"], "POST", plan_id, "hour", body=_hour(first)))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "hour/confirm",
                       body=_hour(first)))[0] == 204
    mine = (await _detail(client, a["token"], plan_id))["plan"]
    theirs = (await _detail(client, b["token"], plan_id))["plan"]
    assert [plan["status"] for plan in (mine, theirs)] == ["planned", "planned"], (mine, theirs)
    return a, b, match_id, idea, plan_id, first


def _hour(when: datetime) -> dict:
    return {"when": when.isoformat()}


def _instant(raw: str | None) -> datetime | None:
    return None if raw is None else datetime.fromisoformat(raw).astimezone(timezone.utc)


async def _read(client: AsyncClient, a: dict, b: dict, plan_id: str) -> tuple[dict, dict]:
    """The same plan as each of them sees it — the pair's two cards, read together."""
    return (
        (await _detail(client, a["token"], plan_id))["plan"],
        (await _detail(client, b["token"], plan_id))["plan"],
    )


async def test_the_half_that_only_agreed_moves_the_hour_from_their_own_plan_card(
    client: AsyncClient, pair_on_a_standing_hour
):
    """The measured defect, held shut at the door the defect was walked through.

    B confirmed A's evening and now names a different one. Before this stage the tap answered 204 and
    ended nothing; now the promise the pair stood on is said to be over, the new instant becomes the
    question the plan is asking, and that question is addressed to A rather than to whoever taps next.
    """
    a, b, match_id, _idea, plan_id, first = pair_on_a_standing_hour
    second = _whole_hour(96)
    assert (await _tap(client, b["token"], "POST", plan_id, "hour", body=_hour(second)))[0] == 204

    mine, theirs = await _read(client, a, b, plan_id)
    for plan in (mine, theirs):
        assert plan["status"] == "rescheduled", plan
        assert plan["starts_at"] is None, "the plan still stood on the hour one half had left"
        assert _instant(plan["pending_hour"]) == second.astimezone(timezone.utc), plan
        assert plan["pending_by"] == b["user_id"], plan
    assert mine["needs_my_answer"] is True, "the half whose answer the move asks for was not asked"
    assert theirs["needs_my_answer"] is False, "the half who moved the hour was asked to confirm it"

    lines = _plan_lines(await _chat(client, a["token"], match_id))
    assert [line["kind"] for line in lines] == [
        "plan_proposed",
        "plan_accepted",
        "plan_agreed",
        "plan_voided",
        "plan_rescheduled",
    ], lines
    assert [_instant(line["plan"]["when"]) for line in lines] == (
        [None, None, first, first, second]
    ), lines
    assert [line["plan"]["is_latest"] for line in lines] == [False, False, False, False, True], lines


async def test_the_answer_to_a_moved_hour_lands_the_plan_on_the_new_one(
    client: AsyncClient, pair_on_a_standing_hour
):
    """A reschedule is a question with an answer, and the answer closes the pair's open one.

    The plan goes back onto an hour — the second one — and stops asking anything, and the chat's
    newest word is the new agreement rather than the moved evening left standing as a promise.
    """
    a, b, match_id, _idea, plan_id, first = pair_on_a_standing_hour
    second = _whole_hour(96)
    assert (await _tap(client, b["token"], "POST", plan_id, "hour", body=_hour(second)))[0] == 204
    assert (await _tap(client, a["token"], "POST", plan_id, "hour/confirm",
                       body=_hour(second)))[0] == 204

    mine, theirs = await _read(client, a, b, plan_id)
    for plan in (mine, theirs):
        assert plan["status"] == "planned", plan
        assert _instant(plan["starts_at"]) == second.astimezone(timezone.utc), plan
        assert plan["pending_hour"] is None and plan["pending_by"] is None, plan
    lines = _plan_lines(await _chat(client, a["token"], match_id))
    assert [line["kind"] for line in lines][-2:] == ["plan_rescheduled", "plan_agreed"], lines
    assert _instant(lines[-1]["plan"]["when"]) == second.astimezone(timezone.utc)
    assert [line["plan"]["is_latest"] for line in lines][-1] is True
    assert first != second


async def test_a_move_loses_the_movers_own_stale_acceptance_and_nothing_else(
    client: AsyncClient, pair_on_a_standing_hour
):
    """«Не допускать потери ответов участников при переносе времени», read row by row.

    An hour is one of the answers a plan carries, not all of them. Moving it withdraws the mover's own
    acceptance of the *instant* they are leaving and nothing else: their word that the idea is worth
    going to, the other half's word, and the other half's own named evening all stand, so nobody is
    asked to confirm a plan they confirmed a minute ago.
    """
    a, b, match_id, idea, plan_id, first = pair_on_a_standing_hour
    second = _whole_hour(96)
    assert (await _tap(client, b["token"], "POST", plan_id, "hour", body=_hour(second)))[0] == 204

    mine, theirs = await _read(client, a, b, plan_id)
    assert (mine["my_decision"], mine["partner_decision"]) == ("joined", "joined"), mine
    assert (theirs["my_decision"], theirs["partner_decision"]) == ("joined", "joined"), theirs
    assert mine["status"] == theirs["status"] == "rescheduled", (mine, theirs)

    hers = _card(await _page(client, a["token"], match_id), idea)
    his = _card(await _page(client, b["token"], match_id), idea)
    assert _instant(hers["my_meeting_time"]) == first.astimezone(timezone.utc), (
        "A's own named evening was rewritten by the half who moved theirs"
    )
    assert _instant(his["i_accepted_time"]) is None, (
        "the acceptance B has just walked away from still stood on B's card"
    )
    assert _instant(his["my_meeting_time"]) == second.astimezone(timezone.utc), his


async def test_naming_the_hour_the_pair_already_stands_on_changes_and_says_nothing(
    client: AsyncClient, pair_on_a_standing_hour
):
    """The exempted tap: naming the hour they already agreed to moves nothing.

    The withdrawal is keyed to *a different instant*, so this tap keeps the acceptance standing rather
    than emptying the plan, and the journal — a diff over the pair's state, not a tap counter — writes
    no line about it. This is what makes the repeated send of a phone that hesitated harmless.
    """
    a, b, match_id, _idea, plan_id, first = pair_on_a_standing_hour
    before = await _chat(client, a["token"], match_id)

    assert (await _tap(client, b["token"], "POST", plan_id, "hour", body=_hour(first)))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "hour", body=_hour(first)))[0] == 204

    mine, theirs = await _read(client, a, b, plan_id)
    assert mine["status"] == theirs["status"] == "planned", (mine, theirs)
    assert _instant(mine["starts_at"]) == first.astimezone(timezone.utc), mine
    after = await _chat(client, a["token"], match_id)
    assert [line["id"] for line in after] == [line["id"] for line in before], after


async def test_a_moved_hour_is_answerable_only_as_the_hour_the_person_saw(
    client: AsyncClient, pair_on_a_standing_hour
):
    """The confirm door answers the instant on the screen, and the screen may be a minute behind.

    A confirming the evening they had stood on while B has already moved it must not silently agree to
    the new one; the refusal is what tells them to look again.
    """
    a, b, _match_id, _idea, plan_id, first = pair_on_a_standing_hour
    second = _whole_hour(96)
    assert (await _tap(client, b["token"], "POST", plan_id, "hour", body=_hour(second)))[0] == 204

    code, text = await _tap(client, a["token"], "POST", plan_id, "hour/confirm", body=_hour(first))
    assert code == 409, text
    assert "no longer" in text, text
    mine, _theirs = await _read(client, a, b, plan_id)
    assert mine["status"] == "rescheduled" and _instant(mine["pending_hour"]) == second, mine


async def test_an_hour_in_the_past_is_refused_and_the_plan_keeps_the_hour_it_had(
    client: AsyncClient, pair_on_a_standing_hour
):
    """A move to an evening that has gone by is not a move, and it does not end the one standing.

    The instant is checked before any row is written, so the pair is left on the hour they were on
    rather than between two hours with nothing to go back to — and their chat says nothing happened.
    """
    a, b, match_id, _idea, plan_id, first = pair_on_a_standing_hour
    before = await _chat(client, a["token"], match_id)

    code, text = await _tap(client, b["token"], "POST", plan_id, "hour", body=_hour(_whole_hour(-6)))
    assert code == 422, text
    assert "passed" in text, text

    mine, theirs = await _read(client, a, b, plan_id)
    assert mine["status"] == theirs["status"] == "planned", (mine, theirs)
    assert _instant(mine["starts_at"]) == first.astimezone(timezone.utc), mine
    assert mine["hour_passed"] is False, mine
    after = await _chat(client, a["token"], match_id)
    assert [line["id"] for line in after] == [line["id"] for line in before], after


async def test_the_partner_with_the_chat_open_hears_a_move_from_either_side(
    client: AsyncClient, pair_on_a_standing_hour
):
    """The move is two frames in the order the pair reads them, and they arrive unprompted.

    A's socket carries the end of the hour first and the question after it, with only the second marked
    as the conversation's newest word; the mover's own socket is told the same, so neither phone has to
    reload a chat to find out what the other one did. The frame is the row the conversation already
    holds — a socket that ran ahead of the commit would announce a plan the database refused.
    """
    a, b, match_id, _idea, plan_id, first = pair_on_a_standing_hour
    sock_a, sock_b = FakeSocket(), FakeSocket()
    task_a = await _open(sock_a, match_id, a["token"])
    task_b = await _open(sock_b, match_id, b["token"])
    try:
        second = _whole_hour(96)
        assert (await _tap(client, b["token"], "POST", plan_id, "hour", body=_hour(second)))[0] == 204
        assert await _wait_until(lambda: len(_plan_frames(sock_a)) == 2)

        for socket in (sock_a, sock_b):
            frames = _plan_frames(socket)
            assert [f["kind"] for f in frames] == ["plan_voided", "plan_rescheduled"], frames
            assert [_instant(f["plan"]["when"]) for f in frames] == [first, second], frames
            assert [f["plan"]["is_latest"] for f in frames] == [False, True], frames
            assert all(f["sender_id"] == b["user_id"] for f in frames), frames
            assert all(f["plan"]["plan_id"] == plan_id for f in frames), frames
        stored = _plan_lines(await _chat(client, a["token"], match_id))
        assert stored[-1]["id"] == frames[-1]["id"], (
            "the socket carried a line the conversation does not hold"
        )

        assert (await _tap(client, a["token"], "POST", plan_id, "hour/confirm",
                           body=_hour(second)))[0] == 204
        assert await _wait_until(lambda: len(_plan_frames(sock_b)) == 3)
        assert [f["kind"] for f in _plan_frames(sock_b)] == [
            "plan_voided", "plan_rescheduled", "plan_agreed",
        ]
    finally:
        await _close(sock_a, task_a)
        await _close(sock_b, task_b)


async def test_a_cancellation_crossing_a_move_leaves_the_pair_one_arrangement(
    client: AsyncClient, pair_on_a_standing_hour
):
    """Either half may cancel, and the other's move cannot reopen what was called off.

    The two taps are fired together and land in whichever order the pair's lock gives them. Both
    orders are acceptable; an incoherent pair is not: the plan reads the same to both of them, their
    chat ends with the cancellation rather than goes on reporting the agreement it took back, and the
    reschedule line exists exactly when the move was the one that landed.
    """
    a, b, match_id, _idea, plan_id, first = pair_on_a_standing_hour
    second = _whole_hour(96)
    cancel, move = await asyncio.gather(
        _tap(client, a["token"], "POST", plan_id, "cancel"),
        _tap(client, b["token"], "POST", plan_id, "hour", body=_hour(second)),
    )
    assert cancel[0] == 204, cancel[1]
    assert move[0] in (204, 409), move[1]

    mine, theirs = await _read(client, a, b, plan_id)
    assert mine["status"] == theirs["status"] == "cancelled", (mine, theirs)
    assert mine["can_cancel"] is False and theirs["can_cancel"] is False, (mine, theirs)
    if move[0] == 409:
        assert _instant(mine["starts_at"]) == first.astimezone(timezone.utc), mine
    else:
        assert mine["starts_at"] is None, mine

    lines = _plan_lines(await _chat(client, a["token"], match_id))
    kinds = [line["kind"] for line in lines]
    assert kinds[-1] == "plan_cancelled", kinds
    assert kinds.count("plan_cancelled") == 1, kinds
    assert ("plan_rescheduled" in kinds) is (move[0] == 204), kinds
    assert lines[-1]["plan"]["is_latest"] is True, lines


async def test_both_halves_moving_at_once_leaves_a_question_and_no_promise(
    client: AsyncClient, pair_on_a_standing_hour
):
    """Two moves fired together do not agree with each other.

    Each half names a different evening, so the pair ends on none of them, and the plan holds exactly
    one open question — the instant that landed last — addressed to the half who did not name it.
    Nothing in the two rows says which tap was second; the plan's own record of the question is what
    makes the pair's state readable rather than merely undecided.
    """
    a, b, _match_id, _idea, plan_id, _first = pair_on_a_standing_hour
    left, right = _whole_hour(72), _whole_hour(120)
    codes = await asyncio.gather(
        _tap(client, a["token"], "POST", plan_id, "hour", body=_hour(left)),
        _tap(client, b["token"], "POST", plan_id, "hour", body=_hour(right)),
    )
    assert [code for code, _ in codes] == [204, 204], codes

    mine, theirs = await _read(client, a, b, plan_id)
    assert mine["status"] == theirs["status"] == "rescheduled", (mine, theirs)
    assert mine["starts_at"] is None and theirs["starts_at"] is None, (mine, theirs)
    asked = _instant(mine["pending_hour"])
    assert asked in (left, right), mine
    assert asked == _instant(theirs["pending_hour"]), "the pair was asked about two different hours"
    assert mine["pending_by"] == theirs["pending_by"], (mine, theirs)
    named_by_a = mine["pending_by"] == a["user_id"]
    assert (mine["needs_my_answer"], theirs["needs_my_answer"]) == (
        (False, True) if named_by_a else (True, False)
    ), (mine, theirs)

    # And the pair can still land on the hour they are being asked about.
    other = a if mine["pending_by"] == b["user_id"] else b
    assert (await _tap(client, other["token"], "POST", plan_id, "hour/confirm",
                       body=_hour(asked)))[0] == 204
    after_mine, after_theirs = await _read(client, a, b, plan_id)
    assert after_mine["status"] == after_theirs["status"] == "planned"
    assert _instant(after_mine["starts_at"]) == asked.astimezone(timezone.utc), after_mine


async def test_a_meeting_that_happened_is_not_moved_to_a_new_hour(
    client: AsyncClient, pair_on_a_standing_hour, monkeypatch: pytest.MonkeyPatch
):
    """Both halves said the meeting took place; an hour is not put onto a plan that is over.

    The refusal is not a gate the client forgot — the person whose phone still shows a live card taps
    against a row the other half closed — and the plan keeps both its hour and its record of it. This
    is the defect stage 108 measured second: against `28afb43` the same two taps answered 204 and 409,
    and the 204 rewrote the closed record out from under the status that still said `completed`
    (`starts_at` emptied, `pending_hour` and `pending_by` filled, `hour_passed` turned false), so the
    pair's list said the meeting had happened while their card said a question was waiting.

    The way back is the one the guard points at rather than a second door: the word that the meeting
    happened is this person's own to take back, and once both halves have taken it the hour is a live
    arrangement again and moves like any other.
    """
    a, b, match_id, idea, plan_id, _first = pair_on_a_standing_hour
    await _hour_behind_them(client, a, b, match_id, idea, monkeypatch)
    assert (await _tap(client, a["token"], "POST", plan_id, "complete"))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "complete"))[0] == 204
    before = await _chat(client, a["token"], match_id)

    codes = [
        (await _tap(client, a["token"], "POST", plan_id, "hour", body=_hour(_whole_hour(96))))[0],
        (await _tap(client, a["token"], "POST", plan_id, "hour/confirm",
                    body=_hour(_whole_hour(96))))[0],
    ]
    assert codes == [409, 409], codes

    mine, _theirs = await _read(client, a, b, plan_id)
    assert mine["status"] == "completed", mine
    assert mine["hour_passed"] is True, mine
    after = await _chat(client, a["token"], match_id)
    assert [line["id"] for line in after] == [line["id"] for line in before], after

    assert (await _tap(client, a["token"], "DELETE", plan_id, "complete"))[0] == 204
    assert (await _tap(client, b["token"], "DELETE", plan_id, "complete"))[0] == 204
    second = _whole_hour(96)
    assert (await _tap(client, a["token"], "POST", plan_id, "hour", body=_hour(second)))[0] == 204
    mine, theirs = await _read(client, a, b, plan_id)
    assert (mine["status"], theirs["status"]) == ("rescheduled", "rescheduled"), (mine, theirs)
    assert _instant(mine["pending_hour"]) == second and mine["pending_by"] == a["user_id"], mine


async def test_a_plan_the_other_half_cancelled_refuses_a_move_until_it_is_taken_back(
    client: AsyncClient, pair_on_a_standing_hour
):
    """The mover's phone was open on the card when the cancellation landed, and the way back is one tap.

    The refusal says the plan is closed rather than the hour wrong, because the arrangement is what
    this door cannot move; restoring the plan reopens the door with it, and the hour the pair stood on
    comes back rather than having to be negotiated a second time.
    """
    a, b, _match_id, _idea, plan_id, first = pair_on_a_standing_hour
    assert (await _tap(client, b["token"], "POST", plan_id, "cancel"))[0] == 204
    code, text = await _tap(client, a["token"], "POST", plan_id, "hour", body=_hour(_whole_hour(96)))
    assert code == 409, text

    assert (await _tap(client, b["token"], "DELETE", plan_id, "cancel"))[0] == 204
    mine, _theirs = await _read(client, a, b, plan_id)
    assert mine["status"] == "planned" and _instant(mine["starts_at"]) == first, mine
    second = _whole_hour(96)
    assert (await _tap(client, a["token"], "POST", plan_id, "hour", body=_hour(second)))[0] == 204
    mine, _theirs = await _read(client, a, b, plan_id)
    assert mine["status"] == "rescheduled" and _instant(mine["pending_hour"]) == second, mine


async def test_a_stranger_naming_a_real_plan_cannot_move_its_hour(
    client: AsyncClient, pair_on_a_standing_hour
):
    """The hour door is opened by a plan id from the url, so the id proves nothing about its holder.

    Membership is checked before any row moves, and an outsider is answered the way an id that does not
    exist is answered; the pair's hour, their chat and the plan's state stay as the stranger found them.
    """
    a, b, match_id, _idea, plan_id, first = pair_on_a_standing_hour
    stranger = await _ready(client, "move_c@befos.app", "Вика")
    before = await _chat(client, a["token"], match_id)

    codes = [
        (await _tap(client, stranger["token"], "POST", plan_id, "hour",
                    body=_hour(_whole_hour(96))))[0],
        (await _tap(client, stranger["token"], "POST", plan_id, "hour/confirm",
                    body=_hour(first)))[0],
        (await _tap(client, stranger["token"], "POST", plan_id, "cancel"))[0],
        (await client.get(f"/api/v1/plans/{plan_id}",
                          headers=auth_headers(stranger["token"]))).status_code,
    ]
    assert codes == [404, 404, 404, 404], codes

    mine, _theirs = await _read(client, a, b, plan_id)
    assert mine["status"] == "planned" and _instant(mine["starts_at"]) == first, mine
    after = await _chat(client, a["token"], match_id)
    assert [line["id"] for line in after] == [line["id"] for line in before], after


async def test_a_called_off_plan_is_not_a_meeting_to_mark_as_done(
    client: AsyncClient, pair_on_a_standing_hour, monkeypatch: pytest.MonkeyPatch
):
    """Both halves' word that the evening happened has nowhere to land on a plan that was called off.

    `set_attended` refuses `cancelled` before it looks at the clock or at either answer, and the row
    keeps everything it held: a person tapping «встреча состоялась» on a card their phone still shows
    live gets a refusal rather than a plan that is simultaneously called off and over. The guard has
    lived in the service since stage 108 without being asked by any check, and stage 108's own row
    pinned the opposite direction only — `completed` refusing a cancellation.

    The way back is the door the guard names: the half who called the plan off takes it back, and the
    same two taps then complete it, which is what shows the refusal came from the cancellation rather
    than from an hour that had not passed or an answer that was already given.
    """
    a, b, match_id, idea, plan_id, _first = pair_on_a_standing_hour
    await _hour_behind_them(client, a, b, match_id, idea, monkeypatch)
    assert (await _tap(client, a["token"], "POST", plan_id, "cancel"))[0] == 204
    before = await _chat(client, a["token"], match_id)

    refusals = [await _tap(client, token, "POST", plan_id, "complete")
                for token in (a["token"], b["token"])]
    assert [code for code, _ in refusals] == [409, 409], refusals
    assert all("not a meeting to mark as done" in text for _code, text in refusals), refusals

    mine, theirs = await _read(client, a, b, plan_id)
    assert [plan["status"] for plan in (mine, theirs)] == ["cancelled", "cancelled"], (mine, theirs)
    assert mine["hour_passed"] is True and mine["starts_at"] == theirs["starts_at"], (mine, theirs)
    assert mine["i_attended"] is False and theirs["i_attended"] is False, (mine, theirs)
    after = await _chat(client, a["token"], match_id)
    assert [line["id"] for line in after] == [line["id"] for line in before], after

    assert (await _tap(client, a["token"], "DELETE", plan_id, "cancel"))[0] == 204
    assert (await _tap(client, a["token"], "POST", plan_id, "complete"))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "complete"))[0] == 204
    done = (await _detail(client, a["token"], plan_id))["plan"]
    assert done["status"] == "completed" and done["can_cancel"] is False, done


async def test_a_refused_idea_is_not_a_meeting_to_complete(
    client: AsyncClient, pair_on_a_standing_hour, monkeypatch: pytest.MonkeyPatch
):
    """The other ending the pair can reach: an idea one half pushed away has no meeting to confirm.

    The hour here has already passed, so the refusal cannot be read as the clock's — `declined` is
    checked before `starts_at` is looked at, and the row says so: the half who refused still owes no
    answer to anybody, and the other half's word that they went stays refused until the refusal is
    taken back. Taking it back is the same tap that made it (stage 107), and after it the completion
    doors open, which is what names the refusal as the thing that refused.
    """
    a, b, match_id, idea, plan_id, _first = pair_on_a_standing_hour
    await _hour_behind_them(client, a, b, match_id, idea, monkeypatch)
    assert (await _tap(client, b["token"], "POST", plan_id, "decline"))[0] == 204

    code, text = await _tap(client, a["token"], "POST", plan_id, "complete")
    assert code == 409, text
    assert "was declined" in text, text

    mine, theirs = await _read(client, a, b, plan_id)
    assert mine["status"] == theirs["status"] == "declined", (mine, theirs)
    assert mine["i_attended"] is False and theirs["partner_attended"] is False, (mine, theirs)

    assert (await _tap(client, b["token"], "DELETE", plan_id, "decline"))[0] == 204
    assert (await _tap(client, a["token"], "POST", plan_id, "complete"))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "complete"))[0] == 204
    done = (await _detail(client, a["token"], plan_id))["plan"]
    assert done["status"] == "completed", done
