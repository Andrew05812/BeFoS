"""The role an account reads about itself, and the choices a complaint still leaves open.

Stage 102 built the moderation surface and left it without a client half: `docs/OPERATIONS.md` §14
named three routes, and the only reader of the queue was somebody holding `psql`. Stage 103 puts a
screen in front of those routes, and that screen needs two answers the API did not give out.

The first is whether the account looking at the screen may open it at all. Nothing in the tree told
an account about its own role — `UserBrief` carried the email and the activation flag, `ProfileOut`
carried the profile — so a client could only learn the answer by walking into a door and being
refused. This file pins the new word on the owner's own profile, `is_moderator`, and pins the
boundary around it: the flag travels only with the answer about the account that asked, it is read
off the row the door reads, no write to the profile can put it there, and somebody else's card does
not carry it.

The second is what a complaint may still be moved to. The transition table lives in the service, and
a client drawing its own buttons would drift from it the first time a transition is closed off — the
drift would show up as a tap that can only ever be refused. So `GET /reports/{report_id}` now answers
with `allowed_next_statuses`, and the last test here checks that table against the write route from
both sides: every status the detail names is accepted, and a status it does not name is refused by
name.
"""

from __future__ import annotations

from httpx import AsyncClient

from .conftest import auth_headers
from .test_a_moderator_reads_the_queue_and_closes_a_complaint import (
    _account,
    _complaint_against,
    _decide,
    _detail,
    _grant_moderator_role,
    _moderator,
    _page,
)

ME = "/api/v1/users/me"


async def _own_answer(client: AsyncClient, account: dict) -> dict:
    response = await client.get(ME, headers=auth_headers(account["token"]))
    assert response.status_code == 200, response.text
    return response.json()


async def _one_complaint(client: AsyncClient, keeper: dict, tag: str) -> dict:
    """A complaint on its own pair of accounts, so one test can hold several of them.

    The sibling's helper fixes the reporter's address, which is right for a test that files once and
    wrong for a test that walks the transition table: three complaints from one reporter are a
    duplicate registration the moment the second one is written.
    """
    reporter = await _account(client, f"witness-{tag}@befos.app", "Свидетель")
    accused = await _account(client, f"accused-{tag}@befos.app", "Обвиняемый")
    filed = await client.post(
        f"/api/v1/users/{accused['user_id']}/report",
        json={"reason": "spam"},
        headers=auth_headers(reporter["token"]),
    )
    assert filed.status_code == 200, filed.text
    rows = await _page(client, keeper)
    return next(row for row in rows if row["reported"]["user_id"] == accused["user_id"])


async def test_the_account_that_is_not_a_moderator_hears_that_about_itself(client: AsyncClient):
    account = await _account(client, "plain@befos.app", "Обычный")
    answer = await _own_answer(client, account)
    assert "is_moderator" in answer
    assert answer["is_moderator"] is False


async def test_the_role_the_profile_names_and_the_door_of_the_queue_read_the_same_row(
    client: AsyncClient,
):
    """The answer is not a second source of truth, so it cannot disagree with the door.

    A client that draws its entry from one place and is stopped by another is a client that shows a
    door to the person it just refused and hides it from the one it would let in. Both halves here
    read `users.is_moderator` per request, so the flag moving under one account moves both at once.
    """
    account = await _account(client, "switch@befos.app", "Ревизор")
    assert (await _own_answer(client, account))["is_moderator"] is False
    assert (
        await client.get("/api/v1/reports", headers=auth_headers(account["token"]))
    ).status_code == 403

    await _grant_moderator_role(account["user_id"])
    assert (await _own_answer(client, account))["is_moderator"] is True
    assert (
        await client.get("/api/v1/reports", headers=auth_headers(account["token"]))
    ).status_code == 200

    await _grant_moderator_role(account["user_id"], moderator=False)
    assert (await _own_answer(client, account))["is_moderator"] is False
    assert (
        await client.get("/api/v1/reports", headers=auth_headers(account["token"]))
    ).status_code == 403


async def test_no_write_to_the_profile_can_give_the_account_the_role(client: AsyncClient):
    """The flag is an answer, never an input — so mass-assigning it stays a dead end.

    The body is sent with the field in it because that is what an attacker's client looks like, and
    the answer has to be the account's own row rather than whatever the request claimed. `Pydantic`
    drops the unknown key, and the row is written by `ProfileService` from the fields it declares.
    """
    account = await _account(client, "climber@befos.app", "Претендент")
    response = await client.patch(
        ME, json={"is_moderator": True}, headers=auth_headers(account["token"])
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_moderator"] is False
    assert (await _own_answer(client, account))["is_moderator"] is False
    assert (
        await client.get("/api/v1/reports", headers=auth_headers(account["token"]))
    ).status_code == 403


async def test_the_role_does_not_travel_with_an_answer_about_somebody_else(client: AsyncClient):
    """A card of a moderator says nothing about its owner being one.

    The queue is a role, not a badge: telling every reader which accounts hold it hands an attacker
    the list of accounts worth compromising, and it tells a reported person who will be reading their
    complaint. The owner's own answer carries the flag; a third party's card does not.
    """
    keeper = await _moderator(client, "keeper@befos.app")
    stranger = await _account(client, "stranger@befos.app", "Посторонний")

    card = await client.get(
        f"/api/v1/users/{keeper['user_id']}", headers=auth_headers(stranger["token"])
    )
    assert card.status_code == 200, card.text
    assert "is_moderator" not in card.json()

    # Even reading one's own card through that route gives the answer the owner's route gives: the
    # flag is not on this schema at all, so a caller cannot pick which of the two it wants.
    self_card = await client.get(
        f"/api/v1/users/{keeper['user_id']}", headers=auth_headers(keeper["token"])
    )
    assert "is_moderator" not in self_card.json()
    assert (await _own_answer(client, keeper))["is_moderator"] is True


async def test_a_complaint_that_is_still_open_names_the_statuses_it_can_be_moved_to(
    client: AsyncClient,
):
    filed = await _complaint_against(client)
    keeper = await _moderator(client, "opener@befos.app")
    detail = await _detail(client, keeper, filed["card"]["id"])

    assert detail["status"] == "open"
    assert detail["allowed_next_statuses"] == ["dismissed", "resolved", "reviewed"]


async def test_a_closed_complaint_names_no_status_it_can_be_moved_to(client: AsyncClient):
    """A dead end says so in the answer instead of leaving the caller to find out by tapping.

    The two closed statuses stay closed on purpose — the history already records the verdict — so the
    screen that draws the decision has nothing to draw here but the rows that say how it ended.
    """
    filed = await _complaint_against(client)
    keeper = await _moderator(client, "closer@befos.app")
    closed = await _decide(client, keeper, filed["card"]["id"], "resolved", "Аккаунт удалён.")
    assert closed.status_code == 200, closed.text

    detail = await _detail(client, keeper, filed["card"]["id"])
    assert detail["status"] == "resolved"
    assert detail["allowed_next_statuses"] == []
    assert [row["to_status"] for row in detail["reviews"]] == ["resolved"]


async def test_every_status_the_detail_names_is_one_the_write_route_accepts(client: AsyncClient):
    """The list is the table read out loud, not a copy of it that is free to drift.

    Each status is asked for on its own complaint, so an accepted move here is a move the row really
    took rather than one the route agreed to consider.
    """
    keeper = await _moderator(client, "checker@befos.app")
    for target in ("reviewed", "resolved", "dismissed"):
        card = await _one_complaint(client, keeper, target)
        named = (await _detail(client, keeper, card["id"]))["allowed_next_statuses"]
        assert target in named, (target, named)
        answer = await _decide(client, keeper, card["id"], target, "Проверено.")
        assert answer.status_code == 200, answer.text
        assert answer.json()["status"] == target


async def test_a_status_the_detail_does_not_name_is_the_one_the_write_route_refuses(
    client: AsyncClient,
):
    """The other side of the same check: what the answer leaves out is what the route turns down.

    `reviewed` may be closed but never reopened, so a client that drew its choices from this answer
    has no tap that ends in the refusal this one asserts.
    """
    filed = await _complaint_against(client)
    keeper = await _moderator(client, "strict@befos.app")
    report_id = filed["card"]["id"]

    assert (await _decide(client, keeper, report_id, "reviewed")).status_code == 200
    detail = await _detail(client, keeper, report_id)
    assert detail["status"] == "reviewed"
    assert detail["allowed_next_statuses"] == ["dismissed", "resolved"]

    refused = await _decide(client, keeper, report_id, "open", "Вернуть в очередь.")
    assert refused.status_code == 422, refused.text
    assert "cannot move" in refused.json()["error"]["message"]
