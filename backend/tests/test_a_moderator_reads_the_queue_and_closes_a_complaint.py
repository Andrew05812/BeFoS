"""A moderator reads the complaint queue, closes a complaint, and the history says who did it.

Before stage 102 the complaint had one reader and one writer, and both were `psql`: `POST
/users/{user_id}/report` wrote the row, `docs/OPERATIONS.md` §14 told the operator to select it and
to `update reports set status = 'resolved'` by hand. So the database could say where a complaint
stood and could not say who put it there, and no account in the product could see a complaint at
all. Stage 102 adds the moderation surface — `GET /reports`, `GET /reports/{report_id}`,
`POST /reports/{report_id}/review` — and this file pins what those three promise:

* the queue is paged by a (created_at, id) cursor and filtered by status, oldest complaint first,
  with the page size bounded by the route rather than by the caller's patience;
* a status moves only along the transitions the service table names, a closed complaint is a dead
  end, and every move writes its own `report_reviews` row in the same transaction as the status —
  so a refused move leaves both exactly where they were;
* the hand that moved it is the session that authenticated, never a number in the body;
* two moderators answering the same complaint produce one decision and one refusal, not two
  histories that contradict each other.

What is measured here is the API and the rows behind it. No Android screen renders the queue: the
moderator's surface is these routes, documented in `docs/OPERATIONS.md` §14, and there is no client
half to this stage's row.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.models import Report, ReportReview, User
from .conftest import auth_headers, complete_onboarding, register_and_auth

QUEUE = "/api/v1/reports"
ALL_REASONS = [
    "spam",
    "harassment",
    "inappropriate",
    "fake",
    "minor",
    "impersonation",
    "threats",
    "other",
]


async def _account(client: AsyncClient, email: str, name: str) -> dict:
    """An account with a profile behind it.

    The queue reads a name and a city off `profiles`, so a test that only registered would be
    asserting against the fallback for a person who was never in the product: an account that
    exists but has not onboarded is a card with nothing on it.
    """
    account = await register_and_auth(client, email)
    await complete_onboarding(client, account["token"], name=name)
    return account


async def _grant_moderator_role(user_id: str, *, moderator: bool = True) -> None:
    """Move the flag the way the documented procedure moves it: one statement, no route.

    Nothing in the API can write `users.is_moderator` — that is what the companion file asserts —
    so a test that needs a moderator has to become the operator for the length of one UPDATE.
    """
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(User).where(User.id == uuid.UUID(user_id)).values(is_moderator=moderator)
        )
        await session.commit()


async def _moderator(client: AsyncClient, email: str, name: str = "Ревизор") -> dict:
    account = await _account(client, email, name)
    await _grant_moderator_role(account["user_id"])
    return account


async def _file(client: AsyncClient, reporter: dict, target_id: str, reason: str = "spam") -> int:
    return (
        await client.post(
            f"/api/v1/users/{target_id}/report",
            json={"reason": reason},
            headers=auth_headers(reporter["token"]),
        )
    ).status_code


async def _complaint_against(client: AsyncClient, accused_email: str = "accused@befos.app") -> dict:
    """One real complaint, filed by a fresh account against a fresh account."""
    reporter = await _account(client, "witness@befos.app", "Свидетель")
    accused = await _account(client, accused_email, "Обвиняемый")
    assert await _file(client, reporter, accused["user_id"]) == 200
    rows = await _page(client, await _moderator(client, "queue-reader@befos.app"))
    return {
        "reporter": reporter,
        "accused": accused,
        "card": next(row for row in rows if row["reported"]["user_id"] == accused["user_id"]),
    }


async def _raw_page(client: AsyncClient, moderator: dict, **params) -> dict:
    """One page of the queue, as the route answers it: a list, a cursor, and a `has_more`.

    `status=None` is dropped rather than sent, because the absence of a filter is what asks for
    every status, and an empty string would be a status nobody declares.
    """
    response = await client.get(
        QUEUE,
        params={key: value for key, value in params.items() if value is not None},
        headers=auth_headers(moderator["token"]),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _page(client: AsyncClient, moderator: dict, **params) -> list[dict]:
    return (await _raw_page(client, moderator, **params))["reports"]


async def _detail(client: AsyncClient, moderator: dict, report_id: str) -> dict:
    response = await client.get(f"{QUEUE}/{report_id}", headers=auth_headers(moderator["token"]))
    assert response.status_code == 200, response.text
    return response.json()


async def _decide(
    client: AsyncClient, moderator: dict, report_id: str, status: str, comment: str | None = None
):
    return await client.post(
        f"{QUEUE}/{report_id}/review",
        json={"status": status, "comment": comment},
        headers=auth_headers(moderator["token"]),
    )


async def _row(report_id: str) -> Report:
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(select(Report).where(Report.id == uuid.UUID(report_id)))
        ).scalar_one()


async def _history(report_id: str) -> list[ReportReview]:
    async with AsyncSessionLocal() as session:
        return list(
            (
                await session.execute(
                    select(ReportReview)
                    .where(ReportReview.report_id == uuid.UUID(report_id))
                    .order_by(ReportReview.created_at.asc(), ReportReview.id.asc())
                )
            ).scalars().all()
        )


async def test_a_moderator_sees_the_complaint_an_account_filed(client: AsyncClient) -> None:
    """The row a person wrote with one tap is a row another account can now read."""
    filed = await _complaint_against(client)
    card = filed["card"]
    assert card["reason"] == "spam"
    assert card["status"] == "open"
    assert card["reporter"]["user_id"] == filed["reporter"]["user_id"]
    assert card["reported"]["user_id"] == filed["accused"]["user_id"]
    assert card["reported"]["is_deleted"] is False
    assert card["reported"]["is_moderator"] is False
    assert card["details"] is None
    assert "email" not in card["reported"] and "email" not in card["reporter"], (
        "the queue started handing out addresses it has no use for"
    )


async def test_the_new_categories_are_stored_and_a_named_one_answers(client: AsyncClient) -> None:
    """The two categories stage 102 adds arrive as rows, and the queue reads them by name."""
    reporter = await register_and_auth(client, "eight-reasons@befos.app")
    accused = await register_and_auth(client, "eight-reasons-target@befos.app")
    for reason in ALL_REASONS:
        assert await _file(client, reporter, accused["user_id"], reason) == 200, reason
    moderator = await _moderator(client, "eight-reasons-reader@befos.app")
    rows = await _page(client, moderator, status="open")
    named = {row["reason"] for row in rows if row["reported"]["user_id"] == accused["user_id"]}
    assert named == set(ALL_REASONS), f"the queue lost a category on the way: {sorted(named)}"


async def test_an_unnamed_category_is_refused_and_names_the_set_it_wants(
    client: AsyncClient,
) -> None:
    reporter = await register_and_auth(client, "wrong-reason@befos.app")
    accused = await register_and_auth(client, "wrong-reason-target@befos.app")
    response = await client.post(
        f"/api/v1/users/{accused['user_id']}/report",
        json={"reason": "creepy"},
        headers=auth_headers(reporter["token"]),
    )
    assert response.status_code == 422, response.text
    message = response.json()["error"]["message"]
    assert "impersonation" in message and "threats" in message, message
    async with AsyncSessionLocal() as session:
        held = list(
            (
                await session.execute(select(Report).where(Report.reporter_id == reporter["user_id"]))
            ).scalars().all()
        )
    assert held == [], f"a category nobody declared was written anyway: {held}"


async def test_the_queue_is_filtered_by_status(client: AsyncClient) -> None:
    """One status asked for is the only status answered, and a closed complaint leaves the open list."""
    reporter = await register_and_auth(client, "filter-witness@befos.app")
    first = await register_and_auth(client, "filter-first@befos.app")
    second = await register_and_auth(client, "filter-second@befos.app")
    assert await _file(client, reporter, first["user_id"]) == 200
    assert await _file(client, reporter, second["user_id"], "threats") == 200
    moderator = await _moderator(client, "filter-reader@befos.app")

    opened = await _raw_page(client, moderator, status="open", limit=100)
    assert {row["status"] for row in opened["reports"]} == {"open"}

    closed = await _decide(client, moderator, opened["reports"][0]["id"], "dismissed", "not visible")
    assert closed.status_code == 200, closed.text

    still_open = await _page(client, moderator, status="open")
    gone = await _page(client, moderator, status="dismissed")
    assert [row["id"] for row in gone] == [opened["reports"][0]["id"]]
    assert opened["reports"][0]["id"] not in {row["id"] for row in still_open}
    assert await _page(client, moderator, status="resolved") == []


async def test_the_queue_pages_on_a_cursor_and_walks_to_its_end(client: AsyncClient) -> None:
    """No complaint is skipped and none is handed out twice while a page is being walked."""
    moderator = await _moderator(client, "cursor-reader@befos.app")
    accused = await register_and_auth(client, "cursor-accused@befos.app")
    for index in range(6):
        witness = await register_and_auth(client, f"cursor-witness-{index}@befos.app")
        assert await _file(client, witness, accused["user_id"], ALL_REASONS[index]) == 200

    whole = await _raw_page(client, moderator, limit=100)
    expected = [row["id"] for row in whole["reports"]]
    assert len(expected) >= 6, expected

    walked: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        params = {"limit": 2}
        if cursor is not None:
            params["after_id"] = cursor
        page = await _raw_page(client, moderator, **params)
        walked.extend(row["id"] for row in page["reports"])
        cursor = page["next_cursor"]
        assert page["has_more"] is (cursor is not None), page
        if cursor is None:
            break
    assert cursor is None, "the queue never reached its end inside ten pages"
    assert walked == expected, f"{walked} against {expected}"
    assert len(set(walked)) == len(walked), "a complaint was handed out twice"


async def test_a_page_beyond_the_bound_and_a_cursor_that_names_no_row_are_both_refused(
    client: AsyncClient,
) -> None:
    moderator = await _moderator(client, "bounds-reader@befos.app")
    too_big = await client.get(
        QUEUE, params={"limit": 101}, headers=auth_headers(moderator["token"])
    )
    assert too_big.status_code == 422, too_big.text

    stale = await client.get(
        QUEUE,
        params={"after_id": str(uuid.uuid4())},
        headers=auth_headers(moderator["token"]),
    )
    assert stale.status_code == 404, stale.text
    assert stale.json()["error"]["code"] == "not_found"

    missing = await client.get(
        f"{QUEUE}/{uuid.uuid4()}", headers=auth_headers(moderator["token"])
    )
    assert missing.status_code == 404, missing.text


async def test_closing_a_complaint_writes_the_row_that_says_who_closed_it(
    client: AsyncClient,
) -> None:
    """The status and its history are one fact, and the history names the hand and the reason."""
    filed = await _complaint_against(client, "close-accused@befos.app")
    moderator = await _moderator(client, "close-reader@befos.app")
    report_id = filed["card"]["id"]

    answered = await _decide(client, moderator, report_id, "resolved", "the account was already gone")
    assert answered.status_code == 200, answered.text
    assert answered.json()["status"] == "resolved"

    assert (await _row(report_id)).status == "resolved"
    history = await _history(report_id)
    assert len(history) == 1, history
    assert history[0].from_status == "open" and history[0].to_status == "resolved"
    assert str(history[0].moderator_id) == moderator["user_id"]
    assert history[0].comment == "the account was already gone"

    detail = await _detail(client, moderator, report_id)
    assert detail["status"] == "resolved"
    assert [row["from_status"] for row in detail["reviews"]] == ["open"]
    assert [row["to_status"] for row in detail["reviews"]] == ["resolved"]
    assert detail["reviews"][0]["moderator_name"], detail["reviews"]


async def test_a_complaint_opened_for_a_look_needs_no_note_and_a_closed_one_does(
    client: AsyncClient,
) -> None:
    """`reviewed` is a step, not a verdict, and the two endings are the ones that must be explained."""
    filed = await _complaint_against(client, "note-accused@befos.app")
    moderator = await _moderator(client, "note-reader@befos.app")
    report_id = filed["card"]["id"]

    looked = await _decide(client, moderator, report_id, "reviewed")
    assert looked.status_code == 200, looked.text
    assert (await _history(report_id))[0].comment is None

    mute = await _decide(client, moderator, report_id, "dismissed", "   ")
    assert mute.status_code == 422, mute.text
    assert "comment" in mute.json()["error"]["message"], mute.text
    assert (await _row(report_id)).status == "reviewed"
    assert len(await _history(report_id)) == 1, "a refusal still wrote a verdict"

    second_hand = await _moderator(client, "note-reader-2@befos.app")
    closed = await _decide(client, second_hand, report_id, "dismissed", "one message, no threat in it")
    assert closed.status_code == 200, closed.text
    history = await _history(report_id)
    assert [(row.from_status, row.to_status) for row in history] == [
        ("open", "reviewed"),
        ("reviewed", "dismissed"),
    ]


async def test_a_transition_the_lifecycle_does_not_have_is_refused(client: AsyncClient) -> None:
    """Four statuses, one table, and everything outside it answered without writing."""
    filed = await _complaint_against(client, "lifecycle-accused@befos.app")
    moderator = await _moderator(client, "lifecycle-reader@befos.app")
    report_id = filed["card"]["id"]

    unknown = await _decide(client, moderator, report_id, "deleted", "no reason at all")
    assert unknown.status_code == 422, unknown.text
    assert "Allowed" in unknown.json()["error"]["message"], unknown.text

    closed = await _decide(client, moderator, report_id, "resolved", "confirmed")
    assert closed.status_code == 200, closed.text

    for target in ("open", "reviewed"):
        reopened = await _decide(client, moderator, report_id, target, "thinking again")
        assert reopened.status_code == 422, f"{target}: {reopened.text}"
        assert "cannot move" in reopened.json()["error"]["message"], reopened.text

    repeat = await _decide(client, moderator, report_id, "resolved", "again")
    assert repeat.status_code == 409, repeat.text
    assert (await _row(report_id)).status == "resolved"
    assert len(await _history(report_id)) == 1, "a refused move left a line in the history"


async def test_a_complaint_about_a_moderator_is_not_theirs_to_close(
    client: AsyncClient,
) -> None:
    """The role says who may decide, not whom they may decide about."""
    accused = await register_and_auth(client, "self-dealing@befos.app")
    witness = await register_and_auth(client, "witness-about-moderator@befos.app")
    assert await _file(client, witness, accused["user_id"], "harassment") == 200
    await _grant_moderator_role(accused["user_id"])

    moderator = await _moderator(client, "another-hand@befos.app")
    rows = await _page(client, moderator, status="open")
    card = next(row for row in rows if row["reported"]["user_id"] == accused["user_id"])
    assert card["reported"]["is_moderator"] is True, "the queue hides that the accused holds the role"

    self_decided = await _decide(client, accused, card["id"], "dismissed", "nothing of the sort")
    assert self_decided.status_code == 403, self_decided.text
    assert (await _row(card["id"])).status == "open"
    assert await _history(card["id"]) == []


async def test_two_hands_answering_one_complaint_leave_one_verdict(client: AsyncClient) -> None:
    """The row is locked while it is being decided, so two decisions become a sequence.

    Which of the two wins is not what is asserted — under either order the pair of answers is one
    acceptance and one refusal, one history row, and a status that says what the history ends with.
    """
    filed = await _complaint_against(client, "race-accused@befos.app")
    first = await _moderator(client, "race-hand-1@befos.app")
    second = await _moderator(client, "race-hand-2@befos.app")
    report_id = filed["card"]["id"]

    answers = await asyncio.gather(
        _decide(client, first, report_id, "resolved", "first hand"),
        _decide(client, second, report_id, "resolved", "second hand"),
    )
    codes = sorted(response.status_code for response in answers)
    assert codes == [200, 409], [response.text for response in answers]
    assert (await _row(report_id)).status == "resolved"
    history = await _history(report_id)
    assert len(history) == 1, f"both hands wrote a verdict: {history}"


async def test_a_comment_longer_than_the_route_allows_changes_nothing(
    client: AsyncClient,
) -> None:
    filed = await _complaint_against(client, "long-accused@befos.app")
    moderator = await _moderator(client, "long-reader@befos.app")
    report_id = filed["card"]["id"]

    too_long = await _decide(client, moderator, report_id, "resolved", "х" * 1001)
    assert too_long.status_code == 422, too_long.text
    assert (await _row(report_id)).status == "open"
    assert await _history(report_id) == []


# How each of the four states is reached from the one every complaint starts in. Read as the walk
# the lifecycle table allows, so the test asks for the state a route can actually put a row into
# instead of inventing a fourth way to get there.
_PATHS = {
    "open": [],
    "reviewed": [("reviewed", None)],
    "resolved": [("resolved", "closed for the test")],
    "dismissed": [("reviewed", None), ("dismissed", "closed for the test")],
}


@pytest.mark.parametrize("status", sorted(_PATHS))
async def test_the_status_a_moderator_is_told_is_the_status_the_row_holds(
    client: AsyncClient, status: str
) -> None:
    """One column, four values, and no parallel vocabulary invented for the same four states."""
    filed = await _complaint_against(client, f"enum-accused-{status}@befos.app")
    moderator = await _moderator(client, f"enum-reader-{status}@befos.app")
    assert filed["card"]["status"] == "open"

    for target, comment in _PATHS[status]:
        answered = await _decide(client, moderator, filed["card"]["id"], target, comment)
        assert answered.status_code == 200, f"{target}: {answered.text}"
        assert answered.json()["status"] == target

    rows = await _page(client, moderator, status=None)
    held = next(row for row in rows if row["id"] == filed["card"]["id"])
    assert held["status"] == status, held
    assert (await _row(filed["card"]["id"])).status == status
    assert len(await _history(filed["card"]["id"])) == len(_PATHS[status])
