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
