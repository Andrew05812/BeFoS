"""A block a person placed by mistake is theirs to undo, and the list of them is theirs to see.

`POST /users/{user_id}/block` was the whole surface of blocking: a tap dissolved the match, hid the
profile in both directions and took the person out of the deck, and nothing in the API could walk it
back. A mis-tap was therefore permanent, and a person who had blocked several accounts over a year
could not remember which. Stage 101 adds the two reads the screen needs — `DELETE /users/{user_id}/block`
and `GET /users/me/blocks` — and this file pins what they promise:

* the row is deleted by its own author: `blocks` is read one-way (`blocker_id` is the caller), so an
  account cannot release the block another account placed, and cannot use the route to ask whether a
  given pair is blocked — a row that is not there and a row that is somebody else's answer alike;
* the answer to an undo is the list that is left, the same way the photograph row is painted from the
  server's answer rather than from what the tap expected;
* undoing a block returns the person to the deck and reopens their profile, and does not resurrect the
  match the block dissolved — a route that quietly re-created a relationship nobody agreed to would be
  the worse defect of the two.

What is not covered here is the screen: the list, its rows and the confirmation dialog are Composable
code, and nothing in this repository's Android set renders it (see the note in `docs/VERIFICATION.md`).
"""

from __future__ import annotations

import asyncio
import io
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import insert, select

from app.core.database import AsyncSessionLocal
from app.models import Block, Report
from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth


async def _person(client: AsyncClient, email: str, name: str) -> dict:
    """An account the deck is willing to show: onboarding done, questionnaire answered."""
    account = await register_and_auth(client, email)
    await complete_onboarding(client, account["token"], name=name)
    await answer_all_questions(client, account["token"])
    return account


async def _block(client: AsyncClient, blocker: dict, target: str) -> None:
    response = await client.post(
        f"/api/v1/users/{target}/block", headers=auth_headers(blocker["token"])
    )
    assert response.status_code == 200, response.text


async def _list(client: AsyncClient, account: dict) -> list[dict]:
    response = await client.get("/api/v1/users/me/blocks", headers=auth_headers(account["token"]))
    assert response.status_code == 200, response.text
    return response.json()["blocked"]


def _ids(rows: list[dict]) -> list[str]:
    return [row["user_id"] for row in rows]


async def _upload_photo(client: AsyncClient, account: dict) -> str:
    picture = io.BytesIO()
    Image.new("RGB", (24, 24), "red").save(picture, format="PNG")
    response = await client.post(
        "/api/v1/users/me/photo",
        headers=auth_headers(account["token"]),
        files={"file": ("red.png", picture.getvalue(), "image/png")},
    )
    assert response.status_code == 200, response.text
    return response.json()["photos"][0]["url"]


async def _deck_ids(client: AsyncClient, viewer: dict) -> list[str]:
    """Every card the deck hands this viewer, following its own cursors rather than one page.

    Paging to the end is what makes the block test a statement about the deck and not about where
    the peer happened to rank on a page.
    """
    headers = auth_headers(viewer["token"])
    cursor: str | None = None
    seen: list[str] = []
    for _ in range(10):
        params: dict = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        response = await client.get("/api/v1/discover", params=params, headers=headers)
        assert response.status_code == 200, response.text
        page = response.json()
        seen.extend(card["user_id"] for card in page["items"])
        if not page["has_more"] or not page["next_cursor"]:
            return seen
        cursor = page["next_cursor"]
    raise AssertionError(f"the deck did not end within ten pages for {viewer['email']}")


async def test_the_list_names_everyone_the_account_blocked_newest_first(
    client: AsyncClient,
) -> None:
    me = await _person(client, "blocks-list-me@befos.app", "Марк")
    first = await _person(client, "blocks-list-a@befos.app", "Аня")
    second = await _person(client, "blocks-list-b@befos.app", "Боря")

    await _block(client, me, first["user_id"])
    await _block(client, me, second["user_id"])

    rows = await _list(client, me)
    assert set(_ids(rows)) == {first["user_id"], second["user_id"]}, rows
    assert _ids(rows) == [second["user_id"], first["user_id"]], (
        f"the newest block has to lead the list a person scrolls: {_ids(rows)}"
    )


async def test_a_row_of_the_list_holds_the_card_a_person_recognises(client: AsyncClient) -> None:
    """A list of uuids is not something a human picks a row out of: name, age, city, leading photo."""
    me = await _person(client, "blocks-card-me@befos.app", "Марк")
    peer = await _person(client, "blocks-card-peer@befos.app", "Нина")
    url = await _upload_photo(client, peer)

    await _block(client, me, peer["user_id"])
    rows = await _list(client, me)
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["name"] == "Нина", row
    assert row["age"] == 30, row
    assert row["city"] == "Москва", row
    assert row["photo_url"] == url, "the row must show the photograph readers are shown, not none"
    assert row["blocked_at"], "the list orders itself by the moment the block was placed"


async def test_an_account_that_has_blocked_nobody_answers_an_empty_list(client: AsyncClient) -> None:
    me = await _person(client, "blocks-empty@befos.app", "Марк")
    assert await _list(client, me) == []


async def test_undoing_a_block_answers_the_list_that_is_left(client: AsyncClient) -> None:
    """The write paints the screen: the answer is the remaining rows, not a boolean.

    A client that removed one row and re-read the whole list would show the list a moment before the
    removal landed if the read raced anything; the row the route answers with is the row the server
    holds after its own commit.
    """
    me = await _person(client, "blocks-undo-me@befos.app", "Марк")
    gone = await _person(client, "blocks-undo-gone@befos.app", "Аня")
    kept = await _person(client, "blocks-undo-kept@befos.app", "Боря")
    await _block(client, me, gone["user_id"])
    await _block(client, me, kept["user_id"])

    removed = await client.delete(
        f"/api/v1/users/{gone['user_id']}/block", headers=auth_headers(me["token"])
    )
    assert removed.status_code == 200, removed.text
    assert _ids(removed.json()["blocked"]) == [kept["user_id"]], removed.json()["blocked"]
    assert _ids(await _list(client, me)) == [kept["user_id"]], (
        "the write answered one list and the read holds another"
    )


async def test_a_block_that_was_never_placed_is_answered_as_a_row_that_is_not_there(
    client: AsyncClient,
) -> None:
    """Both kinds of absent row answer alike: 404 says nothing about whether the account exists."""
    me = await _person(client, "blocks-absent-me@befos.app", "Марк")
    stranger = await _person(client, "blocks-absent-stranger@befos.app", "Нина")

    never_blocked = await client.delete(
        f"/api/v1/users/{stranger['user_id']}/block", headers=auth_headers(me["token"])
    )
    assert never_blocked.status_code == 404, never_blocked.text
    assert never_blocked.json()["error"]["code"] == "not_found", never_blocked.text

    no_such_id = await client.delete(
        f"/api/v1/users/{uuid.uuid4()}/block", headers=auth_headers(me["token"])
    )
    assert no_such_id.status_code == 404, no_such_id.text
    assert no_such_id.json() == never_blocked.json(), (
        "a real account and a number nobody holds answered differently, which tells the caller "
        "whether the profile exists"
    )


async def test_the_second_undo_of_one_block_changes_nothing(client: AsyncClient) -> None:
    """A double tap, or a retry over an answer that never arrived."""
    me = await _person(client, "blocks-twice-me@befos.app", "Марк")
    other = await _person(client, "blocks-twice-other@befos.app", "Нина")
    await _block(client, me, other["user_id"])
    headers = auth_headers(me["token"])

    first = await client.delete(f"/api/v1/users/{other['user_id']}/block", headers=headers)
    assert first.status_code == 200, first.text
    second = await client.delete(f"/api/v1/users/{other['user_id']}/block", headers=headers)
    assert second.status_code == 404, second.text
    assert await _list(client, me) == []


async def test_asking_to_undo_ones_own_block_of_oneself_is_refused(client: AsyncClient) -> None:
    """The schema forbids a self-block (`ck_block_not_self`), so the request names an act that has no meaning."""
    me = await _person(client, "blocks-self@befos.app", "Марк")
    refused = await client.delete(
        f"/api/v1/users/{me['user_id']}/block", headers=auth_headers(me["token"])
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "validation_error", refused.text
    assert await _list(client, me) == []


async def test_one_account_cannot_release_the_block_another_placed(client: AsyncClient) -> None:
    """`is_blocked_either` reads a pair; `remove_block` writes one author's row.

    The direction is the whole safety of the write: deleting on either column would let any account
    unblock any person it had been blocked by, and the 404 keeps the attempt from becoming an oracle
    about which pairs are blocked.
    """
    author = await _person(client, "blocks-dir-author@befos.app", "Марк")
    target = await _person(client, "blocks-dir-target@befos.app", "Нина")
    third = await _person(client, "blocks-dir-third@befos.app", "Боря")
    await _block(client, author, target["user_id"])

    refused = await client.delete(
        f"/api/v1/users/{target['user_id']}/block", headers=auth_headers(third["token"])
    )
    assert refused.status_code == 404, refused.text
    assert _ids(await _list(client, author)) == [target["user_id"]], (
        "the refused write removed somebody else's row"
    )
    # The target cannot undo the block placed on them either, and never sees it.
    own_attempt = await client.delete(
        f"/api/v1/users/{author['user_id']}/block", headers=auth_headers(target["token"])
    )
    assert own_attempt.status_code == 404, own_attempt.text
    assert await _list(client, target) == [], (
        "a person learns they are blocked by reading the list of whom they blocked"
    )


async def test_undoing_a_block_puts_the_person_back_into_the_deck(client: AsyncClient) -> None:
    """The payoff of the write, measured on the screen it is for: the deck's anti-join stops excluding them.

    The block hides the candidate before the deck ever queues them, so nothing about the person has
    been shown yet; undoing it has to hand them back rather than leave a mistaken tap as a permanent
    disappearance.
    """
    viewer = await _person(client, "blocks-deck-viewer@befos.app", "Марк")
    peer = await _person(client, "blocks-deck-peer@befos.app", "Нина")

    await _block(client, viewer, peer["user_id"])
    assert peer["user_id"] not in await _deck_ids(client, viewer)

    removed = await client.delete(
        f"/api/v1/users/{peer['user_id']}/block", headers=auth_headers(viewer["token"])
    )
    assert removed.status_code == 200, removed.text
    assert peer["user_id"] in await _deck_ids(client, viewer), (
        "the block was undone and the deck still refuses the person"
    )


async def test_a_card_the_deck_already_showed_does_not_come_back_after_an_undo(
    client: AsyncClient,
) -> None:
    """The deck's one promise survives the block and its undo: a card is served once.

    The person was already swiped before the mistaken block, so the queue remembers showing them, and
    undoing the block reopens their profile without putting the same card back in the deck. The way
    back to somebody the deck already showed is the profile, not a repeat.
    """
    viewer = await _person(client, "blocks-seen-viewer@befos.app", "Марк")
    peer = await _person(client, "blocks-seen-peer@befos.app", "Нина")
    assert peer["user_id"] in await _deck_ids(client, viewer), "the deck never held them to begin with"

    await _block(client, viewer, peer["user_id"])
    removed = await client.delete(
        f"/api/v1/users/{peer['user_id']}/block", headers=auth_headers(viewer["token"])
    )
    assert removed.status_code == 200, removed.text

    ids = await _deck_ids(client, viewer)
    assert peer["user_id"] not in ids, (
        "the deck repeated a card it had already shown: the no-repeat rule went with the block"
    )
    reopened = await client.get(
        f"/api/v1/users/{peer['user_id']}", headers=auth_headers(viewer["token"])
    )
    assert reopened.status_code == 200, reopened.text


async def test_undoing_a_block_reopens_the_profile_it_closed(client: AsyncClient) -> None:
    viewer = await _person(client, "blocks-profile-viewer@befos.app", "Марк")
    peer = await _person(client, "blocks-profile-peer@befos.app", "Нина")
    await _block(client, viewer, peer["user_id"])
    headers = auth_headers(viewer["token"])

    assert (
        await client.get(f"/api/v1/users/{peer['user_id']}", headers=headers)
    ).status_code == 404

    removed = await client.delete(f"/api/v1/users/{peer['user_id']}/block", headers=headers)
    assert removed.status_code == 200, removed.text
    assert (
        await client.get(f"/api/v1/users/{peer['user_id']}", headers=headers)
    ).status_code == 200, "the row is gone and the profile is still shut"


async def test_undoing_a_block_does_not_resurrect_the_pair_it_dissolved(
    client: AsyncClient, idor_pair
) -> None:
    """A match the block deleted stays deleted: an unblock is not a second tap of «Нравится».

    Re-creating the pair would write a relationship the other person never agreed to resume and hand
    back a chat whose rows the block already took, so the route returns the person to the deck and
    leaves the dissolved pair alone.
    """
    a, b, match_id = idor_pair
    await _block(client, a, b["user_id"])
    headers = auth_headers(a["token"])
    assert (
        await client.get(f"/api/v1/matches/{match_id}", headers=headers)
    ).status_code == 404

    removed = await client.delete(f"/api/v1/users/{b['user_id']}/block", headers=headers)
    assert removed.status_code == 200, removed.text
    assert (
        await client.get(f"/api/v1/matches/{match_id}", headers=headers)
    ).status_code == 404, "undoing the block brought a dissolved pair back"
    listed = await client.get("/api/v1/matches", headers=headers)
    assert match_id not in [entry["match_id"] for entry in listed.json()["matches"]], listed.text


async def test_after_an_undo_a_like_between_the_two_can_build_a_pair_again(
    client: AsyncClient,
) -> None:
    """The way back to a relationship is the gesture that makes it: both people liking each other."""
    a = await _person(client, "blocks-relike-a@befos.app", "Аня")
    b = await _person(client, "blocks-relike-b@befos.app", "Боря")
    await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    await _block(client, a, b["user_id"])

    shut = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    assert shut.status_code == 404, shut.text

    headers = auth_headers(a["token"])
    removed = await client.delete(f"/api/v1/users/{b['user_id']}/block", headers=headers)
    assert removed.status_code == 200, removed.text
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    assert mutual.status_code in (200, 201), mutual.text
    assert mutual.json()["match_id"], "an undone block still refuses the gesture that makes a pair"


async def test_undoing_a_block_does_not_erase_the_complaint_beside_it(client: AsyncClient) -> None:
    """A report goes to the people who read complaints; undoing a block is not withdrawing one."""
    me = await _person(client, "blocks-report-me@befos.app", "Марк")
    peer = await _person(client, "blocks-report-peer@befos.app", "Нина")
    await _block(client, me, peer["user_id"])
    reported = await client.post(
        f"/api/v1/users/{peer['user_id']}/report",
        json={"reason": "spam", "details": "Однократная жалоба"},
        headers=auth_headers(me["token"]),
    )
    assert reported.status_code == 200, reported.text

    removed = await client.delete(
        f"/api/v1/users/{peer['user_id']}/block", headers=auth_headers(me["token"])
    )
    assert removed.status_code == 200, removed.text
    async with AsyncSessionLocal() as session:
        held = list(
            (
                await session.execute(
                    select(Report.id).where(
                        Report.reporter_id == uuid.UUID(me["user_id"]),
                        Report.reported_id == uuid.UUID(peer["user_id"]),
                    )
                )
            ).all()
        )
    assert len(held) == 1, f"undoing the block took the complaint with it: {held}"


async def test_an_account_that_was_blocked_and_then_deleted_leaves_the_list(
    client: AsyncClient,
) -> None:
    """Deletion purges every edge touching the account, so a list cannot name somebody who is gone."""
    me = await _person(client, "blocks-deleted-me@befos.app", "Марк")
    peer = await _person(client, "blocks-deleted-peer@befos.app", "Нина")
    await _block(client, me, peer["user_id"])
    assert _ids(await _list(client, me)) == [peer["user_id"]]

    gone = await client.delete("/api/v1/users/me", headers=auth_headers(peer["token"]))
    assert gone.status_code == 200, gone.text

    assert await _list(client, me) == [], "the list still names an account that no longer represents a person"
    retry = await client.delete(
        f"/api/v1/users/{peer['user_id']}/block", headers=auth_headers(me["token"])
    )
    assert retry.status_code == 404, retry.text


async def test_two_blocks_written_in_one_second_keep_one_order(client: AsyncClient) -> None:
    """`created_at` alone is not an order: rows with one timestamp would shuffle between reads.

    Written straight into the table, because two taps of a route cannot be held to the same
    microsecond, and the tie-break `id` is exactly what a second of scrolling would otherwise hit.
    """
    me = await _person(client, "blocks-steady-me@befos.app", "Марк")
    a = await _person(client, "blocks-steady-a@befos.app", "Аня")
    b = await _person(client, "blocks-steady-b@befos.app", "Боря")
    moment = datetime(2026, 10, 17, 9, 0, 0, tzinfo=timezone.utc)
    async with AsyncSessionLocal() as session:
        for peer in (a, b):
            await session.execute(
                insert(Block).values(
                    blocker_id=uuid.UUID(me["user_id"]),
                    blocked_id=uuid.UUID(peer["user_id"]),
                    created_at=moment,
                    updated_at=moment,
                )
            )
        await session.commit()

    first = _ids(await _list(client, me))
    second = _ids(await _list(client, me))
    assert set(first) == {a["user_id"], b["user_id"]}, first
    assert first == second, "two reads of the same state answered with two different orders"

    async with AsyncSessionLocal() as session:
        rows = list(
            (
                await session.execute(
                    select(Block.id, Block.blocked_id).where(
                        Block.blocker_id == uuid.UUID(me["user_id"]),
                        Block.created_at == moment,
                    )
                )
            ).all()
        )
    expected = [str(blocked) for _, blocked in sorted(rows, key=lambda row: str(row[0]), reverse=True)]
    assert first == expected, (
        f"the tie-break the query states (`id` descending) is not what the list returned: {first}"
    )


async def test_an_undo_racing_a_like_leaves_the_pair_either_matched_or_blocked(
    client: AsyncClient,
) -> None:
    """The invariant the pair lock keeps: no committed match coexists with a committed block.

    A like that lands while an unblock is deleting the row has to wait for it, or the two commit
    together and chat starts serving a pair one of whom still blocks the other.
    """
    a = await _person(client, "blocks-race-a@befos.app", "Аня")
    b = await _person(client, "blocks-race-b@befos.app", "Боря")
    await _block(client, a, b["user_id"])
    await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    headers = auth_headers(a["token"])

    unblock, like = await asyncio.gather(
        client.delete(f"/api/v1/users/{b['user_id']}/block", headers=headers),
        client.post(f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])),
    )
    assert unblock.status_code == 200, unblock.text
    blocked = await _list(client, a)
    matched = await client.get("/api/v1/matches", headers=auth_headers(b["token"]))
    pair_matched = any(
        entry["user_id"] == a["user_id"] for entry in matched.json()["matches"]
    )
    assert not (pair_matched and _ids(blocked) == [b["user_id"]]), (
        "the pair ended up blocked and matched at once, which is what the lock is for"
    )
    assert like.status_code in (200, 201, 404), like.text


@pytest.fixture
async def idor_pair(client: AsyncClient):
    a = await _person(client, "blocks-pair-a@befos.app", "Аня")
    b = await _person(client, "blocks-pair-b@befos.app", "Боря")
    await client.post(f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"]))
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    assert mutual.status_code in (200, 201), mutual.text
    return a, b, mutual.json()["match_id"]
