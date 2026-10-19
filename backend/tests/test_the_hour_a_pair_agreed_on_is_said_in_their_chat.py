"""A pair that agreed on an hour says so in the conversation where they agreed on it.

The chat is where the idea arrived, where the two of them talked it over and where the hour was
offered; the page is where the plan is stored. Until this change the agreement ended at the row:
`accept_time` wrote `accepted_time`, the card on both phones lit up «вы договорились на …», and the
conversation the agreement was the result of stayed silent. A person opening the chat afterwards
found their own last typed sentence as the newest thing in it — the plan was invisible exactly where
the pair looks to remember what they had decided.

The line is a kind of its own rather than a message from one of them, and that is not decoration.
`sender_id` is a real person on every row, so a sentence written as if somebody had typed it gets
attributed to them, grouped with their bubbles and counted as something they said; and the plan
itself is two rows whose instants line up, which a body of prose cannot carry: no title after a
catalogue rename, no moment on the viewer's own clock, no way for the card to know whether the
agreement still stands. So the row carries `kind`, the activity and the instant, and keeps a
sentence in `body` for a client that draws only text.

What is pinned here is when the line appears, because the interesting failures are the ones where a
chat would lie:

A line appears when the idea is put to the pair, when the plan appears, when it ends, and when it
moves — and the pair's state, not the tap, decides. A retried accept changes nothing, so it writes
nothing; a refusal writes nothing; an accept that lands on a traded-away hour produces no plan under
the pair's own rule, so no agreement is announced. The chronology of a moved plan is two lines, the
end of the old moment first, so no promise the pair no longer holds is left standing as the newest
word.

The newest word is read from the whole conversation, not from the page carrying it: a cancellation
always comes after the agreement it cancels, so an older page shows an agreement whose end sits on a
newer one, and a card that called it current would print a promise nobody holds.

Nothing the pair did not decide is offered as if they had. The catalogue has no place for an
activity, so the line names the idea and the moment and stays silent about where.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.services import plan_time
from .conftest import auth_headers
from .test_a_pair_can_agree_on_when_to_meet import (
    _accept,
    _card,
    _offer,
    _pair,
    _page,
    _ready,
    _send,
    _whole_hour,
)
from .test_chat_idempotency import FakeSocket, _close, _open, _wait_until

# The card a chat line draws. `plan_id` is in it because the plan is now a thing of its own: the line
# says which arrangement it records rather than leaving a client to guess which of the pair's plans an
# idea became. `when` is absent on a proposal, which has no hour yet.
PLAN_FIELDS = {"activity_id", "activity_title", "when", "plan_id", "is_latest"}


async def _chat(client: AsyncClient, token: str, match_id: str, *, before_id: str | None = None):
    url = f"/api/v1/matches/{match_id}/messages"
    if before_id is not None:
        url += f"?before_id={before_id}"
    resp = await client.get(url, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["messages"]


async def _say(client: AsyncClient, token: str, match_id: str, body: str) -> None:
    """Type a sentence into the pair's chat, the way a person does from their own phone.

    The page's `select` records the decision and the client writes the message, so a test that wants
    a conversation with a typed line in it has to send one — the backend does not do it on its own.
    """
    resp = await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": body},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text


def _plan_lines(lines: list[dict]) -> list[dict]:
    return [line for line in lines if line["kind"] != "text"]


@pytest.fixture
async def pair_talking_about_one_idea(client: AsyncClient):
    """A pair whose chat holds one idea: the card that put it there, and a sentence about it.

    The card is the first line of the two. `select` is the tap that puts an idea in front of the other
    half, and from this stage it says so in the conversation itself rather than leaving the pair's own
    typed sentence to carry it — so every chronology below starts from it.
    """
    a = await _ready(client, "journal_a@befos.app", "Аня")
    b = await _ready(client, "journal_b@befos.app", "Боря")
    match_id = await _pair(client, a, b)
    cards = await _page(client, a["token"], match_id, force=True)
    idea = cards[0]["activity"]["id"]
    title = cards[0]["activity"]["title"]
    assert await _send(client, a["token"], match_id, idea) in (200, 204)
    await _say(client, a["token"], match_id, f"Давай {title}?")
    return a, b, match_id, idea, title


async def test_the_hour_both_halves_named_is_read_in_their_chat(
    client: AsyncClient, pair_talking_about_one_idea
):
    """The agreement is a fact about the pair, and both of them have to be able to read it back."""
    a, b, match_id, idea, title = pair_talking_about_one_idea
    when = _whole_hour(72)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204

    for token in (a["token"], b["token"]):
        lines = _plan_lines(await _chat(client, token, match_id))
        assert [line["kind"] for line in lines] == ["plan_proposed", "plan_agreed"], (
            f"the pair's chat says {len(lines)} things about one idea: {lines}"
        )
        plan = lines[-1]["plan"]
        assert plan["activity_id"] == idea
        assert plan["activity_title"] == title
        assert datetime.fromisoformat(plan["when"]) == when.astimezone(timezone.utc)
        assert plan["is_latest"] is True
        hour = when.astimezone(timezone.utc).strftime("%H:%M")
        assert title in lines[-1]["body"] and hour in lines[-1]["body"], lines[-1]["body"]


async def test_a_line_about_the_plan_is_not_somebody_saying_it(
    client: AsyncClient, pair_talking_about_one_idea
):
    """A client groups bubbles by author, so a plan must not arrive wearing a person's name.

    The row has an actor — the tap that produced it belongs to somebody, and that is who pays the
    unread count on the other side — but `kind` is what tells the two apart. A plan written as an
    ordinary message would be filed with that person's sentences and read back as something they
    said.
    """
    a, b, match_id, idea = pair_talking_about_one_idea[:4]
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204
    lines = await _chat(client, a["token"], match_id)
    typed = [line for line in lines if line["kind"] == "text"]
    agreed = _plan_lines(lines)
    assert len(typed) == 1 and [line["kind"] for line in agreed] == [
        "plan_proposed",
        "plan_agreed",
    ], lines
    assert agreed[-1]["is_own"] is False, "the person reading the chat was shown their own line"
    assert agreed[-1]["sender_id"] == b["user_id"], (
        "the line does not name the person whose tap made the plan"
    )


async def test_a_refused_agreement_leaves_the_conversation_as_it_was(
    client: AsyncClient, pair_talking_about_one_idea
):
    """Nothing the pair did not agree on may be reported as agreed.

    The refusal is the whole point of the check: a plan that was not written leaves no line behind,
    so the chat cannot show an hour the other half never offered.
    """
    _a, b, match_id, idea, _title = pair_talking_about_one_idea
    before = await _chat(client, b["token"], match_id)
    assert [line["kind"] for line in _plan_lines(before)] == ["plan_proposed"], before
    code, text = await _accept(client, b["token"], match_id, idea, _whole_hour(48))
    assert code == 409, text
    after = await _chat(client, b["token"], match_id)
    assert [line["id"] for line in after] == [line["id"] for line in before], (
        "an agreement nobody offered was written into the conversation"
    )
    assert "plan_agreed" not in [line["kind"] for line in _plan_lines(after)]


async def test_agreeing_twice_to_the_same_hour_says_it_once(
    client: AsyncClient, pair_talking_about_one_idea
):
    """A retry of a send whose answer was lost is the same agreement, not a second one.

    The dedup key a typed message uses cannot serve here: the two rows of a plan are not a message,
    and the pair would read the same sentence twice from a tap that repeated itself. The journal is
    a diff over the plan's state instead, so the second call changes nothing and writes nothing.
    """
    a, b, match_id, idea = pair_talking_about_one_idea[:4]
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204

    lines = _plan_lines(await _chat(client, a["token"], match_id))
    assert [line["kind"] for line in lines] == ["plan_proposed", "plan_agreed"], [
        line["body"] for line in lines
    ]


async def test_moving_the_hour_reports_the_end_of_the_plan(
    client: AsyncClient, pair_talking_about_one_idea
):
    """A chat that kept showing an agreement one half has taken back would lie about the pair.

    The move is two lines and not one, because it is two facts: the hour the pair stood on is over,
    and a new one is being asked about. Folding them into a single sentence would leave the promise
    the half no longer holds unsaid, and showing only the question would leave it standing.
    """
    a, b, match_id, idea, title = pair_talking_about_one_idea
    first, second = _whole_hour(48), _whole_hour(96)
    assert (await _offer(client, a["token"], match_id, idea, first))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, first))[0] == 204
    assert (await _offer(client, a["token"], match_id, idea, second))[0] == 204

    lines = _plan_lines(await _chat(client, b["token"], match_id))
    assert [line["kind"] for line in lines] == [
        "plan_proposed",
        "plan_agreed",
        "plan_voided",
        "plan_rescheduled",
    ], lines
    # Read from the half who agreed: the first line is the other one's proposal, the second is their
    # own answer, and the move — both of its lines — belongs to whoever moved it. Each of them owns
    # the line their own decision produced, which is what keeps the unread count honest on the side
    # that has not opened the chat yet.
    assert [line["is_own"] for line in lines] == [False, True, False, False], lines
    assert datetime.fromisoformat(lines[2]["plan"]["when"]) == first.astimezone(timezone.utc)
    assert datetime.fromisoformat(lines[3]["plan"]["when"]) == second.astimezone(timezone.utc)
    assert [line["plan"]["is_latest"] for line in lines] == [False, False, False, True], (
        "the agreement was still called the newest word after its cancellation"
    )
    assert _card(await _page(client, b["token"], match_id), idea)["agreed_time"] is None
    assert title in lines[2]["body"]


async def test_a_moved_hour_the_pair_lands_on_is_said_as_the_new_agreement(
    client: AsyncClient, pair_talking_about_one_idea
):
    """The chat tells the whole move, including the one made by the half who had only agreed.

    A, B, then A again: A names the first evening, B takes it, B moves it, A accepts the moved instant.
    What the pair has at the end is one promise, and it is the second one — B named 20:00 and A agreed
    to 20:00 — while the first is a moment B has already walked away from. Stage 108 found this
    chronology told wrongly: B's own stale acceptance kept the first hour standing, so B's tap ended
    nothing, asked nothing, and the pair's chat went on reading the first promise as current until A's
    accept cancelled it. The four lines below are the same two facts the half who named the hour always
    produced, now arriving whoever moves it, and the answer to the moved question is said as its own
    agreement rather than as a cancellation.
    """
    a, b, match_id, idea = pair_talking_about_one_idea[:4]
    first, second = _whole_hour(48), _whole_hour(96)
    assert await _send(client, b["token"], match_id, idea) in (200, 204)
    assert (await _offer(client, a["token"], match_id, idea, first))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, first))[0] == 204
    assert (await _offer(client, b["token"], match_id, idea, second))[0] == 204
    assert (await _accept(client, a["token"], match_id, idea, second))[0] == 204

    lines = _plan_lines(await _chat(client, a["token"], match_id))
    assert [line["kind"] for line in lines] == [
        "plan_proposed",
        "plan_accepted",
        "plan_agreed",
        "plan_voided",
        "plan_rescheduled",
        "plan_agreed",
    ], lines
    # Read from A, who put the idea to the pair and answered the moved hour: each line belongs to the
    # half whose tap produced it, and the two lines of B's move are B's.
    assert [line["is_own"] for line in lines] == [True, False, False, False, False, True], lines
    assert [
        datetime.fromisoformat(line["plan"]["when"]).astimezone(timezone.utc) if line["plan"]["when"] else None
        for line in lines
    ] == [None, None, first, first, second, second], lines
    assert [line["plan"]["is_latest"] for line in lines] == [False] * 5 + [True], (
        "the moved agreement is not the newest word about the pair's plan"
    )
    for token in (a["token"], b["token"]):
        assert _card(await _page(client, token, match_id), idea)["agreed_time"] is not None


async def test_an_older_page_of_the_chat_knows_its_agreement_was_cancelled(
    client: AsyncClient, pair_talking_about_one_idea
):
    """The cancellation is always later than the agreement, so the page cannot answer for it.

    Reading backwards from the newest line is how a chat is paged, and an old page holding the
    agreement would show it as current while a newer page already holds its end.
    """
    a, b, match_id, idea = pair_talking_about_one_idea[:4]
    first, second = _whole_hour(48), _whole_hour(96)
    assert (await _offer(client, a["token"], match_id, idea, first))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, first))[0] == 204
    assert (await _offer(client, a["token"], match_id, idea, second))[0] == 204

    newest = await _chat(client, a["token"], match_id)
    end_of_page_id = _plan_lines(newest)[-1]["id"]
    older_page = await _chat(client, a["token"], match_id, before_id=end_of_page_id)
    agreed = _plan_lines(older_page)
    assert [line["kind"] for line in agreed] == [
        "plan_proposed",
        "plan_agreed",
        "plan_voided",
    ], older_page
    assert agreed[1]["plan"]["is_latest"] is False


async def test_an_agreement_whose_hour_has_passed_is_still_the_agreement(
    client: AsyncClient, pair_talking_about_one_idea, monkeypatch: pytest.MonkeyPatch
):
    """Nothing retires a plan on the server, so a screen may call a spent hour spent.

    The pair may have met, may have missed each other, may never have told anybody — a `plan_voided`
    written by the clock at the agreed minute would report an event nobody confirmed. So the row keeps
    its kind and keeps standing as the newest word, and the passing of the hour is read where it is
    drawn. That holds only because no read path asks the clock, which is what this pins: the taps are
    made under a clock two days behind the real one, so the hour they name is already behind the real
    now, and the pair is read back against the real clock after the fake is put away.
    """
    a, b, match_id, idea = pair_talking_about_one_idea[:4]
    monkeypatch.setattr(
        plan_time,
        "utcnow",
        lambda: datetime.now(timezone.utc) - timedelta(days=2),
    )
    when = _whole_hour(-24)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204
    monkeypatch.undo()
    assert when < datetime.now(timezone.utc), "the hour the pair arranged is not behind them yet"

    lines = _plan_lines(await _chat(client, a["token"], match_id))
    assert [line["kind"] for line in lines] == ["plan_proposed", "plan_agreed"], lines
    assert lines[-1]["plan"]["is_latest"] is True, (
        "a plan the clock walked past was reported as ended, which nobody told the server"
    )
    # The page that carries the plan knows the same fact the chat does: the hour the pair landed on,
    # unchanged. Which of them is now behind them is not stored anywhere.
    agreed = _card(await _page(client, b["token"], match_id), idea)["agreed_time"]
    assert datetime.fromisoformat(agreed) == when.astimezone(timezone.utc), agreed


async def test_the_plan_line_names_what_the_pair_knows_and_not_what_it_does_not(
    client: AsyncClient, pair_talking_about_one_idea
):
    """An idea has no place in the catalogue, so a card that printed one would invent it.

    The fields are pinned by name: adding a venue, an address or a guest list to this answer would
    need a source for each of them, and a plan card that filled an absent one in looks exactly like
    the rest. `plan_id` is pinned as one of them because it is the same arrangement the pair's list
    of plans carries — the chat and the plan screen are two views of one row, not two copies.
    """
    a, b, match_id, idea = pair_talking_about_one_idea[:4]
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204
    plan = _plan_lines(await _chat(client, a["token"], match_id))[-1]["plan"]
    assert set(plan) == PLAN_FIELDS, plan
    assert plan["when"] is not None, plan
    listed = await client.get(
        f"/api/v1/matches/{match_id}/plans", headers=auth_headers(a["token"])
    )
    assert listed.status_code == 200, listed.text
    assert plan["plan_id"] in {item["id"] for item in listed.json()["plans"]}, listed.text


async def test_a_conversation_of_only_sentences_reports_no_plan(
    client: AsyncClient
):
    """The page a pair reads every day keeps answering the way it did before this line existed.

    `kind` and `plan` are added to every line, so the ordinary case has to be pinned too: a typed
    message is `text` with no plan, and a build that only reads the older fields gets the same body
    it got before. A pair that never put an idea in front of each other is the conversation this
    checks — a plan line would otherwise come from the tap that opened it, not from the sentence.
    """
    a = await _ready(client, "journal_plain_a@befos.app", "Галя")
    b = await _ready(client, "journal_plain_b@befos.app", "Гоша")
    match_id = await _pair(client, a, b)
    await _say(client, a["token"], match_id, "Привет")
    lines = await _chat(client, a["token"], match_id)
    assert len(lines) == 1
    assert lines[0]["kind"] == "text" and lines[0]["plan"] is None


async def test_somebody_outside_the_pair_cannot_write_a_plan_line_into_its_chat(
    client: AsyncClient, pair_talking_about_one_idea
):
    """A plan is a fact about one pair, and the route has no way to be told about another.

    The activity id and the match id both arrive from the url and the pair is taken from the token,
    so a stranger naming a real card of somebody else's page cannot make a line appear in a
    conversation they are not in — and the answer does not say which of the two was wrong.
    """
    _a, _b, match_id, idea = pair_talking_about_one_idea[:4]
    before = await _chat(client, _a["token"], match_id)
    stranger = await _ready(client, "journal_c@befos.app", "Вика")
    resp = await client.post(
        f"/api/v1/matches/{match_id}/recommendations/{idea}/time/accept",
        json={"when": _whole_hour(48).isoformat()},
        headers=auth_headers(stranger["token"]),
    )
    assert resp.status_code == 404, resp.text
    after = await _chat(client, _a["token"], match_id)
    assert [line["id"] for line in after] == [line["id"] for line in before]


async def test_a_dissolved_pair_arranges_nothing_and_says_nothing(
    client: AsyncClient, pair_talking_about_one_idea
):
    """The block removes the parent of every row this write touches, under the lock it takes.

    The tap lands between the membership read and the insert, so without the pair lock the child
    insert would meet a foreign key with no parent — a 500 to a person who was just blocked, and a
    journal line about a plan in a conversation that no longer exists.
    """
    a, b, match_id, idea = pair_talking_about_one_idea[:4]
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (
        await client.post(
            f"/api/v1/users/{b['user_id']}/block", json={}, headers=auth_headers(a["token"])
        )
    ).status_code == 200
    code, text = await _accept(client, b["token"], match_id, idea, when)
    assert code == 404, text


def _plan_frames(socket: FakeSocket) -> list[dict]:
    return [
        frame
        for frame in socket.sent
        if frame.get("type") == "message" and frame.get("kind") != "text"
    ]


async def test_both_open_chats_hear_the_agreement_without_reopening(
    client: AsyncClient, pair_talking_about_one_idea
):
    """A pair with the conversation on screen learns of the plan while it is looking at it.

    The frame is the one a typed message travels in, with the hour as text and an offset: the plan
    crosses a wire, and the phone that draws it has to place the moment on its own clock. A frame
    sent before the transaction committed would put a plan in front of a pair whose database had
    refused to store it, so this test also proves the order — the line is readable by the time the
    socket carries it.
    """
    a, b, match_id, idea = pair_talking_about_one_idea[:4]
    sock_a, sock_b = FakeSocket(), FakeSocket()
    task_a = await _open(sock_a, match_id, a["token"])
    task_b = await _open(sock_b, match_id, b["token"])
    try:
        when = _whole_hour(48)
        assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
        assert _plan_frames(sock_a) == [] and _plan_frames(sock_b) == [], (
            "an hour nobody answered is not yet a plan, and the chat was told about it"
        )
        assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204
        assert await _wait_until(lambda: len(_plan_frames(sock_a)) == 1)
        assert await _wait_until(lambda: len(_plan_frames(sock_b)) == 1)
        for socket in (sock_a, sock_b):
            frame = _plan_frames(socket)[0]
            assert frame["kind"] == "plan_agreed"
            assert frame["plan"]["activity_id"] == idea
            assert frame["plan"]["is_latest"] is True
            assert datetime.fromisoformat(frame["plan"]["when"]) == when.astimezone(timezone.utc)
        stored = _plan_lines(await _chat(client, a["token"], match_id))
        assert [line["kind"] for line in stored] == ["plan_proposed", "plan_agreed"]
        # The frame the socket carried is the row the conversation already holds, not a promise of
        # one still to come — which is the ordering this check exists for.
        assert stored[-1]["id"] == _plan_frames(sock_a)[0]["id"]
    finally:
        await _close(sock_a, task_a)
        await _close(sock_b, task_b)
