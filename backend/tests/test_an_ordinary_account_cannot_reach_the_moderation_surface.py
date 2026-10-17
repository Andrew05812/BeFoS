"""The moderation door, tested from the outside: nobody else opens it, and nothing writes the key.

Stage 102's other file reads the queue from behind `get_moderator` and checks that what it sees is
right. This one checks that the door is the only way in, which is the half the brief cares about more
than the feature itself: «нельзя полагаться на скрытие кнопок в Android» — a client that hides a
button is a client that hides a button, and the route beside it would still answer if the backend
let it. So every promise here is a refusal:

* an anonymous caller is turned away before the row is looked at, and a signed-in ordinary account
  is turned away the same way whatever the identifier in the path names — a real complaint's id and
  a random one answer alike, so the queue cannot be used to ask whether a report exists;
* no route in the application writes `users.is_moderator`. Registration, onboarding and the profile
  patch are handed the field anyway and none of them takes it, which is what mass assignment looks
  like from the side of a client that hopes for it;
* the hand that decides is the session that authenticated. A body carrying another moderator's id
  changes whose name lands in the history and nothing else;
* the role is read off the row per request, so taking it away stops the account at the next call
  with the same token it was already using;
* the complaint budget is spent on the attempt, not on the row, and the complaint plus its history
  outlive both accounts they name.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import Report, ReportReview, User
from .conftest import auth_headers, register_and_auth
from .test_a_moderator_reads_the_queue_and_closes_a_complaint import (
    ALL_REASONS,
    QUEUE,
    _account,
    _complaint_against,
    _decide,
    _file,
    _grant_moderator_role,
    _history,
    _moderator,
    _row,
)

# The three routes stage 102 mounts, in the shape a caller meets them in. `GET /reports` takes no
# identifier, so it is listed apart: the queue answers 401/403 with no row named at all.
_ANON_CALLS = [
    ("GET", QUEUE, None),
    ("GET", f"{QUEUE}/{uuid.uuid4()}", None),
    ("POST", f"{QUEUE}/{uuid.uuid4()}/review", {"status": "resolved", "comment": "let me in"}),
]


async def _is_moderator_row(user_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        return bool(
            (
                await session.execute(
                    select(User.is_moderator).where(User.id == uuid.UUID(user_id))
                )
            ).scalar_one()
        )


async def test_an_anonymous_caller_is_turned_away_from_every_moderation_route(
    client: AsyncClient,
) -> None:
    """The queue is not a public read, whatever else the deployment serves anonymously."""
    for method, path, payload in _ANON_CALLS:
        response = await client.request(method, path, json=payload or {})
        assert response.status_code == 401, f"{method} {path} -> {response.status_code}: {response.text}"
        assert response.json()["error"]["code"] == "unauthorized"


async def test_an_ordinary_account_is_turned_away_from_every_moderation_route(
    client: AsyncClient,
) -> None:
    """A token that works everywhere else in the app is not a key to this door.

    403 rather than 401: the session is valid and the permission is missing, and a client that
    conflated the two would refresh a token in front of a door no token opens.
    """
    ordinary = await _account(client, "curious@befos.app", "Любопытный")
    headers = auth_headers(ordinary["token"])
    for method, path, payload in _ANON_CALLS:
        response = await client.request(method, path, json=payload or {}, headers=headers)
        assert response.status_code == 403, f"{method} {path} -> {response.status_code}: {response.text}"
        assert response.json()["error"]["code"] == "forbidden"
        assert response.json()["error"]["message"] == "Moderator role is required."

    body = (await client.get(QUEUE, headers=headers)).json()
    assert set(body) <= {"error"}, f"the refusal came back with rows attached: {sorted(body)}"


async def test_the_refusal_does_not_say_whether_the_complaint_exists(
    client: AsyncClient,
) -> None:
    """One answer for a row that is there and a row that is not: the door closes before it looks.

    The role check runs ahead of any read, so this route cannot become the enumeration oracle the
    block work spent two stages closing — an account with a token cannot ask which report ids are
    real, only whether it holds the role.
    """
    filed = await _complaint_against(client, "oracle-accused@befos.app")
    ordinary = await _account(client, "oracle-plain@befos.app", "Прохожий")
    headers = auth_headers(ordinary["token"])

    real = await client.get(f"{QUEUE}/{filed['card']['id']}", headers=headers)
    invented = await client.get(f"{QUEUE}/{uuid.uuid4()}", headers=headers)
    assert (real.status_code, invented.status_code) == (403, 403)
    assert real.json() == invented.json(), "the two answers differ, which is a way of asking"

    review_of_real = await _decide(client, ordinary, filed["card"]["id"], "resolved", "mine now")
    assert review_of_real.status_code == 403, review_of_real.text
    assert (await _row(filed["card"]["id"])).status == "open"
    assert await _history(filed["card"]["id"]) == []


async def test_no_route_writes_the_moderator_flag(client: AsyncClient) -> None:
    """Mass assignment, tried at the three writes a client can reach with a body.

    Pydantic ignores a field the model does not declare, so the flag survives in neither the row nor
    the request: what is asserted is the column, not the answer, because an answer that echoes a
    field nobody wrote is the easier one to fake.
    """
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "self-appointed@befos.app",
            "password": "Test12345",
            "password_confirm": "Test12345",
            "is_moderator": True,
            "role": "moderator",
        },
    )
    assert registered.status_code == 201, registered.text
    user_id = registered.json()["user"]["id"]
    token = registered.json()["tokens"]["access_token"]

    onboarded = await client.post(
        "/api/v1/users/me/onboarding",
        json={
            "name": "Назначенный",
            "birth_date": "1994-02-02",
            "city": "Казань",
            "gender": "male",
            "about": "Ни о чём",
            "dating_goal": "relationship",
            "interests": [],
            "lifestyle": {"smoking": "never", "alcohol": "rarely", "sport": "often"},
            "age_min": 20,
            "age_max": 40,
            "gender_preference": ["female"],
            "is_moderator": True,
        },
        headers=auth_headers(token),
    )
    assert onboarded.status_code == 200, onboarded.text

    patched = await client.patch(
        "/api/v1/users/me",
        json={"is_moderator": True, "city": "Севастополь"},
        headers=auth_headers(token),
    )
    assert patched.status_code == 200, patched.text

    assert await _is_moderator_row(user_id) is False
    assert "is_moderator" not in patched.json()

    queue = await client.get(QUEUE, headers=auth_headers(token))
    assert queue.status_code == 403, queue.text


async def test_a_moderator_declared_in_the_body_is_not_the_one_the_history_names(
    client: AsyncClient,
) -> None:
    """The number in the path and the number in the body both fail to choose the hand.

    `ReviewIn` declares a status and a comment. A `moderator_id` somebody types is not read by the
    service — the identity comes from `Depends(get_moderator)` — so a stolen or guessed moderator id
    buys nothing, and the audit row keeps naming whoever actually signed in.
    """
    filed = await _complaint_against(client, "spoof-accused@befos.app")
    first = await _moderator(client, "spoof-hand-1@befos.app", "Первая рука")
    second = await _moderator(client, "spoof-hand-2@befos.app", "Вторая рука")
    report_id = filed["card"]["id"]

    answered = await client.post(
        f"{QUEUE}/{report_id}/review",
        json={
            "status": "resolved",
            "comment": "decided by somebody else",
            "moderator_id": second["user_id"],
            "moderator": second["user_id"],
            "by": second["user_id"],
        },
        headers=auth_headers(first["token"]),
    )
    assert answered.status_code == 200, answered.text
    history = await _history(report_id)
    assert len(history) == 1, history
    assert str(history[0].moderator_id) == first["user_id"], (
        "the body chose which name the audit row carries"
    )


async def test_the_hourly_budget_is_spent_on_the_attempt_not_on_the_row(
    client: AsyncClient,
) -> None:
    """Twenty complaints an hour per account, and the twenty-first costs a row it never wrote.

    Charged before the service runs: a refusal that costs nothing is a refusal that can be retried
    a thousand times. Keyed by the account, so the same person behind a second address or in a
    second tab spends the same budget — which is the only version of this that bounds a flood
    instead of bounding one IP address of it.

    Three accused accounts and the eight categories, rather than twenty-four accounts: the auth
    routes carry a window of their own, and a test that registered a target per complaint would be
    asserting on that limiter instead of on this one.
    """
    reporter = await _account(client, "flood@befos.app", "Заявитель")
    targets = [
        await register_and_auth(client, f"flood-target-{index}@befos.app") for index in range(3)
    ]

    codes: list[int] = []
    for target in targets:
        for reason in ALL_REASONS:
            codes.append(await _file(client, reporter, target["user_id"], reason))

    assert codes[:20] == [200] * 20, codes
    assert codes[20:] == [429] * 4, f"the budget ran out somewhere else: {codes}"

    extra = await register_and_auth(client, "flood-target-late@befos.app")
    late = await client.post(
        f"/api/v1/users/{extra['user_id']}/report",
        json={"reason": "spam"},
        headers=auth_headers(reporter["token"]),
    )
    assert late.status_code == 429, late.text
    assert late.json()["error"]["code"] == "rate_limited"

    async with AsyncSessionLocal() as session:
        held = list(
            (
                await session.execute(select(Report).where(Report.reporter_id == reporter["user_id"]))
            ).scalars().all()
        )
    assert len(held) == 20, f"a refused complaint still wrote a row: {len(held)}"

    # A second account filing about the same person spends its own budget, not the first one's:
    # the window belongs to whoever writes, which is what makes it a limit rather than a queue.
    other = await _account(client, "flood-second@befos.app", "Второй заявитель")
    assert await _file(client, other, targets[0]["user_id"], "spam") == 200


async def test_taking_the_role_away_stops_the_account_at_the_next_request(
    client: AsyncClient,
) -> None:
    """No role lives in the token, so revocation is immediate rather than due at the expiry.

    The same bearer string serves a 200 and then a 403 with nothing else changed but the column:
    which is what an operator needs after a moderator account is compromised.
    """
    moderator = await _moderator(client, "revoked@befos.app", "Отзываемый")
    headers = auth_headers(moderator["token"])

    before = await client.get(QUEUE, headers=headers)
    assert before.status_code == 200, before.text

    await _grant_moderator_role(moderator["user_id"], moderator=False)

    after = await client.get(QUEUE, headers=headers)
    assert after.status_code == 403, after.text
    detail = await client.get(f"{QUEUE}/{uuid.uuid4()}", headers=headers)
    assert detail.status_code == 403, detail.text
    assert await _is_moderator_row(moderator["user_id"]) is False


async def test_a_complaint_and_its_history_outlive_the_accounts_they_name(
    client: AsyncClient,
) -> None:
    """Deletion is a product promise; the queue is the record of what was said before it.

    Both halves of one complaint delete themselves. The row and the moderator's note stay and stay
    readable, the accused is marked gone rather than erased from the queue, and the age the card
    would have computed from the birth date erasure writes is not served as a person's age.
    """
    filed = await _complaint_against(client, "gone-accused@befos.app")
    moderator = await _moderator(client, "gone-hand@befos.app", "Диспетчер")
    report_id = filed["card"]["id"]

    answered = await _decide(client, moderator, report_id, "resolved", "the account removed itself")
    assert answered.status_code == 200, answered.text

    for account in (filed["reporter"], filed["accused"]):
        gone = await client.delete("/api/v1/users/me", headers=auth_headers(account["token"]))
        assert gone.status_code == 200, gone.text

    detail = await client.get(f"{QUEUE}/{report_id}", headers=auth_headers(moderator["token"]))
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "resolved"
    assert detail.json()["reported"]["is_deleted"] is True
    assert detail.json()["reported"]["age"] is None, (
        "the card put an age on the date the erasure writes"
    )
    assert [row["to_status"] for row in detail.json()["reviews"]] == ["resolved"]

    async with AsyncSessionLocal() as session:
        held = list(
            (await session.execute(select(Report).where(Report.id == uuid.UUID(report_id)))).scalars().all()
        )
        rows = list(
            (
                await session.execute(
                    select(ReportReview).where(ReportReview.report_id == uuid.UUID(report_id))
                )
            ).scalars().all()
        )
    assert len(held) == 1, "deleting an account took the complaint written about it"
    assert len(rows) == 1, "deleting an accounts took the history that says who closed it"


@pytest.mark.parametrize("status", ["resolved", "dismissed"])
async def test_an_ordinary_account_cannot_close_a_complaint_it_holds_no_role_for(
    client: AsyncClient, status: str
) -> None:
    """The two endings, refused twice over: to the person accused, and to the person accusing.

    Neither half of a complaint may move its status. The accused cannot erase the record of
    themselves and the reporter cannot decide their own case, which is the same 403 the queue gives
    — the role is the only credential this surface reads.
    """
    filed = await _complaint_against(client, "both-sides-accused@befos.app")
    report_id = filed["card"]["id"]

    for account in (filed["accused"], filed["reporter"]):
        refused = await _decide(client, account, report_id, status, "I decide this one")
        assert refused.status_code == 403, f"{account['email']}: {refused.text}"

    assert (await _row(report_id)).status == "open"
    assert await _history(report_id) == []
