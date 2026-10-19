"""The taps that pointed at an account, read back by the account they pointed at (stage 112).

`likes` has always stored the whole story of a gesture: who tapped, whom they tapped, and the
percent the tapper's own card carried at that moment. Only one of those three has ever been read
from the reader's side — `has_liked_back` asks whether one named stranger tapped, and the deck's
anti-join asks whether the viewer did. Nobody asked the account's own question, «кто меня выбрал»,
so nine rows of taps could sit pointing at a person who was never told.

What the door answers is therefore fixed by the rows, not recomputed: the card carries the number
the tapper was shown, and a number that is absent stays absent. Who appears is fixed by rules the
repository already owns — a person must still be showable, and the two must not already be a pair
or hold a block — plus one rule this door adds on purpose: the viewer's own pass does not hide a
tap, because a pass is an answer about the deck, not a seal on what somebody else said.
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
from app.services.discovery_service import LIKED_ME_SHOWN

from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)

BIRTH = date(1996, 5, 10)
INBOX = "/api/v1/discover/liked-me"


async def _account(client: AsyncClient, tag: str, *, name: str = "Вера") -> dict:
    creds = await register_and_auth(client, f"s112_{tag}@befos.app")
    await complete_onboarding(client, creds["token"], name=name)
    await answer_all_questions(client, creds["token"])
    return creds


async def _inbox(client: AsyncClient, token: str) -> dict:
    resp = await client.get(INBOX, headers=auth_headers(token))
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
    """Tappers written straight into the tables: this door is about reading, not signing up.

    The rows carry what the live tap carries — a `likes` row with the score the tapper's card
    showed — and their taps step back in time, so the newest of them is the one page first.
    """
    ids = [uuid.uuid4() for _ in range(count)]
    await session.execute(
        insert(User),
        [
            {
                "id": uid,
                "email": f"s112_{tag}_t{i}@befos.app",
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
                "from_user_id": uid,
                "to_user_id": uuid.UUID(viewer_id),
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


async def _counted_inbox(client: AsyncClient, token: str) -> tuple[dict, Counter[str]]:
    seen: list[str] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        body = await _inbox(client, token)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    return body, _counts(seen)


async def test_an_account_nobody_tapped_gets_an_empty_page(
    client: AsyncClient,
) -> None:
    """Empty answers with the same shape as a full one, and promises no second page."""
    viewer = await _account(client, "empty")
    assert await _inbox(client, viewer["token"]) == {"likes": [], "has_more": False}


async def test_a_tap_arrives_with_the_person_and_the_number_their_card_carried(
    client: AsyncClient,
) -> None:
    """The card answers with the tapper's own profile and the percent stored at the tap.

    The number is not recomputed here: whatever `POST /users/{id}/like` told the tapper is what
    the reader is told, because the tapper is the one who decided on seeing it.
    """
    viewer = await _account(client, "card_v", name="Вера")
    tapper = await _account(client, "card_t", name="Пётр")

    tap = await _tap(client, tapper, viewer["user_id"])

    body = await _inbox(client, viewer["token"])
    assert len(body["likes"]) == 1, body
    card = body["likes"][0]
    assert card["user_id"] == tapper["user_id"]
    assert card["name"] == "Пётр"
    assert card["age"] == age_years(BIRTH, utc_today())
    assert card["city"] == "Москва"
    assert card["compatibility"] == tap["compatibility"], (
        "the reader is told a different percent than the one the tapper was shown"
    )
    assert card["liked_at"], "a tap arrived without the moment it happened"
    assert body["has_more"] is False


async def test_the_leading_photo_of_the_tapper_paints_the_card(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """A tapper who put a photo up is shown with it; the batch read answers for the page."""
    viewer = await _account(client, "photo_v", name="Вера")
    tapper = await _account(client, "photo_t", name="Пётр")
    await session.execute(
        insert(Photo),
        {
            "id": uuid.uuid4(),
            "user_id": uuid.UUID(tapper["user_id"]),
            "url": "/uploads/s112_leading.jpg",
            "is_primary": True,
            "position": 0,
        },
    )
    await session.commit()

    await _tap(client, tapper, viewer["user_id"])

    body = await _inbox(client, viewer["token"])
    assert body["likes"][0]["photo_url"] == "/uploads/s112_leading.jpg"


async def test_the_viewers_own_tap_does_not_land_in_their_own_inbox(
    client: AsyncClient,
) -> None:
    """Only rows pointing at the account are read — the outward half of the table stays out."""
    viewer = await _account(client, "out_v", name="Вера")
    peer = await _account(client, "out_p", name="Пётр")

    await client.post(
        f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(viewer["token"])
    )

    assert await _inbox(client, viewer["token"]) == {"likes": [], "has_more": False}


async def test_the_newest_tap_is_answered_first(client: AsyncClient, session: AsyncSession) -> None:
    """Three taps written minutes apart arrive in the order a reader wants them."""
    viewer = await _account(client, "order")
    ids = await _seed_taps(session, viewer["user_id"], 3, tag="order")

    body = await _inbox(client, viewer["token"])
    assert [card["user_id"] for card in body["likes"]] == ids, (
        "the page did not lead with the newest tap"
    )


async def test_a_tap_whose_score_was_never_measured_arrives_without_a_number(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """The column is nullable and the door does not fill it in.

    A `0` here would claim a measured bottom of the scale for a pair nobody scored — the same
    mistake defect 72-1 named for the compatibility bars.
    """
    viewer = await _account(client, "null_v")
    [tapper_id] = await _seed_taps(session, viewer["user_id"], 1, tag="null", score=None)

    body = await _inbox(client, viewer["token"])
    assert len(body["likes"]) == 1
    card = body["likes"][0]
    assert card["user_id"] == tapper_id
    assert card["compatibility"] is None, (
        f"an unmeasured tap answered with {card['compatibility']}"
    )


async def test_the_page_carries_the_newest_fifty_taps_and_says_there_are_more(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """A cap that cuts the oldest taps, and a flag that admits the rest exist."""
    viewer = await _account(client, "cap_v")
    ids = await _seed_taps(session, viewer["user_id"], LIKED_ME_SHOWN + 1, tag="cap")

    body = await _inbox(client, viewer["token"])
    assert len(body["likes"]) == LIKED_ME_SHOWN
    assert body["has_more"] is True
    assert [card["user_id"] for card in body["likes"]] == ids[:LIKED_ME_SHOWN], (
        "the page cut somebody other than the oldest tapper"
    )


async def test_a_page_exactly_at_the_cap_promises_no_more(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """`has_more` means more rows, not a page that happened to be full."""
    viewer = await _account(client, "capfit_v")
    await _seed_taps(session, viewer["user_id"], LIKED_ME_SHOWN, tag="capfit")

    body = await _inbox(client, viewer["token"])
    assert len(body["likes"]) == LIKED_ME_SHOWN
    assert body["has_more"] is False


async def test_a_pair_already_formed_is_read_as_a_pair_and_not_as_a_tap(
    client: AsyncClient,
) -> None:
    """Mutual interest lives in the match list; naming it twice would be noise.

    The like row that started it stays in the table — the pair was made of it — but the door that
    answers «кто меня ещё не выбрал» has no business holding it up next to the door that already
    says «вы пара».
    """
    viewer = await _account(client, "match_v", name="Вера")
    tapper = await _account(client, "match_t", name="Пётр")

    await _tap(client, tapper, viewer["user_id"])
    back = await _tap(client, viewer, tapper["user_id"])
    assert back["match"] is True, back

    assert await _inbox(client, viewer["token"]) == {"likes": [], "has_more": False}

    matches = await client.get("/api/v1/matches", headers=auth_headers(viewer["token"]))
    assert matches.status_code == 200, matches.text
    assert [m["user_id"] for m in matches.json()["matches"]] == [tapper["user_id"]]


async def test_a_person_who_hid_their_profile_stops_being_named_by_the_inbox(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """The tap is older than the hiding; the hiding still wins.

    A profile pulled out of the search is a person who asked not to be shown. Listing them beside
    the fact that they tapped would hand back exactly what they withdrew, to whoever asks.
    """
    viewer = await _account(client, "hidden_v")
    [tapper_id] = await _seed_taps(session, viewer["user_id"], 1, tag="hidden")

    assert len((await _inbox(client, viewer["token"]))["likes"]) == 1

    await session.execute(
        update(Profile).where(Profile.user_id == uuid.UUID(tapper_id)).values(is_hidden=True)
    )
    await session.commit()

    assert await _inbox(client, viewer["token"]) == {"likes": [], "has_more": False}


async def test_a_tapper_whose_account_stopped_being_shown_is_not_named(
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

    assert await _inbox(client, viewer["token"]) == {"likes": [], "has_more": False}


async def test_a_block_in_either_direction_takes_the_tap_out_of_the_list(
    client: AsyncClient,
) -> None:
    """The relationship between the two decides, not who wrote the row.

    Both halves matter: the reader who blocked somebody does not want their name served back, and
    a tapper who blocked the reader has withdrawn the contact — the deck hides both, and this list
    is the same social graph.
    """
    reader = await _account(client, "block_r", name="Вера")
    blocked_by_reader = await _account(client, "block_a", name="Пётр")
    blocker = await _account(client, "block_b", name="Игорь")

    await _tap(client, blocked_by_reader, reader["user_id"])
    await _tap(client, blocker, reader["user_id"])
    assert len((await _inbox(client, reader["token"]))["likes"]) == 2

    await client.post(
        f"/api/v1/users/{blocked_by_reader['user_id']}/block",
        headers=auth_headers(reader["token"]),
    )
    await client.post(
        f"/api/v1/users/{reader['user_id']}/block",
        headers=auth_headers(blocker["token"]),
    )

    body = await _inbox(client, reader["token"])
    assert body["likes"] == [], (
        f"a block left {len(body['likes'])} tap(s) readable across it: {[c['name'] for c in body['likes']]}"
    )


async def test_a_tap_behind_a_the_reader_passed_still_arrives(
    client: AsyncClient,
) -> None:
    """A pass closes the card, not the record of what the person answered with.

    The deck's own rule drops everybody the reader already acted on; copied here it would hide the
    taps of people the reader passed, and a pass would silently become irrevocable — nobody would
    learn that the person they skipped had said yes.
    """
    reader = await _account(client, "pass_r", name="Вера")
    tapper = await _account(client, "pass_t", name="Пётр")

    passed = await client.post(
        f"/api/v1/users/{tapper['user_id']}/pass", headers=auth_headers(reader["token"])
    )
    assert passed.status_code == 200, passed.text
    await _tap(client, tapper, reader["user_id"])

    body = await _inbox(client, reader["token"])
    assert [card["name"] for card in body["likes"]] == ["Пётр"]


async def test_an_anonymous_reader_is_turned_away_before_any_name_is_named(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """401, and no tap of anybody's reaches the body."""
    viewer = await _account(client, "anon_v")
    [tapper_id] = await _seed_taps(session, viewer["user_id"], 1, tag="anon")

    resp = await client.get(INBOX)
    assert resp.status_code == 401, resp.text
    assert tapper_id not in resp.text


async def test_reading_the_inbox_writes_nothing(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """The door only reads: a page asked for twice answers twice and leaves the table alone."""
    viewer = await _account(client, "quiet_v")
    await _seed_taps(session, viewer["user_id"], 2, tag="quiet")
    before = len((await session.execute(select(Like.id))).all())

    first = await _inbox(client, viewer["token"])
    second = await _inbox(client, viewer["token"])

    assert first == second
    after = len((await session.execute(select(Like.id))).all())
    assert after == before, "reading the list of taps changed the table of taps"


async def test_the_page_pays_one_read_per_concern_whatever_it_carries(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """Three statements for the whole page: the taps, their cards, their leading photos.

    The bound is on repeats, not on the total. A loop that asked per card would show it here: the
    same three reads for one tap and for a dozen (the same shape stage 33 fixed for the match list).
    """
    one_reader = await _account(client, "batch_one", name="Вера")
    many_reader = await _account(client, "batch_many", name="Вера")
    await _seed_taps(session, one_reader["user_id"], 1, tag="batch_one")
    await _seed_taps(session, many_reader["user_id"], 12, tag="batch_many")

    single_body, single_counts = await _counted_inbox(client, one_reader["token"])
    page_body, page_counts = await _counted_inbox(client, many_reader["token"])

    assert len(single_body["likes"]) == 1 and len(page_body["likes"]) == 12
    for name in _MARKERS:
        assert single_counts[name] == page_counts[name] == 1, (
            f"{name} read {single_counts[name]} times for one tap and {page_counts[name]} for twelve"
        )
