"""A pair can end without either person blocking the other.

Until stage 105 the only ways a pair ended were a block and an account deletion, and each of them
says something the other person did not ask to have said: a block hides the blocker from the deck
and shuts their profile in both directions, and leaves a row in `blocks` that the blocked person's
unblock route cannot even see. «Мы не подходим друг другу» needed its own verb, and
`DELETE /matches/{match_id}` is it: the pair row goes, everything the pair owned goes with it
through the schema's own `ON DELETE CASCADE`, and the two people stay plain, unblocked accounts.

What this file pins:

* the write belongs to a member: a third account is answered 404, the same answer an unknown id
  gets, so the route cannot be probed for which pairs exist;
* the end is the end — messages and plans of the pair are rows of the dissolved row's children, and
  the proof is read from the tables, not from the screens that lost their subject;
* the `likes` go with the pair, which is the whole difference between «unmatch» and «retry»: one
  next tap by one person alone must not write a relationship the other dissolved;
* no `blocks` row is created and no profile is shut: the unmatch is not a block in disguise;
* a complaint filed before the unmatch stays: the report names people, not the pair, and ending a
  relationship is not withdrawing a report about it;
* the write races the pair's own chat the way the block already does — the pair lock makes the
  send wait for the dissolve, and the answer is 404, never an FK 500.

What is not covered here is the screen: the row, its dialog and the wording are Composable code,
and nothing in this repository's Android set renders them until stage 105 §4 (see
`docs/VERIFICATION.md`).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import or_, select

from app.core.database import AsyncSessionLocal
from app.models import Activity, Block, Like, Match, Message, Report, SharedPlan
from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth


async def _person(client: AsyncClient, email: str, name: str) -> dict:
    """An account the deck is willing to show: onboarding done, questionnaire answered."""
    account = await register_and_auth(client, email)
    await complete_onboarding(client, account["token"], name=name)
    await answer_all_questions(client, account["token"])
    return account


async def _pair(client: AsyncClient, a: dict, b: dict) -> str:
    """A real pair: both people liked each other through the route that makes matches."""
    liked = await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    assert liked.status_code in (200, 201), liked.text
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    assert mutual.status_code in (200, 201), mutual.text
    assert mutual.json()["match"], mutual.text
    return mutual.json()["match_id"]


async def _listed_match_ids(client: AsyncClient, account: dict) -> list[str]:
    response = await client.get("/api/v1/matches", headers=auth_headers(account["token"]))
    assert response.status_code == 200, response.text
    return [entry["match_id"] for entry in response.json()["matches"]]


async def _dissolve(client: AsyncClient, account: dict, match_id: str):
    return await client.delete(f"/api/v1/matches/{match_id}", headers=auth_headers(account["token"]))


async def _send(client: AsyncClient, account: dict, match_id: str, body: str) -> int:
    response = await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": body},
        headers=auth_headers(account["token"]),
    )
    return response.status_code


async def _message_ids(match_id: str) -> list[str]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(select(Message.id).where(Message.match_id == uuid.UUID(match_id)))
        ).all()
    return [str(row[0]) for row in rows]


@pytest.fixture
async def matched(client: AsyncClient):
    a = await _person(client, "unmatch-a@befos.app", "Аня")
    b = await _person(client, "unmatch-b@befos.app", "Боря")
    match_id = await _pair(client, a, b)
    return a, b, match_id


async def test_dissolving_a_pair_takes_it_from_both_members_lists(client: AsyncClient, matched) -> None:
    """One write, two screens: the pair vanishes for the person who tapped and for the other alike."""
    a, b, match_id = matched
    assert match_id in await _listed_match_ids(client, a)
    assert match_id in await _listed_match_ids(client, b)

    ended = await _dissolve(client, a, match_id)
    assert ended.status_code == 204, ended.text
    assert await ended.aread() == b"", "204 that carries a body is a response no client asked for"

    assert await _listed_match_ids(client, a) == []
    assert await _listed_match_ids(client, b) == [], (
        "the person who tapped left the pair but the other half still sees it"
    )
    async with AsyncSessionLocal() as session:
        row = (await session.execute(select(Match.id).where(Match.id == uuid.UUID(match_id)))).first()
    assert row is None, "the list is empty and the row is standing"


async def test_every_read_of_a_dissolved_pair_answers_a_pair_that_is_not_there(
    client: AsyncClient, matched
) -> None:
    """Detail, history, compatibility — the routes that took the pair as their subject."""
    a, b, match_id = matched
    assert (await _dissolve(client, a, match_id)).status_code == 204
    for who in (a, b):
        headers = auth_headers(who["token"])
        for path in (
            f"/api/v1/matches/{match_id}",
            f"/api/v1/matches/{match_id}/messages",
            f"/api/v1/matches/{match_id}/compatibility",
        ):
            response = await client.get(path, headers=headers)
            assert response.status_code == 404, f"{path} answered {response.status_code}: {response.text}"
            assert response.json()["error"]["code"] == "not_found", response.text


async def test_the_second_tap_is_answered_like_a_pair_nobody_holds(client: AsyncClient, matched) -> None:
    """A retry over a lost answer, next to the probe it must not answer.

    Both the dissolved id and a uuid no row ever held have to produce the same envelope: an
    answer that differed would turn this route into an oracle for which pair ids exist.
    """
    a, b, match_id = matched
    assert (await _dissolve(client, a, match_id)).status_code == 204

    retry = await _dissolve(client, a, match_id)
    assert retry.status_code == 404, retry.text
    never = await _dissolve(client, a, str(uuid.uuid4()))
    assert never.status_code == 404, never.text
    assert retry.json() == never.json(), (
        "a pair that was here a second ago and a number nobody held answered differently"
    )
    assert await _listed_match_ids(client, b) == []


async def test_a_third_account_cannot_end_someone_elses_pair(client: AsyncClient, matched) -> None:
    a, b, match_id = matched
    stranger = await _person(client, "unmatch-stranger@befos.app", "Вера")

    refused = await _dissolve(client, stranger, match_id)
    assert refused.status_code == 404, refused.text
    assert match_id in await _listed_match_ids(client, a), "the refused write dissolved the pair anyway"
    assert match_id in await _listed_match_ids(client, b)


async def test_the_conversation_goes_with_the_pair(client: AsyncClient, matched) -> None:
    """The chat is a child of the pair row, and the schema is the cleanup.

    Read from the table rather than through the routes: the routes for a dissolved pair answer 404
    (pinned above), which would hide whether any message row is still standing under it.
    """
    a, b, match_id = matched
    assert await _send(client, a, match_id, "Привет") == 201
    assert await _send(client, b, match_id, "Привет, рад видеть") == 201
    assert len(await _message_ids(match_id)) == 2

    assert (await _dissolve(client, a, match_id)).status_code == 204
    assert await _message_ids(match_id) == [], (
        "the pair ended and its messages are standing — orphans no route can reach and no person can delete"
    )


async def test_the_plans_go_with_the_row(client: AsyncClient, matched) -> None:
    """The pair's arranged idea is `shared_plans`, CASCADE'd on `match_id` like the messages."""
    a, b, match_id = matched
    async with AsyncSessionLocal() as session:
        activity_id = (await session.execute(select(Activity.id).limit(1))).scalar_one()
        plan_id = uuid.uuid4()
        session.add(
            SharedPlan(
                id=plan_id,
                match_id=uuid.UUID(match_id),
                activity_id=activity_id,
                created_by=uuid.UUID(a["user_id"]),
                title="Прогулка вдоль набережной",
            )
        )
        await session.commit()

    assert (await _dissolve(client, a, match_id)).status_code == 204
    async with AsyncSessionLocal() as session:
        held = (await session.execute(select(SharedPlan.id).where(SharedPlan.match_id == uuid.UUID(match_id)))).all()
    assert held == [], f"the pair ended and its plan is standing: {held}"


async def test_an_unmatch_writes_no_block_and_shuts_no_profile(client: AsyncClient, matched) -> None:
    """The difference between the two verbs, measured on the rows they leave behind.

    A block would put a row in `blocks`, hide the blocker from the other's deck, and answer 404 on
    the blocked profile. An unmatch must do none of that: the two people stay plain accounts that
    can read each other, and the only way back to the deck is the profile — the deck keeps its
    no-repeat rule for a card it already showed.
    """
    a, b, match_id = matched
    assert (await _dissolve(client, a, match_id)).status_code == 204

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Block.id).where(
                    or_(
                        (Block.blocker_id == uuid.UUID(a["user_id"]))
                        & (Block.blocked_id == uuid.UUID(b["user_id"])),
                        (Block.blocker_id == uuid.UUID(b["user_id"]))
                        & (Block.blocked_id == uuid.UUID(a["user_id"])),
                    )
                )
            )
        ).all()
    assert rows == [], "the unmatch wrote a block, and now one of them is hidden without having asked"

    reopened = await client.get(
        f"/api/v1/users/{b['user_id']}", headers=auth_headers(a["token"])
    )
    assert reopened.status_code == 200, reopened.text


async def test_one_more_like_does_not_bring_the_pair_back(client: AsyncClient, matched) -> None:
    """«начать заново можно, но только вдвоём»: the dissolved half's next tap alone matches nobody.

    This is what the deletion of both `likes` rows is for. Left standing, the ex-partner's
    `has_liked_back` would still be true, and one tap by the person who dissolved the pair would
    have `ensure_match` write a fresh pair the other never agreed to — the unmatch would undo
    itself on the next card.
    """
    a, b, match_id = matched
    assert (await _dissolve(client, a, match_id)).status_code == 204

    again = await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    assert again.status_code in (200, 201), again.text
    body = again.json()
    assert body["liked"] is True, body
    assert body["match"] is False, body
    assert body["match_id"] is None, "a dissolved pair resurrected itself on one person's tap"
    assert await _listed_match_ids(client, b) == []

    async with AsyncSessionLocal() as session:
        likes = (
            await session.execute(
                select(Like.id).where(
                    or_(
                        (Like.from_user_id == uuid.UUID(a["user_id"]))
                        & (Like.to_user_id == uuid.UUID(b["user_id"])),
                        (Like.from_user_id == uuid.UUID(b["user_id"]))
                        & (Like.to_user_id == uuid.UUID(a["user_id"])),
                    )
                )
            )
        ).all()
    assert len(likes) == 1, f"the unmatch left the old likes standing: {likes}"


async def test_two_new_likes_build_a_pair_under_a_new_id(client: AsyncClient, matched) -> None:
    """The way back is the gesture that made the pair in the first place, twice over again."""
    a, b, old_id = matched
    assert (await _dissolve(client, a, old_id)).status_code == 204

    first = await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    assert first.status_code in (200, 201), first.text
    second = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    assert second.status_code in (200, 201), second.text
    new_id = second.json()["match_id"]
    assert second.json()["match"] is True, second.text
    assert new_id and new_id != old_id, (
        f"the new pair carries the dissolved row's id {old_id}: readers would reopen a chat the cascade already took"
    )
    assert new_id in await _listed_match_ids(client, a)
    assert new_id in await _listed_match_ids(client, b)


async def test_a_complaint_filed_before_the_unmatch_stays_for_the_moderator(
    client: AsyncClient, matched
) -> None:
    """The report names people, not the pair: ending a relationship does not withdraw a complaint.

    A report filed from the pair's chat outlives that chat by design of the rows — `reports` keys on
    `reporter_id`/`reported_id`, so the pair's cascade cannot reach it — and the moderator reads
    what was said about a person, which a later unmatch cannot unmake.
    """
    a, b, match_id = matched
    filed = await client.post(
        f"/api/v1/users/{b['user_id']}/report",
        json={"reason": "spam", "details": "Жалоба до расторжения"},
        headers=auth_headers(a["token"]),
    )
    assert filed.status_code == 200, filed.text

    assert (await _dissolve(client, a, match_id)).status_code == 204
    async with AsyncSessionLocal() as session:
        held = (
            await session.execute(
                select(Report.id).where(
                    Report.reporter_id == uuid.UUID(a["user_id"]),
                    Report.reported_id == uuid.UUID(b["user_id"]),
                )
            )
        ).all()
    assert len(held) == 1, f"the unmatch took the complaint with it: {held}"


async def test_dissolving_while_the_partner_is_writing_never_answers_500(
    client: AsyncClient, matched
) -> None:
    """The same invariant the block race test holds, for the new writer.

    `ChatService.send` takes the pair's advisory lock before it writes, so a send that meets a
    dissolve in flight waits for it and then finds no pair — a 404, not the FK violation that
    raced before the lock existed. The test asks for the whole set of honest answers only:
    the write either made it before the end (201) or is told the pair is gone (404).
    """
    a, b, match_id = matched

    async def write(body: str):
        return await _send(client, b, match_id, body)

    dissolve, *sends = await asyncio.gather(
        _dissolve(client, a, match_id),
        write("Первая"),
        write("Вторая"),
        write("Третья"),
    )
    assert dissolve.status_code == 204, dissolve.text
    for status in sends:
        assert status in (201, 404), f"a write into a pair being dissolved answered {status}"
    assert await _message_ids(match_id) == [], (
        "the race left message rows under a dissolved pair — the cascade missed what the lock let in"
    )
