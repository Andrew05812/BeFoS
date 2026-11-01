"""Свой аккаунт отвечает, закончен ли онбординг, — а не оставляет клиент угадывать по полям.

Приложение решает, куда послать человека после входа, по своей оценке «анкета заполнена». Пока она
строилась из полей, она расходилась с тем, что знает сервер: регистрация оставляет скорлупу с
именем из почты и целью `relationship`, поэтому «непустое имя + непустая цель» не отличает
зарегистрированного человека от прошедшего онбординг. А человек, который осознанно не назвал ни
одного интереса — право, закреплённое за ним на стадии 72.2, — под это правило не попадает вовсе:
клиент отправляет его обратно в форму, и до своей пары, переписки и планов он дойти не может.

Сервер про такого человека не гадает: `users.onboarding_completed_at` ставится один раз и является
тем же признаком, которым колода отсекает скорлупу. Здесь проверяется, что он доходит до владельца
аккаунта — и только до него.
"""

from __future__ import annotations

from httpx import AsyncClient

from .conftest import auth_headers, register_and_auth

ONBOARDING = {
    "name": "Аня",
    "birth_date": "1996-05-10",
    "city": "Москва",
    "gender": "female",
    "about": "Интеграционный тест",
    "dating_goal": "relationship",
    # Пустой список — это ответ, а не пропуск: онбординг принимает его и называет вслух.
    "interests": [],
    "lifestyle": {"smoking": "never", "alcohol": "rarely", "sport": "often"},
    "age_min": 20,
    "age_max": 45,
    "gender_preference": ["female", "male", "nonbinary", "other"],
}


async def _me(client: AsyncClient, token: str) -> dict:
    resp = await client.get("/api/v1/users/me", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_a_registered_shell_says_it_is_not_onboarded(client: AsyncClient) -> None:
    creds = await register_and_auth(client, "s125_gate.shell@befos.app")
    body = await _me(client, creds["token"])
    # Имя и цель у скорлупы уже есть — по полям её не отличить, и клиент по ним ошибается.
    assert body["name"], body
    assert body["dating_goal"] == "relationship", body
    assert body["onboarding_completed"] is False, body


async def test_onboarding_without_a_single_interest_is_still_onboarding(client: AsyncClient) -> None:
    creds = await register_and_auth(client, "s125_gate.silent@befos.app")
    resp = await client.post(
        "/api/v1/users/me/onboarding",
        json=ONBOARDING,
        headers=auth_headers(creds["token"]),
    )
    assert resp.status_code == 200, resp.text
    body = await _me(client, creds["token"])
    assert body["interests"] == [], body
    assert body["onboarding_completed"] is True, (
        "человек, не назвавший интересов, прошёл онбординг: клиент, читающий только поля, "
        "отправит его обратно в форму и лишит своей пары"
    )


async def test_a_stranger_reading_the_card_learned_nothing_about_the_gate(
    client: AsyncClient,
) -> None:
    owner = await register_and_auth(client, "s125_gate.owner@befos.app")
    resp = await client.post(
        "/api/v1/users/me/onboarding",
        json=ONBOARDING,
        headers=auth_headers(owner["token"]),
    )
    assert resp.status_code == 200, resp.text
    outsider = await register_and_auth(client, "s125_gate.outsider@befos.app")
    resp = await client.get(
        f"/api/v1/users/{owner['user_id']}", headers=auth_headers(outsider["token"])
    )
    assert resp.status_code == 200, resp.text
    card = resp.json()
    assert "onboarding_completed" not in card, (
        "признак прожитого онбординга — дело владельца аккаунта; чужая карточка не должна его "
        "носить ни в каком виде"
    )
