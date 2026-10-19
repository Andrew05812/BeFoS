"""An idea the pair likes is not yet a plan until the pair has a when.

§81 of the sprint lists «согласование времени» among the actions the ideas page owes a pair. Until
this change the screen ended at «отправить в чат»: the sentence arrived in the conversation, the
pair agreed in words, and the page remembered nothing about the agreement. A card both halves had
accepted was indistinguishable from one nobody had answered, so the plan lived only in the chat
scrollback, where neither of them looks when deciding what to do on Saturday.

The facts a plan is made of are two, and they belong to different people: one half names a moment,
the other agrees to it. That shape decides the storage. A single column on the pair cannot say who
offered and who accepted, and a state machine would have to invent states the rows do not describe,
so each half's row carries both of its own answers — `meeting_time` and `accepted_time` — and a plan
exists when one row's `accepted_time` equals the other row's `meeting_time`. The read of the page
already fetches both rows of both people in one statement, so the two instants ride along on the
SELECT the round-trip guard counts rather than costing the screen a query per card.

Four product decisions are pinned here, not just the arithmetic:

A time belongs to an idea the pair is already talking about, so naming a moment for a card nobody
has sent to the chat is refused. The alternative lets the page display «договорились» about a plan
the other half never saw.

An agreement is read back to both halves from the same instant, and every comparison is made on
instants rather than on the strings that carried them: the pair is often in two cities, so 19:00 in
one of them is a different moment from 19:00 in the other, and the same moment written with a
Moscow offset has to match the one written in UTC.

Accepting a time is not proposing the idea. The row a person holds can carry an acceptance and no
proposal, and the mark «выбрали эту идею» — the one stage 63 was opened to make honest — stays off.

A pair that named two different moments has not agreed. One names 19:00 and the other names 20:00, and
the card shows the two proposals with no plan line: the rows support two different «договорились» and
printing the earlier of the two would invent a promise neither of them holds. What *is* a promise is an
evening one half moved and the other then took — and that reading needs the mover's own earlier
acceptance to stop counting, because a row holding two accepted instants as though both still stood is
what made the half who had only ever agreed unable to move the hour at all (stage 108).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

INTERESTS = ["volunteering", "cinema", "board_games"]


async def _ready(client: AsyncClient, email: str, name: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(
        client, creds["token"], name=name, interests=list(INTERESTS)
    )
    await answer_all_questions(client, creds["token"])
    return creds


async def _pair(client: AsyncClient, a: dict, b: dict) -> str:
    await client.post(f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"]))
    second = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    assert second.status_code in (200, 201), second.text
    return second.json()["match_id"]


async def _page(client: AsyncClient, token: str, match_id: str, *, force: bool = False) -> list[dict]:
    url = f"/api/v1/matches/{match_id}/recommendations"
    if force:
        url += "?force=true"
    resp = await client.get(url, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["recommendations"]


async def _send(client: AsyncClient, token: str, match_id: str, activity_id: int) -> int:
    resp = await client.post(
        f"/api/v1/matches/{match_id}/recommendations/{activity_id}/select",
        headers=auth_headers(token),
    )
    return resp.status_code


async def _push(client: AsyncClient, token: str, match_id: str, activity_id: int) -> int:
    resp = await client.post(
        f"/api/v1/matches/{match_id}/recommendations/{activity_id}/decline",
        headers=auth_headers(token),
    )
    return resp.status_code


async def _offer(
    client: AsyncClient, token: str, match_id: str, activity_id: int, when: datetime
) -> tuple[int, str]:
    resp = await client.put(
        f"/api/v1/matches/{match_id}/recommendations/{activity_id}/time",
        json={"when": when.isoformat()},
        headers=auth_headers(token),
    )
    return resp.status_code, resp.text


async def _accept(
    client: AsyncClient, token: str, match_id: str, activity_id: int, when: datetime
) -> tuple[int, str]:
    resp = await client.post(
        f"/api/v1/matches/{match_id}/recommendations/{activity_id}/time/accept",
        json={"when": when.isoformat()},
        headers=auth_headers(token),
    )
    return resp.status_code, resp.text


def _card(cards: list[dict], activity_id: int) -> dict:
    card = next((c for c in cards if c["activity"]["id"] == activity_id), None)
    assert card is not None, f"the page no longer carries the card: {[c['activity']['id'] for c in cards]}"
    return card


def _whole_hour(hours_ahead: int) -> datetime:
    """A moment the pair would actually say out loud, in UTC, on the hour.

    The offset from `hours_ahead` is negative in one check on purpose: a past instant has to be
    expressible so the route can be seen refusing it.
    """
    now = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)
    return now.replace(minute=0, second=0, microsecond=0)


def _same_instant_elsewhere(when: datetime) -> datetime:
    """The same moment written with a three-hours-ahead offset, for the two-cities check."""
    return when.astimezone(timezone(timedelta(hours=3)))


def _parsed(card: dict, field: str) -> datetime | None:
    raw = card.get(field)
    if raw is None:
        return None
    assert raw.endswith("+00:00") or "+" in raw[10:] or raw.endswith("Z"), (
        f"{field} was echoed without an offset, so the client cannot place it in a zone: {raw!r}"
    )
    return datetime.fromisoformat(raw)


@pytest.fixture
async def pair_with_an_idea_in_chat(client: AsyncClient):
    """A pair that has met, opened its page, and put the first card into its chat."""
    a = await _ready(client, "when_a@befos.app", "Аня")
    b = await _ready(client, "when_b@befos.app", "Боря")
    match_id = await _pair(client, a, b)
    cards = await _page(client, a["token"], match_id, force=True)
    assert len(cards) >= 3, cards
    idea = cards[0]["activity"]["id"]
    assert await _send(client, a["token"], match_id, idea) in (200, 204)
    return a, b, match_id, idea


async def test_a_time_for_an_idea_the_chat_never_saw_is_refused(
    client: AsyncClient, pair_with_an_idea_in_chat
):
    """The plan is about a message the pair received, so it cannot precede it.

    Red before the check existed in the other direction: nothing stopped a person from arranging a
    meeting for a card they had never sent, and the page would have shown the other half a
    «договорились» about a plan nobody proposed.
    """
    a, _b, match_id, _idea = pair_with_an_idea_in_chat
    untouched = next(
        c["activity"]["id"] for c in await _page(client, a["token"], match_id)
        if c["activity"]["id"] != _idea
    )
    code, text = await _offer(client, a["token"], match_id, untouched, _whole_hour(24))
    assert code == 409, text
    card = _card(await _page(client, a["token"], match_id), untouched)
    assert card["my_meeting_time"] is None, "the refused offer was still written down"


async def test_a_named_time_comes_back_to_the_person_who_named_it(
    client: AsyncClient, pair_with_an_idea_in_chat
):
    """The tap has to survive the next visit, which is the whole point of storing it."""
    a, _b, match_id, idea = pair_with_an_idea_in_chat
    when = _whole_hour(48)
    code, text = await _offer(client, a["token"], match_id, idea, when)
    assert code == 204, text
    card = _card(await _page(client, a["token"], match_id), idea)
    assert _parsed(card, "my_meeting_time") == when, card["my_meeting_time"]
    assert card["partner_meeting_time"] is None
    assert card["agreed_time"] is None, "an offer nobody answered is not yet a plan"


async def test_the_offered_time_is_shown_to_the_other_half(
    client: AsyncClient, pair_with_an_idea_in_chat
):
    """A time one half names is a question the other has to be able to answer."""

    a, b, match_id, idea = pair_with_an_idea_in_chat
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    card = _card(await _page(client, b["token"], match_id), idea)
    assert _parsed(card, "partner_meeting_time") == when, (
        "the partner's page cannot see the moment being offered, so it has nothing to accept"
    )
    assert card["my_meeting_time"] is None
    assert card["agreed_time"] is None


async def test_both_halves_read_the_same_plan_after_one_agrees(
    client: AsyncClient, pair_with_an_idea_in_chat
):
    """The agreement is one fact seen from two phones, and both have to land on the same instant."""
    a, b, match_id, idea = pair_with_an_idea_in_chat
    when = _whole_hour(72)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    code, text = await _accept(client, b["token"], match_id, idea, when)
    assert code == 204, text

    mine = _card(await _page(client, a["token"], match_id), idea)
    theirs = _card(await _page(client, b["token"], match_id), idea)
    assert _parsed(mine, "agreed_time") == when
    assert _parsed(theirs, "agreed_time") == when
    assert mine["agreed_time"] == theirs["agreed_time"], (
        "the two halves were shown two different strings for one plan"
    )
    assert _parsed(mine, "i_accepted_time") is None, "the proposer was marked as the one who agreed"
    assert _parsed(theirs, "i_accepted_time") == when
    assert _parsed(theirs, "my_meeting_time") is None, (
        "accepting a moment was written as if this person had offered one"
    )


async def test_the_same_instant_written_in_two_zones_is_one_plan(
    client: AsyncClient, pair_with_an_idea_in_chat
):
    """The pair is often in two cities, so the comparison is on instants, never on strings.

    The offer goes out with a UTC offset, the acceptance comes back with a three-hour one for the
    same moment. A route that compared the two texts would answer 409 to a pair that agreed.
    """
    a, b, match_id, idea = pair_with_an_idea_in_chat
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    code, text = await _accept(client, b["token"], match_id, idea, _same_instant_elsewhere(when))
    assert code == 204, text
    assert _parsed(_card(await _page(client, a["token"], match_id), idea), "agreed_time") == when


async def test_agreeing_to_a_moment_nobody_offered_is_refused(client: AsyncClient, pair_with_an_idea_in_chat):
    """An acceptance answers a question; without one there is nothing to agree to."""
    _a, b, match_id, idea = pair_with_an_idea_in_chat
    code, text = await _accept(client, b["token"], match_id, idea, _whole_hour(48))
    assert code == 409, text
    assert _card(await _page(client, b["token"], match_id), idea)["i_accepted_time"] is None


async def test_agreeing_to_a_moment_that_moved_is_refused(client: AsyncClient, pair_with_an_idea_in_chat):
    """The instant in the request is what the person saw; if it is gone, the tap is stale.

    Without this the pair could silently agree to a time neither of them named: the first half moves
    the offer between the second half reading it and tapping it, and the acceptance lands on the
    new one.
    """
    a, b, match_id, idea = pair_with_an_idea_in_chat
    first, second = _whole_hour(48), _whole_hour(96)
    assert (await _offer(client, a["token"], match_id, idea, first))[0] == 204
    assert (await _offer(client, a["token"], match_id, idea, second))[0] == 204
    code, text = await _accept(client, b["token"], match_id, idea, first)
    assert code == 409, text
    assert _card(await _page(client, b["token"], match_id), idea)["agreed_time"] is None
    assert _parsed(_card(await _page(client, b["token"], match_id), idea), "partner_meeting_time") == second


async def test_moving_the_offer_voids_the_plan(client: AsyncClient, pair_with_an_idea_in_chat):
    """A plan is an instant both named; once one half moves it, neither promise stands.

    The acceptance row is left where it is — it records that this person did agree to that moment —
    but the card reports no plan, because the pair now has two different instants on it.
    """
    a, b, match_id, idea = pair_with_an_idea_in_chat
    first, second = _whole_hour(48), _whole_hour(96)
    assert (await _offer(client, a["token"], match_id, idea, first))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, first))[0] == 204
    assert _card(await _page(client, a["token"], match_id), idea)["agreed_time"] is not None
    assert (await _offer(client, a["token"], match_id, idea, second))[0] == 204

    mine = _card(await _page(client, a["token"], match_id), idea)
    theirs = _card(await _page(client, b["token"], match_id), idea)
    assert mine["agreed_time"] is None and theirs["agreed_time"] is None, (
        "the page still showed a plan for a moment one half has taken back"
    )
    assert _parsed(mine, "my_meeting_time") == second
    assert _parsed(theirs, "i_accepted_time") == first, (
        "the acceptance was rewritten when the other half moved their offer"
    )


async def test_a_pair_naming_two_different_hours_has_no_plan(
    client: AsyncClient, pair_with_an_idea_in_chat
):
    """Two offers, neither of them taken, is a conversation, not a promise.

    This is the case `_agreed_instant` refuses to decide between: each half holds a different instant
    and neither has agreed to the other's, so the rows support two different «договорились» and the
    honest answer is the one that claims neither. The card shows both proposals and no plan line;
    folding the two into the earlier instant would print a meeting one of them has never accepted.

    It used to be pinned with a different pair of taps — offer, accept, offer, accept — whose last
    answer genuinely does land both halves on one instant. That chronology read as no plan only
    because the mover's stale acceptance kept the *first* hour agreed beside the second offer, which
    is the reading `set_meeting_time` now withdraws; what the pair that ends on one accepted hour has
    is a plan, and `test_a_moved_hour_the_pair_accepts_is_the_plan` says so.
    """
    a, b, match_id, idea = pair_with_an_idea_in_chat
    first, second = _whole_hour(48), _whole_hour(96)
    assert await _send(client, b["token"], match_id, idea) in (200, 204)
    assert (await _offer(client, a["token"], match_id, idea, first))[0] == 204
    assert (await _offer(client, b["token"], match_id, idea, second))[0] == 204

    mine = _card(await _page(client, a["token"], match_id), idea)
    theirs = _card(await _page(client, b["token"], match_id), idea)
    assert mine["agreed_time"] is None and theirs["agreed_time"] is None
    assert _parsed(mine, "my_meeting_time") == first
    assert _parsed(mine, "partner_meeting_time") == second
    assert _parsed(mine, "i_accepted_time") is None


async def test_a_moved_hour_the_pair_accepts_is_the_plan(
    client: AsyncClient, pair_with_an_idea_in_chat
):
    """A pair that moved an evening and accepted the move stands on the new one, from either half.

    The mover here is the half who had only ever agreed, and the tap that follows is the other half
    accepting the moved instant. Two promises in order, each taken by the other: what the rows hold at
    the end is one instant both halves point at, and a card that read it as no plan was reading the
    mover's withdrawn acceptance as though it still stood.
    """
    a, b, match_id, idea = pair_with_an_idea_in_chat
    first, second = _whole_hour(48), _whole_hour(96)
    assert await _send(client, b["token"], match_id, idea) in (200, 204)
    assert (await _offer(client, a["token"], match_id, idea, first))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, first))[0] == 204
    assert (await _offer(client, b["token"], match_id, idea, second))[0] == 204
    assert _card(await _page(client, a["token"], match_id), idea)["agreed_time"] is None, (
        "the hour the pair stood on still read as agreed after the half who agreed to it moved away"
    )
    assert (await _accept(client, a["token"], match_id, idea, second))[0] == 204

    mine = _card(await _page(client, a["token"], match_id), idea)
    theirs = _card(await _page(client, b["token"], match_id), idea)
    assert _parsed(mine, "agreed_time") == second
    assert _parsed(theirs, "agreed_time") == second
    # And the acceptance the mover withdrew is not left reading as a second promise: the new instant
    # is the only one anybody stands on, so exactly one plan is agreed rather than two.
    assert _parsed(theirs, "i_accepted_time") is None
    assert _parsed(mine, "my_meeting_time") == first


async def test_a_moment_in_the_past_is_refused(client: AsyncClient, pair_with_an_idea_in_chat):
    """A plan that has already happened is a write nobody can act on."""
    a, _b, match_id, idea = pair_with_an_idea_in_chat
    when = _whole_hour(-2)
    code, text = await _offer(client, a["token"], match_id, idea, when)
    assert code == 422, text
    assert _card(await _page(client, a["token"], match_id), idea)["my_meeting_time"] is None, (
        "the refused instant was stored anyway"
    )


async def test_a_moment_a_year_away_is_refused(client: AsyncClient, pair_with_an_idea_in_chat):
    """Beyond the horizon the product plans on, the card would promise a date nobody means."""
    a, _b, match_id, idea = pair_with_an_idea_in_chat
    code, text = await _offer(client, a["token"], match_id, idea, _whole_hour(24 * 420))
    assert code == 422, text


async def test_a_moment_without_a_zone_is_refused(client: AsyncClient, pair_with_an_idea_in_chat):
    """A wall clock with no offset names a different instant per city, so it is not accepted.

    Red on a schema that took a plain `datetime`: the naive value would be read back as UTC by one
    phone and shifted by the other, and the pair would see two times for one tap.
    """
    a, _b, match_id, idea = pair_with_an_idea_in_chat
    naive = _whole_hour(48).replace(tzinfo=None).isoformat()
    resp = await client.put(
        f"/api/v1/matches/{match_id}/recommendations/{idea}/time",
        json={"when": naive},
        headers=auth_headers(a["token"]),
    )
    assert resp.status_code == 422, resp.text
    assert _card(await _page(client, a["token"], match_id), idea)["my_meeting_time"] is None


async def test_agreeing_to_a_time_is_not_offering_the_idea(client: AsyncClient, pair_with_an_idea_in_chat):
    """The mark «выбрали эту идею» belongs to the message that went into the chat.

    Accepting a moment writes the same row a proposal writes, so the two columns could have been
    folded together — and then the half who only said «да, в 19:00» would be shown as having sent
    the idea, which is the defect stage 63 was opened to close.
    """
    a, b, match_id, idea = pair_with_an_idea_in_chat
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204

    theirs = _card(await _page(client, b["token"], match_id), idea)
    assert theirs["selected"] is False, "accepting a time marked the idea as this person's proposal"
    assert theirs["partner_selected"] is True
    mine = _card(await _page(client, a["token"], match_id), idea)
    assert mine["selected"] is True and mine["partner_selected"] is False


async def test_naming_a_time_takes_the_card_back_from_the_pushed_away_list(
    client: AsyncClient, pair_with_an_idea_in_chat
):
    """A person who arranges a meeting for an idea has not refused it.

    The two answers cannot both stand, and the tap is the later, more specific one, so the refusal
    is cleared rather than kept beside a plan the same card now carries.
    """
    a, _b, match_id, idea = pair_with_an_idea_in_chat
    untouched = next(
        c["activity"]["id"] for c in await _page(client, a["token"], match_id)
        if c["activity"]["id"] != idea
    )
    assert await _send(client, a["token"], match_id, untouched) in (200, 204)
    assert await _push(client, a["token"], match_id, untouched) in (200, 204)
    assert _card(await _page(client, a["token"], match_id), untouched)["declined"] is True
    assert (await _offer(client, a["token"], match_id, untouched, _whole_hour(48)))[0] == 204
    card = _card(await _page(client, a["token"], match_id), untouched)
    assert card["declined"] is False, (
        "the page reported a person who both refused this idea and arranged it"
    )


async def test_agreeing_to_a_time_takes_back_this_persons_own_refusal(
    client: AsyncClient, pair_with_an_idea_in_chat
):
    """Same rule from the other tap, on the half who had pushed the card away."""
    a, b, match_id, idea = pair_with_an_idea_in_chat
    when = _whole_hour(48)
    assert await _push(client, b["token"], match_id, idea) in (200, 204)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204
    card = _card(await _page(client, b["token"], match_id), idea)
    assert card["declined"] is False
    assert _parsed(card, "agreed_time") == when


async def test_a_plan_survives_the_page_being_rebuilt(client: AsyncClient, pair_with_an_idea_in_chat):
    """`?force=true` re-scores the catalogue and writes a new page; the taps are not in it.

    A fix that carried the instants through `recommendations.explanation` would be green on the
    cached read and lose the agreement here — which is the path a profile edit takes.
    """
    a, b, match_id, idea = pair_with_an_idea_in_chat
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204
    rebuilt = _card(await _page(client, a["token"], match_id, force=True), idea)
    assert _parsed(rebuilt, "agreed_time") == when, "rebuilding the page forgot a plan the pair made"


async def test_a_plan_of_one_pair_does_not_appear_on_another(client: AsyncClient):
    """The decision belongs to a pair, and so does the instant attached to it."""
    a = await _ready(client, "when2_a@befos.app", "Аня")
    b = await _ready(client, "when2_b@befos.app", "Боря")
    c = await _ready(client, "when2_c@befos.app", "Вова")
    first = await _pair(client, a, b)
    second = await _pair(client, a, c)
    first_cards = await _page(client, a["token"], first, force=True)
    second_cards = await _page(client, a["token"], second, force=True)
    shared = {card["activity"]["id"] for card in second_cards}
    common = [card["activity"]["id"] for card in first_cards if card["activity"]["id"] in shared]
    assert common, "the two pages share no card, so this comparison cannot be made"
    idea = common[0]
    when = _whole_hour(48)
    assert await _send(client, a["token"], first, idea) in (200, 204)
    assert (await _offer(client, a["token"], first, idea, when))[0] == 204

    assert _parsed(_card(await _page(client, a["token"], first), idea), "my_meeting_time") == when
    other = _card(await _page(client, a["token"], second), idea)
    assert other["my_meeting_time"] is None, "one pair's time was shown on another pair's page"
    assert other["agreed_time"] is None


async def test_a_time_for_an_idea_the_catalogue_does_not_know_is_refused(
    client: AsyncClient, pair_with_an_idea_in_chat
):
    """The id in the url is a claim about the catalogue, and the catalogue is the only answer."""
    a, _b, match_id, _idea = pair_with_an_idea_in_chat
    resp = await client.put(
        f"/api/v1/matches/{match_id}/recommendations/999999/time",
        json={"when": _whole_hour(48).isoformat()},
        headers=auth_headers(a["token"]),
    )
    assert resp.status_code == 404, resp.text


async def test_a_stranger_cannot_name_a_time_for_a_pairs_idea(
    client: AsyncClient, pair_with_an_idea_in_chat
):
    """A stranger is not in this pair, so the route answers 404 and writes nothing."""
    a, _b, match_id, idea = pair_with_an_idea_in_chat
    stranger = await _ready(client, "when_stranger@befos.app", "Гость")
    assert await _push(client, a["token"], match_id, idea) in (200, 204)
    code, _text = await _offer(client, stranger["token"], match_id, idea, _whole_hour(48))
    assert code == 404
    card = _card(await _page(client, a["token"], match_id), idea)
    assert card["my_meeting_time"] is None, "the offer landed even though the route refused"
    assert card["partner_meeting_time"] is None


async def test_a_dissolved_pair_has_no_card_to_arrange(client: AsyncClient, pair_with_an_idea_in_chat):
    """The preference row is a child of the match, so a dissolve takes the plan with it.

    Without the pair lock the write reaches a `match_id` that is already gone and the client gets a
    500 for a pair that simply no longer exists — the same class closed on the chat, purge and
    proposal routes.
    """
    a, b, match_id, idea = pair_with_an_idea_in_chat
    resp = await client.post(
        f"/api/v1/users/{b['user_id']}/block", json={}, headers=auth_headers(a["token"])
    )
    assert resp.status_code == 200, resp.text
    code, _text = await _offer(client, a["token"], match_id, idea, _whole_hour(48))
    assert code == 404
    code, _text = await _accept(client, a["token"], match_id, idea, _whole_hour(48))
    assert code == 404


async def test_the_plan_reads_back_the_same_way_twice(client: AsyncClient, pair_with_an_idea_in_chat):
    """Control: two reads of one state are one answer, so the screen has nothing to guess.

    Green before and after this change — a check on the shape of the new fields, not on a defect.
    """
    a, b, match_id, idea = pair_with_an_idea_in_chat
    when = _whole_hour(48)
    assert (await _offer(client, a["token"], match_id, idea, when))[0] == 204
    assert (await _accept(client, b["token"], match_id, idea, when))[0] == 204
    first = _card(await _page(client, a["token"], match_id), idea)
    second = _card(await _page(client, a["token"], match_id), idea)
    keys = ("my_meeting_time", "partner_meeting_time", "i_accepted_time", "agreed_time")
    assert [first.get(k) for k in keys] == [second.get(k) for k in keys]
    assert sorted(k for k in first if k.endswith("_time")) == sorted(keys)
