"""A tap that writes a record nobody reads is a tap that never happened.

`POST /matches/{match_id}/recommendations/{activity_id}/select` answers 204 and writes a row into
`activity_preferences` (`app/repositories/activity_repo.py`, `score = 1.0`). Nothing reads that row:
no route, no service, no screen, no query in the repository — the interest catalogue, the answer
vectors and the stored page are what the recommendation engine sees, and a recorded choice is in
none of them. So the tap has one visible effect, and it is the wrong one. The card stays on the
pair's page exactly where it was, the client keeps its own idea of what has been chosen only in the
ViewModel scoped to one visit to the tab (`RecommendationsViewModel.selected`), and the next time the
person opens that tab the same card reads as untouched — tapping it again sends «Идея для нас: X.
Что скажете?» into the pair's chat a second time. The comment above that send claims the recorded
choice feeds the next recommendation pass; it feeds nothing, because it is never read.

The record also forgets the one thing that makes it answerable. The route knows which pair the tap
belongs to — `match_id` is in the url — and drops it: the row is keyed on (user, activity) alone. A
choice made for one pair is therefore indistinguishable from the same choice made for another, which
is why a flag read out of this table cannot be shown on a second pair's page. The fix keeps the pair
the tap was made for and reads it back for the viewer who made it.

Three of these checks would also go green on a wrong fix — one that marks the card for the whole
pair, or one that marks it wherever its viewer has ever tapped — so they are named here: the flag
belongs to the requesting half, not to the other one, and not to a pair the tap was not made for.
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


def _flag(cards: list[dict], activity_id: int) -> object:
    card = next((c for c in cards if c["activity"]["id"] == activity_id), None)
    assert card is not None, f"the page no longer carries the card that was tapped: {cards}"
    return card.get("selected", "<absent>")


@pytest.fixture
async def tapped_pair(client: AsyncClient):
    a = await _ready(client, "tap_a@befos.app", "Аня")
    b = await _ready(client, "tap_b@befos.app", "Боря")
    match_id = await _pair(client, a, b)
    cards = await _page(client, a["token"], match_id, force=True)
    assert len(cards) >= 3, cards
    top = cards[0]["activity"]["id"]
    status = await _tap(client, a["token"], match_id, top)
    assert status in (200, 204), status
    return a, b, match_id, top


async def test_a_card_the_viewer_chose_comes_back_marked(client: AsyncClient, tapped_pair):
    """The record of the tap is readable from the page the tap came off.

    Red before the fix on the plain absence: the response has no field that could carry it, so
    `_flag` reports `<absent>` and the caller has no way to tell a chosen card from a fresh one.
    """
    a, _b, match_id, top = tapped_pair
    cards = await _page(client, a["token"], match_id)
    assert _flag(cards, top) is True, (
        "the page cannot say which card this person already chose, although the choice was written"
    )
    others = [c for c in cards if c["activity"]["id"] != top]
    assert all(_flag(cards, c["activity"]["id"]) is False for c in others), (
        "cards nobody tapped came back marked: "
        f"{[(c['activity']['slug'], _flag(cards, c['activity']['id'])) for c in others]}"
    )


async def test_the_choice_of_one_half_is_not_the_other_halfs(client: AsyncClient, tapped_pair):
    """The flag is the viewer's. A pair-level flag would hide the card from the partner's own view.

    Green would mean the write was read back per match rather than per (match, viewer) — the same
    page object served to both halves, which is what the stored `recommendations` rows are.
    """
    _a, b, match_id, top = tapped_pair
    partner_cards = await _page(client, b["token"], match_id)
    assert _flag(partner_cards, top) is False, (
        "the other half reads this card as their own choice; the flag belongs to the viewer who "
        f"tapped it (partner sees `{_flag(partner_cards, top)}`)"
    )


async def test_a_rebuilt_page_still_knows_what_the_viewer_chose(
    client: AsyncClient, tapped_pair
):
    """The choice lives in the record, not in the cached page.

    `?force=true` deletes the stored page and re-scores the catalogue, so a fix that carried the flag
    in `recommendations` would lose it exactly here — and the card would be tappable a second time
    right after a profile edit, which is the case the invalidation exists for.
    """
    a, _b, match_id, top = tapped_pair
    rebuilt = await _page(client, a["token"], match_id, force=True)
    assert _flag(rebuilt, top) is True, (
        "rebuilding the page forgot a choice that was written down"
    )


async def test_a_choice_made_for_one_pair_does_not_mark_another(client: AsyncClient):
    """The record is about this pair. A user with two matches proves it.

    Same three people, same interests, so both pages carry the same cards: a tap for pair A-B must
    leave the identical card in pair A-C unmarked. Red before the fix because nothing is read back at
    all; red on a user-level fix, because the row would carry no pair to filter on.
    """
    a = await _ready(client, "twice_a@befos.app", "Аня")
    b = await _ready(client, "twice_b@befos.app", "Боря")
    c = await _ready(client, "twice_c@befos.app", "Вова")
    first = await _pair(client, a, b)
    second = await _pair(client, a, c)
    first_cards = await _page(client, a["token"], first, force=True)
    second_cards = await _page(client, a["token"], second, force=True)
    shared = [card["activity"]["id"] for card in first_cards]
    common = [card["activity"]["id"] for card in second_cards if card["activity"]["id"] in shared]
    assert common, "the two pages share no card, so this comparison cannot be made"
    chosen = common[0]
    assert await _tap(client, a["token"], first, chosen) in (200, 204)

    assert _flag(await _page(client, a["token"], first), chosen) is True
    assert _flag(await _page(client, a["token"], second), chosen) is False, (
        "a card chosen for one pair came back chosen on another pair's page"
    )


async def test_the_flag_moves_nothing_else_on_the_page(client: AsyncClient, tapped_pair):
    """Control: reading the record back must not have re-ordered or re-priced the page.

    A second tap on the card that is already recorded is the case that could have gone wrong — the
    write is an `ON CONFLICT DO UPDATE`, and the page is rebuilt from the same rows. Green on the
    tree before the fix and on the tree after it: it is a check on the shape of the repair, not on
    the defect.
    """
    a, _b, match_id, top = tapped_pair
    before = [(c["activity"]["slug"], c["score"], c["position"]) for c in await _page(client, a["token"], match_id)]
    assert await _tap(client, a["token"], match_id, top) in (200, 204)
    after = [(c["activity"]["slug"], c["score"], c["position"]) for c in await _page(client, a["token"], match_id)]
    assert before == after, "tapping a card changed the page it sits on"
