"""A match that both accepted must stay readable after one side presses «Скрыть из подбора».

The switch is a deck preference: its label in `SettingsScreen.kt` says hide *from matching*,
and the tests around it enforce exactly that — the candidate leaves the next page, and
`POST /users/{id}/like` / `pass` and the public card `GET /users/{id}` stop resolving the id,
because an id is not secret and was on somebody's screen a moment ago. None of that is a
request to erase a pair that already mutually agreed to talk.

`GET /matches/{match_id}` reached the peer through the deck's own rule, so the switch erased
the match detail while three sibling routes of the same screen kept answering about the same
person: the match list resolves profiles with a query that asks only whether the account was
deleted, the chat never consults `is_hidden`, and `GET /matches/{id}/compatibility` reads both
profiles directly. The API answered «Match not found» to the person who is in the pair. In the
shipped app `ChatViewModel.loadPartner` swallows that refusal, so what the user sees is a live
conversation whose header has dropped from the partner's name to the fallback «Чат».
"""

from __future__ import annotations

from fastapi import status
from httpx import AsyncClient

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth


async def _ready(client: AsyncClient, email: str, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def _matched_pair(client: AsyncClient) -> tuple[dict, dict, str]:
    a = await _ready(client, "hide_detail_a@befos.app", "Аня", "female")
    b = await _ready(client, "hide_detail_b@befos.app", "Боря", "male")
    await client.post(f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"]))
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    assert mutual.status_code == 200, mutual.text
    return a, b, mutual.json()["match_id"]


async def _hide(client: AsyncClient, creds: dict) -> None:
    resp = await client.post(
        "/api/v1/users/me/visibility", headers=auth_headers(creds["token"]), json={"hidden": True}
    )
    assert resp.status_code == 200, resp.text


async def test_a_member_still_opens_their_own_match_after_the_partner_hides(
    client: AsyncClient,
):
    """The four routes about one match have to agree for the person who is in it."""
    a, b, match_id = await _matched_pair(client)
    await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": "Привет, я из матча"},
        headers=auth_headers(a["token"]),
    )
    await _hide(client, b)

    detail = await client.get(f"/api/v1/matches/{match_id}", headers=auth_headers(a["token"]))
    assert detail.status_code == 200, detail.text
    assert detail.json()["other_user"]["user_id"] == b["user_id"]

    # Hiding does not blind the hider to their own pair either.
    own_side = await client.get(f"/api/v1/matches/{match_id}", headers=auth_headers(b["token"]))
    assert own_side.status_code == 200, own_side.text
    assert own_side.json()["other_user"]["user_id"] == a["user_id"]

    # The routes that never filtered on is_hidden keep answering, which is the whole point:
    # the screen is not being torn down, only its header was refusing to load.
    listed = await client.get("/api/v1/matches", headers=auth_headers(a["token"]))
    assert listed.status_code == 200
    assert [m["match_id"] for m in listed.json()["matches"]] == [match_id]

    compat = await client.get(
        f"/api/v1/matches/{match_id}/compatibility", headers=auth_headers(a["token"])
    )
    assert compat.status_code == 200, compat.text

    history = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(a["token"])
    )
    assert history.status_code == 200, history.text
    assert history.json()["messages"][0]["body"] == "Привет, я из матча"


async def test_hiding_still_works_for_the_same_person_outside_the_match(client: AsyncClient):
    """The exemption belongs to the match, not to the viewer.

    A, who is B's match, is still a stranger to B's card everywhere else: the public profile
    route keeps the deck's rule, so the switch remains enforceable against an id copied from a
    link or a screenshot.
    """
    a, b, match_id = await _matched_pair(client)
    await _hide(client, b)

    card = await client.get(
        f"/api/v1/users/{b['user_id']}", headers=auth_headers(a["token"])
    )
    assert card.status_code == status.HTTP_404_NOT_FOUND, card.text

    fresh = await _ready(client, "hide_detail_c@befos.app", "Вика", "female")
    like = await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(fresh["token"])
    )
    assert like.status_code == status.HTTP_404_NOT_FOUND, like.text


async def test_a_partner_still_disappears_from_the_match_when_the_account_is_deleted(
    client: AsyncClient,
):
    """Reading a live match is not the same as resurrecting an erased one.

    The exempted lookup still joins on `users.is_deleted`, and `delete_account` dissolves the
    match rows anyway, so the member gets the honest 404 here rather than a card of somebody
    who asked to be removed.
    """
    a, b, match_id = await _matched_pair(client)
    gone = await client.delete("/api/v1/users/me", headers=auth_headers(b["token"]))
    assert gone.status_code == 200, gone.text

    detail = await client.get(f"/api/v1/matches/{match_id}", headers=auth_headers(a["token"]))
    assert detail.status_code == status.HTTP_404_NOT_FOUND, detail.text

    listed = await client.get("/api/v1/matches", headers=auth_headers(a["token"]))
    assert [m["match_id"] for m in listed.json()["matches"]] == []
