"""An idea one half of the pair chose is a fact the other half's page was throwing away.

`activity_preferences` records a tap under three columns: who tapped, what they tapped, and which
pair it was for (`app/models/activity.py`, since stage 63 kept the pair). `GET
/matches/{id}/recommendations` read it back filtered on the viewer alone — `chosen_activity_ids(user_id,
match_id, ...)`, one `WHERE user_id = ...` — and so answered exactly one of the two questions the
table can answer about this pair. The other half's rows were read out of the database and dropped:
the page a person opened named their own taps and stayed silent about the partner's, although the
partner's tap had already put «Идея для нас: X. Что скажете?» into that same pair's chat
(`RecommendationsViewModel.select`). So the pair could not see agreement. Both halves choosing the
same evening looked, on each of their screens, like one person proposing and one person silent — and
the card that both had chosen offered «Предложить в чате» to the second one, whose tap would send a
third copy of a sentence the chat already carries twice.

Nothing here is a secret being lifted: the row is the pair's own, readable only by the two people
`_require_match` admits to this `match_id`, and its content is a message the reader already received.

These checks are red on the wrong repairs, which is why they are separated: a flag folded to the
pair (both halves marked whenever either tapped) passes the agreement test and fails the one that
keeps the viewer's own flag their own; a flag keyed on the person rather than the pair passes both
and fails the one about a second pair.
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


def _card(cards: list[dict], activity_id: int) -> dict:
    card = next((c for c in cards if c["activity"]["id"] == activity_id), None)
    assert card is not None, f"the page no longer carries the card that was tapped: {cards}"
    return card


@pytest.fixture
async def pair_with_one_chosen_card(client: AsyncClient):
    """A pair whose top card the second half has chosen and the first half has not."""
    a = await _ready(client, "agree_a@befos.app", "Аня")
    b = await _ready(client, "agree_b@befos.app", "Боря")
    match_id = await _pair(client, a, b)
    cards = await _page(client, a["token"], match_id, force=True)
    assert len(cards) >= 3, cards
    top = cards[0]["activity"]["id"]
    assert await _tap(client, b["token"], match_id, top) in (200, 204)
    return a, b, match_id, top


@pytest.fixture
async def tapped_solo(client: AsyncClient):
    """The same pair, with the top card chosen by the first half instead of the second."""
    a = await _ready(client, "solo2_a@befos.app", "Аня")
    b = await _ready(client, "solo2_b@befos.app", "Боря")
    match_id = await _pair(client, a, b)
    cards = await _page(client, a["token"], match_id, force=True)
    top = cards[0]["activity"]["id"]
    assert await _tap(client, a["token"], match_id, top) in (200, 204)
    return a, b, match_id, top


async def test_the_partners_choice_is_named_on_my_page(client: AsyncClient, pair_with_one_chosen_card):
    """The reader sees the other half's tap, and their own state unchanged.

    Red before this change on the plain absence: the response carried no field that could hold it.
    """
    a, _b, match_id, top = pair_with_one_chosen_card
    cards = await _page(client, a["token"], match_id)
    assert _card(cards, top).get("partner_selected", "<absent>") is True, (
        "the page still cannot say that the other half chose this idea"
    )
    assert _card(cards, top)["selected"] is False, (
        "the partner's choice was written as the viewer's own; the two flags are different answers"
    )
    others = [c for c in cards if c["activity"]["id"] != top]
    assert all(c.get("partner_selected") is False for c in others), (
        "cards nobody tapped came back as the partner's: "
        f"{[(c['activity']['slug'], c.get('partner_selected')) for c in others]}"
    )


async def test_my_own_choice_is_not_reported_as_my_partners(client: AsyncClient, tapped_solo):
    """A flag folded to the pair would mark both halves from either tap. This one says no.

    The stored page is shared by the pair, so the temptation is to read it back per match; the tap
    is per person, and the card has to keep the two apart to show agreement rather than one voice.
    """
    a, _b, match_id, top = tapped_solo
    cards = await _page(client, a["token"], match_id)
    assert _card(cards, top)["selected"] is True
    assert _card(cards, top).get("partner_selected") is False, (
        "the viewer's own tap came back as the partner's"
    )


async def test_a_card_both_halves_chose_is_marked_both_ways(client: AsyncClient, pair_with_one_chosen_card):
    """The agreement the page exists to show: the same card chosen by each of them.

    Red if the read answers for one person only, which is what it did — then the second half's
    screen would say the idea is theirs alone, and the first half's would say nobody seconded it.
    """
    a, b, match_id, top = pair_with_one_chosen_card
    assert await _tap(client, a["token"], match_id, top) in (200, 204)
    for token in (a["token"], b["token"]):
        cards = await _page(client, token, match_id)
        card = _card(cards, top)
        assert card["selected"] is True and card.get("partner_selected") is True, (
            f"an idea both halves chose is not shown that way to one of them: {card}"
        )


async def test_a_rebuilt_page_still_names_the_partners_choice(
    client: AsyncClient, pair_with_one_chosen_card
):
    """`?force=true` re-scores the catalogue and writes a new page; the taps are not in it.

    A fix that carried the partner's flag through `recommendations.explanation` would be green on
    the cached read and lose the agreement right here, which is the path a profile edit takes.
    """
    a, _b, match_id, top = pair_with_one_chosen_card
    rebuilt = await _page(client, a["token"], match_id, force=True)
    assert _card(rebuilt, top).get("partner_selected") is True, (
        "rebuilding the page forgot a choice the other half had written down"
    )


async def test_a_choice_made_in_one_pair_does_not_mark_another(client: AsyncClient):
    """The partner whose choice is named is this pair's partner, not anyone I matched with.

    A-C's page must not report Боря's tap on the A-B card, although the card, the activity id and
    the interest lists are the same on both pages.
    """
    a = await _ready(client, "solo_a@befos.app", "Аня")
    b = await _ready(client, "solo_b@befos.app", "Боря")
    c = await _ready(client, "solo_c@befos.app", "Вова")
    first = await _pair(client, a, b)
    second = await _pair(client, a, c)
    first_cards = await _page(client, a["token"], first, force=True)
    second_cards = await _page(client, a["token"], second, force=True)
    shared = [card["activity"]["id"] for card in second_cards]
    common = [card["activity"]["id"] for card in first_cards if card["activity"]["id"] in shared]
    assert common, "the two pages share no card, so this comparison cannot be made"
    chosen = common[0]
    assert await _tap(client, b["token"], first, chosen) in (200, 204)

    assert _card(await _page(client, a["token"], first), chosen).get("partner_selected") is True
    assert _card(await _page(client, a["token"], second), chosen).get("partner_selected") is False, (
        "one partner's choice was shown on another pair's page"
    )


async def test_the_partners_flag_moves_nothing_else_on_the_page(
    client: AsyncClient, pair_with_one_chosen_card
):
    """Control: reading the second half's taps back must not re-order or re-price the page.

    Green before and after — a check on the shape of the change, not on the defect it fixes.
    """
    a, _b, match_id, top = pair_with_one_chosen_card
    cards = await _page(client, a["token"], match_id)
    assert [(c["activity"]["slug"], c["score"], c["position"], c["selected"]) for c in cards] == [
        (c["activity"]["slug"], c["score"], c["position"], c["selected"])
        for c in await _page(client, a["token"], match_id, force=True)
    ], "the page changed under a read that only reports more of it"
    assert _card(cards, top)["selected"] is False
