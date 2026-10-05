"""§21/§22: what a profile row is allowed to say, and who is allowed to see it.

Two facts the rest of the product leans on. A mandatory answer stays mandatory after the
whitespace is stripped, otherwise the identity line of a card is a separator with nothing
on one side of it. And a profile that nobody ever filled in belongs to nobody else's deck:
registration writes a shell so every read has a row, and that shell carries a name taken
from the email, a placeholder birth date and no answers.
"""

from __future__ import annotations

from httpx import AsyncClient

from .conftest import auth_headers, complete_onboarding, register_and_auth


async def test_onboarding_refuses_a_city_that_is_only_whitespace(client: AsyncClient):
    creds = await register_and_auth(client, "dq-onb@befos.app")
    resp = await client.post(
        "/api/v1/users/me/onboarding",
        json={
            "name": "Город",
            "birth_date": "1995-02-02",
            "city": "   ",
            "gender": "female",
            "dating_goal": "relationship",
        },
        headers=auth_headers(creds["token"]),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["message"] == "City is required."

    me = await client.get("/api/v1/users/me", headers=auth_headers(creds["token"]))
    assert me.json()["city"] == ""


async def test_patch_refuses_a_city_erased_to_whitespace(client: AsyncClient):
    creds = await register_and_auth(client, "dq-patch@befos.app")
    await complete_onboarding(client, creds["token"], city="Казань")

    resp = await client.patch(
        "/api/v1/users/me", json={"city": " \t "}, headers=auth_headers(creds["token"])
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["message"] == "City cannot be empty."

    me = await client.get("/api/v1/users/me", headers=auth_headers(creds["token"]))
    assert me.json()["city"] == "Казань"


async def test_padded_answers_are_stored_without_the_padding(client: AsyncClient):
    creds = await register_and_auth(client, "dq-pad@befos.app")
    await complete_onboarding(client, creds["token"])

    resp = await client.patch(
        "/api/v1/users/me", json={"city": "  Сочи  "}, headers=auth_headers(creds["token"])
    )
    assert resp.status_code == 200
    assert resp.json()["city"] == "Сочи"

async def test_a_profile_that_never_finished_onboarding_is_not_a_card(client: AsyncClient):
    viewer = await register_and_auth(client, "dq-viewer@befos.app")
    await complete_onboarding(client, viewer["token"], name="Зря", gender="male")

    shell = await register_and_auth(client, "dq-shell-never-onboarded@befos.app")

    first = await client.get(
        "/api/v1/discover", params={"limit": 50}, headers=auth_headers(viewer["token"])
    )
    assert first.status_code == 200
    shown = [c["user_id"] for c in first.json()["items"]]
    assert shell["user_id"] not in shown, "a shell profile was served as somebody's card"

    # The same account once it has answered: the deck is a stored queue, so the newcomer
    # has to arrive through the refill that runs when the queue has nothing left.
    await complete_onboarding(client, shell["token"], name="Всё есть", gender="female")

    second = await client.get(
        "/api/v1/discover", params={"limit": 50}, headers=auth_headers(viewer["token"])
    )
    assert second.status_code == 200
    assert shell["user_id"] in [c["user_id"] for c in second.json()["items"]]
    card = next(c for c in second.json()["items"] if c["user_id"] == shell["user_id"])
    assert card["city"] == "Москва"
