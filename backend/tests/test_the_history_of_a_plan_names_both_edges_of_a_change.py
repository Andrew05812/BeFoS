"""What the pair's plan went through is readable as the words that moved, not as the words it holds.

The plan already had a history before this change: every state the pair moved through wrote a line
into their conversation, and `detail` read those lines back as `events`. What those lines could not
answer is the question a person actually opens a history for. A place change said «План изменён» and
the card drew the place the plan holds *now* — so a pair looking for the address they had been to
before found the current one and nothing else. The previous value existed only in the row that had
already been overwritten.

So the change line now names both edges of every field that moved, in the pair's own words, and the
history is read off the same conversation lines the chat carries rather than from a second journal
table. That choice is the reason there is no migration in this stage: a parallel table would hold one
copy of the pair's chronology per reader, and the two of them would be free to disagree about a tap
that failed halfway.

What is pinned here is the part a pair can be harmed by getting wrong:

Every kind of word they said about the plan lands in the history with its author and its moment — the
proposal, the agreement, the change, the cancellation — and a plan that was called off or completed
keeps them. A history that disappears with the arrangement is a record that cannot be read back.

A change names what it replaced. First word, moved word and erased word are three different answers
and the sentence says all three.

A remark a person leaves about their own plan is not in it. `personal_note` is read by its author
alone, and the history is read by both halves — so the private word never reaches the line that
would carry it.

And a stranger with a valid token gets the same answer for somebody else's real plan id as for one
that does not exist, because confirming that an arrangement is real is itself the leak.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

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
from .test_a_pairs_plan_is_one_thing_that_every_screen_moves import (
    _detail,
    _edit,
    _hour_behind_them,
    _plans_of,
    _tap,
)


@pytest.fixture
async def pair_on_an_hour(client: AsyncClient):
    """A pair standing on an agreed hour, with the plan's id and the moment they stand on.

    Everything below asks what a history line *says*, and a line about an arrangement that has no
    hour yet cannot answer it: the moment a change carries is the one the pair still stands on.
    """
    a = await _ready(client, "history_a@befos.app", "Аня")
    b = await _ready(client, "history_b@befos.app", "Боря")
    match_id = await _pair(client, a, b)
    cards = await _page(client, a["token"], match_id, force=True)
    idea = cards[0]["activity"]["id"]
    title = cards[0]["activity"]["title"]
    assert await _send(client, a["token"], match_id, idea) in (200, 204)
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204
    plans = await _plans_of(client, a["token"], match_id)
    assert len(plans) == 1 and plans[0]["status"] == "planned", plans
    return a, b, match_id, idea, title, when, plans[0]["id"]


async def _events(client: AsyncClient, token: str, plan_id: str) -> list[dict]:
    return (await _detail(client, token, plan_id))["events"]


def _says(events: list[dict], fragment: str) -> dict:
    """The one line whose sentence carries this fragment, so a test can read the rest of it.

    Returning the line rather than a boolean is the point: a history that names both edges of a
    change in the wrong order says the same words as one that does it right.
    """
    hits = [line for line in events if fragment in line["body"]]
    assert len(hits) == 1, [line["body"] for line in events]
    return hits[0]


async def test_the_history_holds_every_word_the_pair_said_about_the_plan(
    client: AsyncClient, pair_on_an_hour
):
    """One arrangement, and its whole story readable from one plan id.

    The chronology is the pair's own: the idea put to them, the hour both of them named, the place
    one of them wrote, the promise taken back. Each line names the kind of word it is, the person
    whose tap produced it, and the moment it speaks about — which is what makes the history an answer
    rather than a list of states.
    """
    a, b, _match_id, _idea, _title, when, plan_id = pair_on_an_hour
    assert (await _edit(client, a["token"], plan_id, {"place": "Книжный дворик"}))[0] == 200
    assert (await _tap(client, b["token"], "POST", plan_id, "cancel"))[0] == 204

    for token, viewer in ((a["token"], a), (b["token"], b)):
        events = await _events(client, token, plan_id)
        assert [line["kind"] for line in events] == [
            "plan_proposed",
            "plan_agreed",
            "plan_changed",
            "plan_cancelled",
        ], f"{viewer['user_id']}: {events}"
        assert [line["sender_id"] for line in events] == [
            a["user_id"], b["user_id"], a["user_id"], b["user_id"]
        ], "a history line was attributed to somebody whose tap did not produce it"
        assert all(line["created_at"] for line in events)
        assert datetime.fromisoformat(events[1]["plan"]["when"]) == when.astimezone(timezone.utc)
        assert datetime.fromisoformat(events[3]["plan"]["when"]) == when.astimezone(timezone.utc)
        assert events[-1]["plan"]["is_latest"] is True

    # The story is still readable after the plan it belongs to is closed.
    assert (await _detail(client, a["token"], plan_id))["plan"]["status"] == "cancelled"
    assert len(await _events(client, a["token"], plan_id)) == 4


async def test_a_completed_plan_keeps_the_story_that_led_to_it(
    client: AsyncClient, pair_on_an_hour, monkeypatch: pytest.MonkeyPatch
):
    """Saying the meeting happened is the last line of a history, not the end of it.

    The pair is put on an hour the real clock has passed so the two words that complete the plan are
    honest, and the chronology keeps every line that came before — the proposal, the agreement, the
    place they wrote — with the completion last.
    """
    a, b, match_id, idea, _title, _when, plan_id = pair_on_an_hour
    await _edit(client, a["token"], plan_id, {"place": "Книжный дворик"})
    await _hour_behind_them(client, a, b, match_id, idea, monkeypatch)

    assert (await _tap(client, a["token"], "POST", plan_id, "complete"))[0] == 204
    assert (await _tap(client, b["token"], "POST", plan_id, "complete"))[0] == 204

    events = await _events(client, a["token"], plan_id)
    kinds = [line["kind"] for line in events]
    assert kinds[-1] == "plan_completed", kinds
    assert "plan_changed" in kinds and kinds[0] == "plan_proposed", kinds
    assert (await _detail(client, a["token"], plan_id))["plan"]["status"] == "completed"


async def test_a_place_written_for_the_first_time_says_it_was_not_there_before(
    client: AsyncClient, pair_on_an_hour
):
    """The first address the pair writes is a different fact from a move, and is said as itself."""
    a, _b, _match_id, _idea, _title, _when, plan_id = pair_on_an_hour
    assert (await _edit(client, a["token"], plan_id, {"place": "Книжный дворик"}))[0] == 200

    line = _says(await _events(client, a["token"], plan_id), "место: не было → ")
    assert "«Книжный дворик»" in line["body"], line["body"]
    assert line["kind"] == "plan_changed"


async def test_a_moved_place_names_where_the_pair_had_been_and_where_they_are_now(
    client: AsyncClient, pair_on_an_hour
):
    """This is the sentence the history screen exists to answer.

    Without both edges the record says only that the plan changed and the row says what it is now, so
    the address the pair was going to is gone from every screen they have.
    """
    a, _b, _match_id, _idea, _title, _when, plan_id = pair_on_an_hour
    assert (await _edit(client, a["token"], plan_id, {"place": "Книжный дворик"}))[0] == 200
    assert (await _edit(client, a["token"], plan_id, {"place": "Театр у парка"}))[0] == 200

    events = await _events(client, a["token"], plan_id)
    moved = _says(events, "место: «Книжный дворик» → «Театр у парка»")
    assert moved["sender_id"] == a["user_id"]
    assert events.index(moved) > events.index(
        _says(events, "место: не было →")
    ), "the move was recorded before the word it moved"


async def test_a_word_taken_off_the_plan_is_said_as_gone(
    client: AsyncClient, pair_on_an_hour
):
    """Erasing is not saying nothing: the pair had an address and now they do not.

    The flag that clears a field is the one the card sends when the person empties the box, so a
    history that showed the current value alone would read as though nothing had happened at all.
    """
    a, _b, _match_id, _idea, _title, _when, plan_id = pair_on_an_hour
    assert (await _edit(client, a["token"], plan_id, {"place": "Книжный дворик"}))[0] == 200
    assert (await _edit(client, a["token"], plan_id, {"clear_place": True}))[0] == 200

    _says(await _events(client, a["token"], plan_id), "место: «Книжный дворик» → снято")


async def test_one_save_that_moved_two_words_says_both(
    client: AsyncClient, pair_on_an_hour
):
    """A tap that writes place and note at once is one event about two fields, not two lines.

    Both edges of both fields are in the sentence, because the card prefills the two boxes with what
    the row holds and a person may rewrite both before saving.
    """
    a, _b, _match_id, _idea, _title, _when, plan_id = pair_on_an_hour
    assert (await _edit(
        client, a["token"], plan_id, {"place": "Книжный дворик", "note": "Позвоню у входа"}
    ))[0] == 200
    assert (await _edit(
        client, a["token"], plan_id, {"place": "Театр у парка", "note": "Куплю билеты"}
    ))[0] == 200

    line = _says(await _events(client, a["token"], plan_id), "Театр у парка»")
    assert "место: «Книжный дворик» → «Театр у парка»" in line["body"], line["body"]
    assert "заметка: «Позвоню у входа» → «Куплю билеты»" in line["body"], line["body"]


async def test_a_change_that_moved_nothing_adds_no_line(
    client: AsyncClient, pair_on_an_hour
):
    """The resent save is the same save, and a history of taps would say a change nobody made.

    A person presses «сохранить» twice because the phone hesitated. The second tap moves no field, so
    the diff is empty and the pair's chronology stays the length it was.
    """
    a, _b, _match_id, _idea, _title, _when, plan_id = pair_on_an_hour
    assert (await _edit(client, a["token"], plan_id, {"place": "Книжный дворик"}))[0] == 200
    before = await _events(client, a["token"], plan_id)

    assert (await _edit(client, a["token"], plan_id, {"place": "Книжный дворик"}))[0] == 200
    assert (await _edit(client, a["token"], plan_id, {}))[0] == 200
    after = await _events(client, a["token"], plan_id)
    assert [line["id"] for line in after] == [line["id"] for line in before], after


async def test_a_remark_about_ones_own_plan_is_not_in_the_history_both_read(
    client: AsyncClient, pair_on_an_hour
):
    """The private note and the shared note are different fields, and only one of them is said aloud.

    The plan's own note belongs to the pair and is journalled with both edges of the move; a
    person's own remark lives on their member row and reaches their own read alone, so the history
    the other half opens holds no trace of it — not the text, not a line saying it changed.
    """
    a, b, _match_id, _idea, _title, _when, plan_id = pair_on_an_hour
    before = await _events(client, a["token"], plan_id)

    assert (await client.put(
        f"/api/v1/plans/{plan_id}/note",
        json={"note": "Возьму билеты на две"},
        headers=auth_headers(a["token"]),
    )).status_code == 204

    for token in (a["token"], b["token"]):
        events = await _events(client, token, plan_id)
        assert [line["id"] for line in events] == [line["id"] for line in before], events
        assert "билеты" not in str([line["body"] for line in events]), events
    assert (await _detail(client, a["token"], plan_id))["my_note"] == "Возьму билеты на две"


async def test_a_stranger_reading_a_real_plan_id_gets_no_history_at_all(
    client: AsyncClient, pair_on_an_hour
):
    """The history belongs to the pair, and the plan id is a guess anybody can make.

    Membership is checked before the journal is read, and the refusal is the one an id that does not
    exist gets — an outsider who learned that a plan id has a history learned that a pair arranged
    something.
    """
    a, _b, _match_id, _idea, _title, _when, plan_id = pair_on_an_hour
    assert (await _edit(client, a["token"], plan_id, {"place": "Книжный дворик"}))[0] == 200
    stranger = await _ready(client, "history_c@befos.app", "Вика")

    resp = await client.get(f"/api/v1/plans/{plan_id}", headers=auth_headers(stranger["token"]))
    assert resp.status_code == 404, resp.text
    assert (await client.get(
        f"/api/v1/plans/{plan_id}", headers=auth_headers(a["token"])
    )).status_code == 200
