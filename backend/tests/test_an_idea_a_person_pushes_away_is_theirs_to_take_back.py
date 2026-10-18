"""An idea a person pushes away is a decision, and a decision has to survive the next visit.

The ideas page could do one thing with a card: take it. `POST /matches/{id}/recommendations/
{activity_id}/select` wrote a row, the row's existence answered «я уже предлагал(а) этой паре эту
идею», and nothing else. A pair that is not interested therefore had no move left: the card kept its
place in the stored page, kept coming back after a rebuild, and the person who had already decided
about it had to scroll past it every time. §81 of the sprint names «отклонение» and «история» among
the actions this screen owes a person, and both are the same fact seen from either side — what was
pushed away, and where it went.

Two things make this smaller than it looks, and one makes it not-so-small:

The row is already keyed on (person, card, pair), so a refusal needs no new key. It does need a new
column, because the row's existence cannot mean two opposite things at once: a card whose proposal
went into the pair's chat and was then pushed away is one card carrying two facts, and flattening
them would let the page offer a second copy of a message the chat already has — the exact defect
stage 63 closed.

The read stays one statement: `decisions_by_pair` asks the table for both columns of both people in
the same `SELECT` the choice-invariant already counts, so the warm page keeps its five round trips
and the rebuilt one its twelve.

What is refused stays on the page that reports it. Filtering declined cards out of the response
would hide the decision the §81 history asks for and leave it unreversible — there would be no card
on screen to tap «Вернуть» — so the answer is the flag `declined`, which belongs to the reader the
same way `selected` does.

A refusal is not named to the other half. A proposal is a message the pair received, so reporting it
back carries nothing new; a refusal never left the person's own list, and saying «партнёр отклонил»
would turn an edit of one's own page into a statement about them that no conversation in this
product carries. These checks pin that boundary too, because it is a product decision and not an
accident of the query.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

INTERESTS = ["volunteering", "cinema", "board_games"]


async def _ready(client: AsyncClient, email: str, name: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, interests=list(INTERESTS))
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


async def _tap(client: AsyncClient, token: str, match_id: str, activity_id: int) -> int:
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


async def _bring_back(client: AsyncClient, token: str, match_id: str, activity_id: int) -> int:
    resp = await client.delete(
        f"/api/v1/matches/{match_id}/recommendations/{activity_id}/decline",
        headers=auth_headers(token),
    )
    return resp.status_code


def _card(cards: list[dict], activity_id: int) -> dict:
    card = next((c for c in cards if c["activity"]["id"] == activity_id), None)
    assert card is not None, f"the page no longer carries the card: {[c['activity']['id'] for c in cards]}"
    return card


@pytest.fixture
async def pair_with_a_second_card(client: AsyncClient):
    """A pair that has met, with the second card of the page pushed away by the first half."""
    a = await _ready(client, "push_a@befos.app", "Аня")
    b = await _ready(client, "push_b@befos.app", "Боря")
    match_id = await _pair(client, a, b)
    cards = await _page(client, a["token"], match_id, force=True)
    assert len(cards) >= 3, cards
    pushed = cards[1]["activity"]["id"]
    assert await _push(client, a["token"], match_id, pushed) in (200, 204)
    return a, b, match_id, pushed


async def test_a_pushed_idea_is_named_as_pushed_on_the_page_of_the_person_who_pushed_it(
    client: AsyncClient, pair_with_a_second_card
):
    """The decision survives the next visit to the tab, which is the whole point of recording it.

    Red before this change on the plain absence: the response carried no field that could hold a
    refusal, because the screen had no way to make one.
    """
    a, _b, match_id, pushed = pair_with_a_second_card
    cards = await _page(client, a["token"], match_id)
    card = _card(cards, pushed)
    assert card.get("declined", "<absent>") is True, "the page cannot say this idea was pushed away"
    assert card["selected"] is False, (
        "a refusal came back as a proposal: the two are different answers to different questions"
    )
    others = [c for c in cards if c["activity"]["id"] != pushed]
    assert all(c.get("declined") is False for c in others), (
        "cards nobody refused are reported as refused: "
        f"{[(c['activity']['slug'], c.get('declined')) for c in others]}"
    )


async def test_a_pushed_idea_is_not_reported_to_the_other_half(
    client: AsyncClient, pair_with_a_second_card
):
    """The partner's page answers for their own decisions only.

    This is the boundary the change could easily cross: one `SELECT` reads both halves' rows, and a
    `partner_declined` field would be free. It is refused here because a refusal never went into the
    pair's chat, so naming it would tell the partner something nobody said to them.
    """
    _a, b, match_id, pushed = pair_with_a_second_card
    cards = await _page(client, b["token"], match_id)
    card = _card(cards, pushed)
    assert card["declined"] is False, "the refusal of one half was read back to the other"
    assert card["selected"] is False
    assert not any(key.endswith("declined") and key != "declined" for key in card), (
        f"the page grew a second refusal field, which would name one half's edit to the other: "
        f"{sorted(card)}"
    )


async def test_a_refusal_taken_back_puts_the_card_where_it_was(client: AsyncClient, pair_with_a_second_card):
    """Undo is a decision too, and the only one that lets a person change their mind by tap."""
    a, _b, match_id, pushed = pair_with_a_second_card
    assert await _bring_back(client, a["token"], match_id, pushed) in (200, 204)
    card = _card(await _page(client, a["token"], match_id), pushed)
    assert card["declined"] is False
    assert card["selected"] is False, (
        "bringing a card back marked it as proposed — no message ever went into the chat"
    )


async def test_an_idea_already_proposed_keeps_its_proposal_after_being_pushed_away(
    client: AsyncClient, pair_with_a_second_card
):
    """Both answers at once: the sentence is in the pair's chat, and the card is refused.

    Red on the wrong repair that folds the two into one flag — then the refused card loses its mark,
    comes back offering «Предложить в чате», and the chat reads the same sentence twice. That is the
    defect stage 63 closed, arriving back through the side door.

    The two taps are made in the order a person changes their mind in: the card that was pushed away
    is proposed to, and then pushed away again. The proposal mark survives the second tap, while the
    refusal of a card somebody has just put to the pair is what the pair's plan reads as their answer
    — see `test_the_half_that_confirmed_can_still_say_no`.
    """
    a, _b, match_id, pushed = pair_with_a_second_card
    assert await _tap(client, a["token"], match_id, pushed) in (200, 204)
    assert await _push(client, a["token"], match_id, pushed) in (200, 204)
    card = _card(await _page(client, a["token"], match_id), pushed)
    assert card["selected"] is True and card["declined"] is True, (
        f"one of the two answers was lost: {card}"
    )


async def test_a_refusal_survives_the_page_being_rebuilt(client: AsyncClient, pair_with_a_second_card):
    """`?force=true` re-scores the catalogue and writes a new page; the taps are not in it.

    A fix that carried the flag through `recommendations.explanation` would be green on the cached
    read and lose the refusal here — which is the path a profile edit takes.
    """
    a, _b, match_id, pushed = pair_with_a_second_card
    rebuilt = await _page(client, a["token"], match_id, force=True)
    assert _card(rebuilt, pushed)["declined"] is True, (
        "rebuilding the page forgot a decision the reader had written down"
    )


async def test_a_refusal_in_one_pair_does_not_push_the_card_out_of_another(client: AsyncClient):
    """Same card, same two interest lists, different pair: the decision belongs to one pair.

    A row written without its `match_id`, or a read keyed on the person alone, passes the tests
    above and fails here.
    """
    a = await _ready(client, "push2_a@befos.app", "Аня")
    b = await _ready(client, "push2_b@befos.app", "Боря")
    c = await _ready(client, "push2_c@befos.app", "Вова")
    first = await _pair(client, a, b)
    second = await _pair(client, a, c)
    first_cards = await _page(client, a["token"], first, force=True)
    second_cards = await _page(client, a["token"], second, force=True)
    shared = {card["activity"]["id"] for card in second_cards}
    common = [card["activity"]["id"] for card in first_cards if card["activity"]["id"] in shared]
    assert common, "the two pages share no card, so this comparison cannot be made"
    chosen = common[0]
    assert await _push(client, a["token"], first, chosen) in (200, 204)

    assert _card(await _page(client, a["token"], first), chosen)["declined"] is True
    assert _card(await _page(client, a["token"], second), chosen)["declined"] is False, (
        "one pair's refusal was shown on another pair's page"
    )


async def test_a_refusal_of_a_card_the_page_never_offered_is_refused_not_fictional(
    client: AsyncClient, pair_with_a_second_card
):
    """The id in the url is a claim about the catalogue, and the catalogue is the only answer.

    Before the check existed, an id of no activity reached a foreign key and the client got a 500
    for a url that simply does not name anything.
    """
    a, _b, match_id, _pushed = pair_with_a_second_card
    resp = await client.post(
        f"/api/v1/matches/{match_id}/recommendations/999999/decline",
        headers=auth_headers(a["token"]),
    )
    assert resp.status_code == 404, resp.status_code


async def test_a_stranger_cannot_push_a_pairs_idea_away(client: AsyncClient, pair_with_a_second_card):
    """The guard is the one every match route uses: a stranger is not in this pair, so 404.

    Red on a route that took `match_id` and wrote without asking who holds it. The card the stranger
    aims at is one nobody has refused yet, so the assertion after the refusal is about this write
    rather than about the one the fixture made.
    """
    stranger = await _ready(client, "push_stranger@befos.app", "Гость")
    a, _b, match_id, pushed = pair_with_a_second_card
    untouched = next(
        c["activity"]["id"] for c in await _page(client, a["token"], match_id)
        if c["activity"]["id"] != pushed
    )
    resp = await client.post(
        f"/api/v1/matches/{match_id}/recommendations/{untouched}/decline",
        headers=auth_headers(stranger["token"]),
    )
    assert resp.status_code == 404, resp.status_code
    assert _card(await _page(client, a["token"], match_id), untouched)["declined"] is False, (
        "the refusal landed even though the route refused"
    )


async def test_the_refusal_moves_nothing_else_on_the_page(client: AsyncClient, pair_with_a_second_card):
    """Control: recording a refusal must not re-order, re-price or drop any card.

    Green before and after this change — a check on the shape of it, not on the defect.
    """
    a, _b, match_id, pushed = pair_with_a_second_card
    cards = await _page(client, a["token"], match_id)
    after = await _page(client, a["token"], match_id, force=True)
    assert [(c["activity"]["id"], c["position"]) for c in cards if c["activity"]["id"] != pushed] == [
        (c["activity"]["id"], c["position"]) for c in after if c["activity"]["id"] != pushed
    ], "the cards nobody refused changed place or price under a read that only reports more of it"
    assert _card(cards, pushed)["declined"] is True
