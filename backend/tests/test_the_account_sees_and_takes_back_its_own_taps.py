"""The taps an account made, read back by that account and taken back by it (stage 116).

Stage 112 opened the door that reads the half of `likes` where `to_user_id` is the reader — «кто меня
выбрал». The other half, the rows the reader's own card wrote toward other people, had still never
been read back to the account that wrote them, and a tap once made could still not be withdrawn:
`POST /users/{id}/like` was the only verb the route owned, so `DELETE` to it stood at 405. This file
names the whole shape of the two doors the stage opens, measured on the account's own gestures.

What the list answers is fixed by the rows, not recomputed — the card carries the number the tapper
was shown when they tapped, and a number that is absent stays absent. Who appears is fixed by the
rules the repository already owns for the inbox: a person must still be showable, and the two must not
already be a pair or hold a block. That pair rule earns its place here for a reason the inbox did not
carry: once a tap is answered back, the relationship lives in the match list, so the door that answers
«кого я ещё не выбрал» has no business holding the same stranger up a second time.

Withdrawal is deliberately narrower than a tap is wide. `DELETE /users/{id}/like` clears only the
requester's own direction, and it leaves a formed pair standing — ending a pair is stage 105's door,
with its own cascade over the chat and the plans, and a "take my tap back" button must not silently
dissolve a conversation the two of them built.

Stage 123 changed one thing in the shape this file pins down: the answer gained `next_cursor`, because
the door had been admitting that taps stood behind its fifty while giving the reader no way to ask for
them. The places here that compare a whole body therefore name the new key, and an empty account answers
`{"likes": [], "has_more": False, "next_cursor": None}`. Rows, order, card fields and the visibility
rules are the ones this file has held since the evening the door opened.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date, timedelta
from typing import Callable

from httpx import AsyncClient
from sqlalchemy import event, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models import Like, Photo, Profile, User
from app.models.base import age_years, utc_today, utcnow
from app.services.discovery_service import LIKED_SHOWN

from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)

BIRTH = date(1996, 5, 10)
LIKED = "/api/v1/discover/liked"


async def _account(client: AsyncClient, tag: str, *, name: str = "Вера") -> dict:
    creds = await register_and_auth(client, f"s116_{tag}@befos.app")
    await complete_onboarding(client, creds["token"], name=name)
    await answer_all_questions(client, creds["token"])
    return creds


async def _liked(client: AsyncClient, token: str) -> dict:
    resp = await client.get(LIKED, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _tap(client: AsyncClient, tapper: dict, target_id: str) -> dict:
    resp = await client.post(
        f"/api/v1/users/{target_id}/like", headers=auth_headers(tapper["token"])
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _seed_taps(
    session: AsyncSession,
    viewer_id: str,
    count: int,
    *,
    tag: str,
    score: float | None = 0.7,
    minutes_apart: int = 5,
) -> list[str]:
    """Tapped people written straight into the tables: this door is about reading, not signing up.

    The rows carry what the live tap carries — a `likes` row, directed *from* the viewer toward the
    seeded person, with the score the viewer's card showed — and their taps step back in time, so the
    newest of them is the one page first.
    """
    ids = [uuid.uuid4() for _ in range(count)]
    await session.execute(
        insert(User),
        [
            {
                "id": uid,
                "email": f"s116_{tag}_t{i}@befos.app",
                "password_hash": "not-a-real-hash",
                "is_active": True,
                "is_deleted": False,
            }
            for i, uid in enumerate(ids)
        ],
    )
    await session.execute(
        insert(Profile),
        [
            {
                "id": uuid.uuid4(),
                "user_id": uid,
                "name": f"Тэп {i}",
                "birth_date": BIRTH,
                "gender": "male",
                "city": "Казань",
                "dating_goal": "relationship",
                "lifestyle": {},
                "is_hidden": False,
                "onboarding_completed_at": utcnow(),
            }
            for i, uid in enumerate(ids)
        ],
    )
    newest = utcnow()
    await session.execute(
        insert(Like),
        [
            {
                "id": uuid.uuid4(),
                "from_user_id": uuid.UUID(viewer_id),
                "to_user_id": uid,
                "compatibility_score": score,
                "created_at": newest - timedelta(minutes=minutes_apart * i),
            }
            for i, uid in enumerate(ids)
        ],
    )
    await session.commit()
    return [str(uid) for uid in ids]


_MARKERS = {
    "taps": "from likes",
    "cards": "from profiles",
    "photos": "from photos",
}


def _listener(seen: list[str]) -> Callable[..., None]:
    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    return _record


def _counts(seen: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for statement in seen:
        for name, marker in _MARKERS.items():
            if marker in statement:
                counts[name] += 1
    return counts


async def _counted_liked(client: AsyncClient, token: str) -> tuple[dict, Counter[str]]:
    seen: list[str] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        body = await _liked(client, token)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    return body, _counts(seen)


async def test_an_account_that_tapped_nobody_gets_an_empty_page(
    client: AsyncClient,
) -> None:
    """Empty answers with the same shape as a full one, and promises no second page."""
    viewer = await _account(client, "empty")
    assert await _liked(client, viewer["token"]) == {
        "likes": [],
        "has_more": False,
        "next_cursor": None,
    }


async def test_a_tap_arrives_with_the_person_and_the_number_my_card_carried(
    client: AsyncClient,
) -> None:
    """The card answers with the tapped person's own profile and the percent stored at the tap.

    The number is not recomputed here: whatever `POST /users/{id}/like` told the tapper is what the
    same account is told when it reads its own gesture back, because that was the number it decided on.
    """
    viewer = await _account(client, "card_v", name="Вера")
    peer = await _account(client, "card_p", name="Пётр")

    tap = await _tap(client, viewer, peer["user_id"])

    body = await _liked(client, viewer["token"])
    assert len(body["likes"]) == 1, body
    card = body["likes"][0]
    assert card["user_id"] == peer["user_id"]
    assert card["name"] == "Пётр"
    assert card["age"] == age_years(BIRTH, utc_today())
    assert card["city"] == "Москва"
    assert card["compatibility"] == tap["compatibility"], (
        "the account is told a different percent than the one it was shown when it tapped"
    )
    assert card["liked_at"], "a tap arrived without the moment it happened"
    assert body["has_more"] is False


async def test_the_leading_photo_of_the_tapped_person_paints_the_card(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """A person I tapped who put a photo up is shown with it; the batch read answers for the page."""
    viewer = await _account(client, "photo_v", name="Вера")
    peer = await _account(client, "photo_p", name="Пётр")
    await session.execute(
        insert(Photo),
        {
            "id": uuid.uuid4(),
            "user_id": uuid.UUID(peer["user_id"]),
            "url": "/uploads/s116_leading.jpg",
            "is_primary": True,
            "position": 0,
        },
    )
    await session.commit()

    await _tap(client, viewer, peer["user_id"])

    body = await _liked(client, viewer["token"])
    assert body["likes"][0]["photo_url"] == "/uploads/s116_leading.jpg"


async def test_a_tap_another_made_at_me_stays_out_of_my_own_list(
    client: AsyncClient,
) -> None:
    """Only rows written by the account are read — the inward half of the table belongs to the inbox."""
    viewer = await _account(client, "in_v", name="Вера")
    peer = await _account(client, "in_p", name="Пётр")

    await _tap(client, peer, viewer["user_id"])

    assert await _liked(client, viewer["token"]) == {
        "likes": [],
        "has_more": False,
        "next_cursor": None,
    }


async def test_the_newest_tap_is_answered_first(client: AsyncClient, session: AsyncSession) -> None:
    """Three taps written minutes apart arrive in the order a reader wants them."""
    viewer = await _account(client, "order")
    ids = await _seed_taps(session, viewer["user_id"], 3, tag="order")

    body = await _liked(client, viewer["token"])
    assert [card["user_id"] for card in body["likes"]] == ids, (
        "the page did not lead with the newest tap"
    )


async def test_a_tap_whose_score_was_never_measured_arrives_without_a_number(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """The column is nullable and the door does not fill it in.

    A `0` here would claim a measured bottom of the scale for a pair nobody scored — the same mistake
    defect 72-1 named for the compatibility bars.
    """
    viewer = await _account(client, "null_v")
    [tapped_id] = await _seed_taps(session, viewer["user_id"], 1, tag="null", score=None)

    body = await _liked(client, viewer["token"])
    assert len(body["likes"]) == 1
    card = body["likes"][0]
    assert card["user_id"] == tapped_id
    assert card["compatibility"] is None, (
        f"an unmeasured tap answered with {card['compatibility']}"
    )


async def test_the_page_carries_the_newest_fifty_taps_and_says_there_are_more(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """A cap that cuts the oldest taps, a flag that admits the rest exist, and a link that reaches them.

    The flag and the link were split apart by stage 123: until then the door admitted the rest existed
    and gave the reader nothing to ask with, so this file's cap guard had to gain the second half.
    """
    viewer = await _account(client, "cap_v")
    ids = await _seed_taps(session, viewer["user_id"], LIKED_SHOWN + 1, tag="cap")

    body = await _liked(client, viewer["token"])
    assert len(body["likes"]) == LIKED_SHOWN
    assert body["has_more"] is True
    assert body["next_cursor"], "the page admitted more taps exist and handed over no way to reach them"
    assert [card["user_id"] for card in body["likes"]] == ids[:LIKED_SHOWN], (
        "the page cut somebody other than the oldest tapped person"
    )


async def test_a_page_exactly_at_the_cap_promises_no_more(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """`has_more` means more rows, not a page that happened to be full — and the cursor agrees."""
    viewer = await _account(client, "capfit_v")
    await _seed_taps(session, viewer["user_id"], LIKED_SHOWN, tag="capfit")

    body = await _liked(client, viewer["token"])
    assert len(body["likes"]) == LIKED_SHOWN
    assert body["next_cursor"] is None, (
        "a page that promises nothing behind it still hands out a link to follow"
    )
    assert body["has_more"] is False


async def test_a_pair_already_formed_is_read_as_a_pair_and_not_as_a_tap(
    client: AsyncClient,
) -> None:
    """Mutual interest lives in the match list; naming it twice would be noise.

    The like row that started it stays in the table — the pair was made of it — but the door that
    answers «кого я ещё не выбрал» has no business holding it up beside the door that says «вы пара»,
    the same exclusion stage 112 struck from the other side.
    """
    viewer = await _account(client, "match_v", name="Вера")
    peer = await _account(client, "match_p", name="Пётр")

    await _tap(client, viewer, peer["user_id"])
    back = await _tap(client, peer, viewer["user_id"])
    assert back["match"] is True, back

    assert await _liked(client, viewer["token"]) == {
        "likes": [],
        "has_more": False,
        "next_cursor": None,
    }

    matches = await client.get("/api/v1/matches", headers=auth_headers(viewer["token"]))
    assert matches.status_code == 200, matches.text
    assert [m["user_id"] for m in matches.json()["matches"]] == [peer["user_id"]]


async def test_a_person_who_hid_their_profile_stops_being_named_by_the_list(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """The tap is older than the hiding; the hiding still wins.

    A profile pulled out of the search is a person who asked not to be shown. Listing them beside the
    fact that I tapped them hands back exactly what they withdrew, and to a reader who already knows
    they exist.
    """
    viewer = await _account(client, "hidden_v")
    [tapped_id] = await _seed_taps(session, viewer["user_id"], 1, tag="hidden")

    assert len((await _liked(client, viewer["token"]))["likes"]) == 1

    await session.execute(
        update(Profile).where(Profile.user_id == uuid.UUID(tapped_id)).values(is_hidden=True)
    )
    await session.commit()

    assert await _liked(client, viewer["token"]) == {
        "likes": [],
        "has_more": False,
        "next_cursor": None,
    }


async def test_a_tapped_person_whose_account_stopped_being_shown_is_not_named(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """Deleted and deactivated accounts leave the list on the same rule the deck uses."""
    viewer = await _account(client, "gone_v")
    deleted_id, inactive_id = await _seed_taps(session, viewer["user_id"], 2, tag="gone")

    await session.execute(
        update(User).where(User.id == uuid.UUID(deleted_id)).values(is_deleted=True)
    )
    await session.execute(
        update(User).where(User.id == uuid.UUID(inactive_id)).values(is_active=False)
    )
    await session.commit()

    assert await _liked(client, viewer["token"]) == {
        "likes": [],
        "has_more": False,
        "next_cursor": None,
    }


async def test_a_block_in_either_direction_takes_the_tap_out_of_the_list(
    client: AsyncClient,
) -> None:
    """The relationship between the two decides, not who wrote the row.

    Both halves matter: I do not want a name I blocked held up as one of my own taps, and a person who
    blocked me has withdrawn the contact — the deck hides both, and this list is the same social graph.
    """
    reader = await _account(client, "block_r", name="Вера")
    blocked_by_reader = await _account(client, "block_a", name="Пётр")
    blocker = await _account(client, "block_b", name="Игорь")

    await _tap(client, reader, blocked_by_reader["user_id"])
    await _tap(client, reader, blocker["user_id"])
    assert len((await _liked(client, reader["token"]))["likes"]) == 2

    await client.post(
        f"/api/v1/users/{blocked_by_reader['user_id']}/block",
        headers=auth_headers(reader["token"]),
    )
    await client.post(
        f"/api/v1/users/{reader['user_id']}/block",
        headers=auth_headers(blocker["token"]),
    )

    body = await _liked(client, reader["token"])
    assert body["likes"] == [], (
        f"a block left {len(body['likes'])} tap(s) readable across it: {[c['name'] for c in body['likes']]}"
    )


async def test_an_anonymous_reader_is_turned_away_before_any_name_is_named(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """401, and no tap of anybody's reaches the body."""
    viewer = await _account(client, "anon_v")
    [tapped_id] = await _seed_taps(session, viewer["user_id"], 1, tag="anon")

    resp = await client.get(LIKED)
    assert resp.status_code == 401, resp.text
    assert tapped_id not in resp.text


async def test_reading_the_list_writes_nothing(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """The door only reads: a page asked for twice answers twice and leaves the table alone."""
    viewer = await _account(client, "quiet_v")
    await _seed_taps(session, viewer["user_id"], 2, tag="quiet")
    before = len((await session.execute(select(Like.id))).all())

    first = await _liked(client, viewer["token"])
    second = await _liked(client, viewer["token"])

    assert first == second
    after = len((await session.execute(select(Like.id))).all())
    assert after == before, "reading the list of taps changed the table of taps"


async def test_the_page_pays_one_read_per_concern_whatever_it_carries(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """Three statements for the whole page: the taps, their cards, their leading photos.

    The bound is on repeats, not on the total. A loop that asked per card would show it here: the
    same three reads for one tap and for a dozen (the shape stage 33 fixed for the match list and
    stage 112 fixed for the inbox).
    """
    one_reader = await _account(client, "batch_one", name="Вера")
    many_reader = await _account(client, "batch_many", name="Вера")
    await _seed_taps(session, one_reader["user_id"], 1, tag="batch_one")
    await _seed_taps(session, many_reader["user_id"], 12, tag="batch_many")

    single_body, single_counts = await _counted_liked(client, one_reader["token"])
    page_body, page_counts = await _counted_liked(client, many_reader["token"])

    assert len(single_body["likes"]) == 1 and len(page_body["likes"]) == 12
    for name in _MARKERS:
        assert single_counts[name] == page_counts[name] == 1, (
            f"{name} read {single_counts[name]} times for one tap and {page_counts[name]} for twelve"
        )


async def test_taking_a_tap_back_removes_it_and_answers_with_the_list_that_is_left(
    client: AsyncClient,
) -> None:
    """The withdrawal returns the page the server holds, the way unblocking and unpassing do."""
    viewer = await _account(client, "undo_v", name="Вера")
    kept = await _account(client, "undo_keep", name="Пётр")
    dropped = await _account(client, "undo_drop", name="Игорь")

    await _tap(client, viewer, kept["user_id"])
    await _tap(client, viewer, dropped["user_id"])

    resp = await client.delete(
        f"/api/v1/users/{dropped['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    assert resp.status_code == 200, resp.text
    assert [c["user_id"] for c in resp.json()["likes"]] == [kept["user_id"]]
    assert await _liked(client, viewer["token"]) == resp.json(), (
        "the answer the withdrawal gave is not the page that follows it"
    )


async def test_taking_a_tap_back_only_touches_my_half_of_the_pair(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """A tap says nothing about the tap the other person made, so their row is not mine to clear."""
    viewer = await _account(client, "half_v", name="Вера")
    peer = await _account(client, "half_p", name="Пётр")

    await _tap(client, viewer, peer["user_id"])
    await _tap(client, peer, viewer["user_id"])  # forms a pair; both rows exist
    theirs = (
        await session.execute(
            select(Like.id).where(Like.from_user_id == uuid.UUID(peer["user_id"]))
        )
    ).scalar_one()

    back = await client.delete(
        f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    assert back.status_code == 200, back.text

    mine_gone = (
        await session.execute(
            select(Like.id).where(Like.from_user_id == uuid.UUID(viewer["user_id"]))
        )
    ).first()
    assert mine_gone is None, "my direction of the pair survived the withdrawal"
    assert (await session.execute(select(Like.id).where(Like.id == theirs))).first() is not None, (
        "the withdrawal deleted a row the requester never owned"
    )


async def test_taking_a_tap_back_leaves_a_formed_pair_standing(
    client: AsyncClient,
) -> None:
    """Un-pairing is the match list's own door; withdrawing a tap must not dissolve a conversation.

    The requester's like row goes, the other half and the pair row do not: `matches` still names the
    stranger, because ending a pair is stage 105's unmatch, with its cascade over the chat and plans.
    """
    viewer = await _account(client, "pair_v", name="Вера")
    peer = await _account(client, "pair_p", name="Пётр")

    await _tap(client, viewer, peer["user_id"])
    back = await _tap(client, peer, viewer["user_id"])
    assert back["match"] is True, back

    resp = await client.delete(
        f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    assert resp.status_code == 200, resp.text

    matches = await client.get("/api/v1/matches", headers=auth_headers(viewer["token"]))
    assert matches.status_code == 200, matches.text
    assert [m["user_id"] for m in matches.json()["matches"]] == [peer["user_id"]], (
        "withdrawing a tap dissolved a pair it had no business ending"
    )


async def test_an_undo_nobody_made_and_a_stranger_answer_alike(
    client: AsyncClient,
) -> None:
    """404 for both, with one message: the route cannot be used to ask whether two others tapped.

    A number this account never tapped and a number that belongs to nobody are the same answer, the
    way stage 114 made undoing a pass you never made indistinguishable.
    """
    viewer = await _account(client, "miss_v", name="Вера")
    stranger = await _account(client, "miss_s", name="Пётр")

    never = await client.delete(
        f"/api/v1/users/{stranger['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    gone = await client.delete(
        f"/api/v1/users/{uuid.uuid4()}/like", headers=auth_headers(viewer["token"])
    )

    assert never.status_code == 404, never.text
    assert gone.status_code == 404, gone.text
    assert never.json() == gone.json(), (
        f"the two answers differ and tell the caller which id exists: {never.json()} vs {gone.json()}"
    )


async def test_taking_back_someone_else_s_tap_is_theirs_to_take(
    client: AsyncClient,
) -> None:
    """A tapped person undoing my tap on them would delete a row they never wrote — they get the 404."""
    reader = await _account(client, "own_r", name="Вера")
    writer = await _account(client, "own_w", name="Пётр")

    await _tap(client, writer, reader["user_id"])

    resp = await client.delete(
        f"/api/v1/users/{writer['user_id']}/like", headers=auth_headers(reader["token"])
    )
    assert resp.status_code == 404, resp.text
    assert [c["user_id"] for c in (await _liked(client, writer["token"]))["likes"]] == [
        reader["user_id"]
    ]


async def test_taking_back_your_own_tap_is_named_rather_than_404(
    client: AsyncClient,
) -> None:
    """Self is an input error, not an absent row — the same split as blocking and passing yourself.

    A tap aimed at yourself can never have been written (`ck_like_not_self`), so answering 404 would
    send the caller looking for a row they just tried to undo.
    """
    viewer = await _account(client, "self_v", name="Вера")

    resp = await client.delete(
        f"/api/v1/users/{viewer['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    assert resp.status_code == 422, resp.text
    assert "your own" in resp.json()["error"]["message"].lower(), resp.text


async def test_a_tap_taken_back_once_is_absent_the_second_time(
    client: AsyncClient,
) -> None:
    """The withdrawal is not idempotent-by-pretence: a second DELETE finds no row and answers 404."""
    viewer = await _account(client, "twice_v", name="Вера")
    peer = await _account(client, "twice_p", name="Пётр")

    await _tap(client, viewer, peer["user_id"])

    first = await client.delete(
        f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    assert first.status_code == 200, first.text

    second = await client.delete(
        f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    assert second.status_code == 404, second.text


async def test_anonymous_withdrawal_is_turned_away_before_anything_is_deleted(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """No token, no removal: 401, and my tap of a stranger still stands in the table."""
    viewer = await _account(client, "anonu_v")
    [tapped_id] = await _seed_taps(session, viewer["user_id"], 1, tag="anonu")

    resp = await client.delete(f"/api/v1/users/{tapped_id}/like")
    assert resp.status_code == 401, resp.text

    rows = (
        await session.execute(
            select(Like.id).where(
                Like.from_user_id == uuid.UUID(viewer["user_id"]),
                Like.to_user_id == uuid.UUID(tapped_id),
            )
        )
    ).first()
    assert rows is not None, "an unauthenticated DELETE reached the table"
