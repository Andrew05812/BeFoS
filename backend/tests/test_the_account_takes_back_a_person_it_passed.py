"""A pass is an answer about the deck, not a seal — the account can take it back (stage 114).

`POST /users/{id}/pass` has always written one row and nothing else. Two readers then keep that row
forever: the deck's anti-join (`_acted_conditions`) refuses to rank a candidate the viewer already
answered, and `new_candidate_ids` refuses to even look at a candidate who has *any* row in
`discovery_queue` — so the person who was shown and passed sits in the queue as a seen row, and the
pair stays unreachable by every route the product has. Stage 112 named the same shape from the other
side and refused to copy it into the inbox: dropping the reader's own pass there «would make a pass
irrevocable in secret». This is the door that secret was about.

Undoing a pass therefore has to clear both records, not one of them, and the released person comes
back at the end of the deck: ranks are assigned once and never reassigned (the deck's whole paging
guarantee), so a release re-queues through the normal refill and cannot cut in front of cards that
are already waiting. The list of passes is the account's own — a row where this account is the
*passed* side belongs to the other person's list and is not readable here, the same one-way rule the
blocked list keeps.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import Counter
from datetime import date, timedelta
from typing import Callable

from httpx import AsyncClient
from sqlalchemy import delete, event, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models import DiscoveryQueue, Pass, Photo, Profile, User
from app.models.base import age_years, utc_today, utcnow
from app.services.discovery_service import PASSED_SHOWN

from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)

PASSED = "/api/v1/discover/passed"
BIRTH = date(1996, 5, 10)


async def _account(client: AsyncClient, tag: str, *, name: str = "Вера") -> dict:
    creds = await register_and_auth(client, f"s114_{tag}@befos.app")
    await complete_onboarding(client, creds["token"], name=name)
    await answer_all_questions(client, creds["token"])
    return creds


async def _passed(client: AsyncClient, token: str) -> dict:
    resp = await client.get(PASSED, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _pass(client: AsyncClient, viewer: dict, target_id: str) -> None:
    resp = await client.post(
        f"/api/v1/users/{target_id}/pass", headers=auth_headers(viewer["token"])
    )
    assert resp.status_code == 200, resp.text


async def _undo(client: AsyncClient, viewer: dict, target_id: str) -> dict:
    resp = await client.delete(
        f"/api/v1/users/{target_id}/pass", headers=auth_headers(viewer["token"])
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _deck(client: AsyncClient, token: str, *, max_pages: int = 10) -> list[str]:
    """Every card the deck still hands out, in the order the pages arrive.

    A pass is worth undoing only if the person comes back through the same door that hid them, so the
    assertions below walk the real paging path rather than reading the queue table.
    """
    ids: list[str] = []
    cursor: str | None = None
    for _ in range(max_pages):
        resp = await client.get(
            "/api/v1/discover",
            headers=auth_headers(token),
            params={"limit": 20} if cursor is None else {"limit": 20, "cursor": cursor},
        )
        assert resp.status_code == 200, resp.text
        page = resp.json()
        ids.extend(card["user_id"] for card in page["items"])
        cursor = page.get("next_cursor")
        if not cursor:
            break
    return ids


async def _seed_people(
    session: AsyncSession, viewer_id: str, count: int, *, tag: str
) -> list[str]:
    """Showable profiles written straight into the tables — this page is about reading, not signing up.

    Each row is a person the deck would rank: not deleted, active, a finished onboarding, an age
    inside the viewer's range. Their `passes` rows step back in time, so the newest answer leads.
    """
    ids = [uuid.uuid4() for _ in range(count)]
    await session.execute(
        insert(User),
        [
            {
                "id": uid,
                "email": f"s114_{tag}_p{i}@befos.app",
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
                "name": f"Пропуск {i}",
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
        insert(Pass),
        [
            {
                "id": uuid.uuid4(),
                "from_user_id": uuid.UUID(viewer_id),
                "to_user_id": uid,
                "created_at": newest - timedelta(minutes=5 * i),
            }
            for i, uid in enumerate(ids)
        ],
    )
    await session.commit()
    return [str(uid) for uid in ids]


async def _queue_rows(session: AsyncSession, viewer_id: str, candidate_id: str) -> list[tuple[int, str]]:
    rows = (
        await session.execute(
            select(DiscoveryQueue.rank, DiscoveryQueue.status).where(
                DiscoveryQueue.viewer_id == uuid.UUID(viewer_id),
                DiscoveryQueue.candidate_id == uuid.UUID(candidate_id),
            )
        )
    ).all()
    return [(row[0], row[1]) for row in rows]


async def _highest_rank(
    session: AsyncSession, viewer_id: str, *, excluding: str | None = None
) -> int:
    """The deck's ceiling for this viewer — the rank a refill appends after.

    ``excluding`` drops one candidate's own row from the reading, because the ceiling a release has to
    clear is the one made of the rows that stay. The released pair's old rank is gone with its row, and
    counting it would ask the newcomer to beat a position it no longer holds.
    """
    conditions = [DiscoveryQueue.viewer_id == uuid.UUID(viewer_id)]
    if excluding is not None:
        conditions.append(DiscoveryQueue.candidate_id != uuid.UUID(excluding))
    stmt = (
        select(DiscoveryQueue.rank).where(*conditions).order_by(DiscoveryQueue.rank.desc()).limit(1)
    )
    return int((await session.execute(stmt)).scalar_one())


_MARKERS = {
    "passes": "from passes",
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


async def _counted_page(client: AsyncClient, token: str) -> tuple[dict, Counter[str]]:
    seen: list[str] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        body = await _passed(client, token)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    return body, _counts(seen)


async def test_an_account_that_passed_nobody_gets_an_empty_page(
    client: AsyncClient,
) -> None:
    """Empty answers with the same shape as a full one, and promises no second page."""
    viewer = await _account(client, "empty")
    assert await _passed(client, viewer["token"]) == {"passed": [], "has_more": False}


async def test_a_pass_arrives_with_the_person_and_the_moment_it_was_made(
    client: AsyncClient,
) -> None:
    """The row the deck wrote is readable by the account that wrote it.

    Until this door existed the answer could only be read back by asking the deck again: «show me
    people I have not answered», which by construction never names an answered person.
    """
    viewer = await _account(client, "one_v", name="Вера")
    peer = await _account(client, "one_p", name="Пётр")

    await _pass(client, viewer, peer["user_id"])

    body = await _passed(client, viewer["token"])
    assert len(body["passed"]) == 1, body
    card = body["passed"][0]
    assert card["user_id"] == peer["user_id"]
    assert card["name"] == "Пётр"
    assert card["age"] == age_years(BIRTH, utc_today())
    assert card["city"] == "Москва"
    assert card["passed_at"], "a pass arrived without the moment it happened"
    assert body["has_more"] is False


async def test_the_leading_photo_of_the_passed_person_paints_the_card(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """A person who put a photo up is shown with it; the batch read answers for the page."""
    viewer = await _account(client, "photo_v", name="Вера")
    peer = await _account(client, "photo_p", name="Пётр")
    await session.execute(
        insert(Photo),
        {
            "id": uuid.uuid4(),
            "user_id": uuid.UUID(peer["user_id"]),
            "url": "/uploads/s114_leading.jpg",
            "is_primary": True,
            "position": 0,
        },
    )
    await session.commit()

    await _pass(client, viewer, peer["user_id"])

    body = await _passed(client, viewer["token"])
    assert body["passed"][0]["photo_url"] == "/uploads/s114_leading.jpg"


async def test_the_newest_pass_is_answered_first(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """Three answers written minutes apart arrive in the order a reader wants them."""
    viewer = await _account(client, "order")
    ids = await _seed_people(session, viewer["user_id"], 3, tag="order")

    body = await _passed(client, viewer["token"])
    assert [card["user_id"] for card in body["passed"]] == ids, (
        "the page did not lead with the newest pass"
    )


async def test_the_page_carries_the_newest_fifty_passes_and_says_there_are_more(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """A cap that cuts the oldest answers, and a flag that admits the rest exist."""
    viewer = await _account(client, "cap_v")
    ids = await _seed_people(session, viewer["user_id"], PASSED_SHOWN + 1, tag="cap")

    body = await _passed(client, viewer["token"])
    assert len(body["passed"]) == PASSED_SHOWN
    assert body["has_more"] is True
    assert [card["user_id"] for card in body["passed"]] == ids[:PASSED_SHOWN], (
        "the page cut somebody other than the oldest answer"
    )


async def test_a_page_exactly_at_the_cap_promises_no_more(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """`has_more` means more rows, not a page that happened to be full."""
    viewer = await _account(client, "capfit_v")
    await _seed_people(session, viewer["user_id"], PASSED_SHOWN, tag="capfit")

    body = await _passed(client, viewer["token"])
    assert len(body["passed"]) == PASSED_SHOWN
    assert body["has_more"] is False


async def test_the_passed_list_and_the_deck_never_name_the_same_person(
    client: AsyncClient,
) -> None:
    """The two readers of the deck's rule agree, because they read the same rows.

    This is the shape that made the pass feel final: the deck stopped naming the person, and no other
    door named them either. A list that contradicted the deck would be a second, worse bug.
    """
    viewer = await _account(client, "deck_v", name="Вера")
    peer = await _account(client, "deck_p", name="Пётр")

    assert peer["user_id"] in await _deck(client, viewer["token"])
    await _pass(client, viewer, peer["user_id"])

    assert peer["user_id"] not in await _deck(client, viewer["token"])
    assert [card["user_id"] for card in (await _passed(client, viewer["token"]))["passed"]] == [
        peer["user_id"]
    ]


async def test_a_pass_is_answered_once_however_many_times_the_card_was_swiped(
    client: AsyncClient,
) -> None:
    """A double tap writes one row, so the list holds one card and the undo releases one answer.

    `uq_pass_pair` already refused the second row; this is the read that notices.
    """
    viewer = await _account(client, "twice_v", name="Вера")
    peer = await _account(client, "twice_p", name="Пётр")

    await _pass(client, viewer, peer["user_id"])
    await _pass(client, viewer, peer["user_id"])

    body = await _passed(client, viewer["token"])
    assert [card["user_id"] for card in body["passed"]] == [peer["user_id"]]


async def test_a_person_the_reader_liked_stops_being_named_as_passed(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """The like route already deletes the pass row, and this list follows the row, not the history.

    Stage 26 wrote that deletion: liking somebody makes the earlier answer about them moot. A list
    that kept both would offer an undo for a gesture the account has already taken back.
    """
    viewer = await _account(client, "like_v", name="Вера")
    peer = await _account(client, "like_p", name="Пётр")

    await _pass(client, viewer, peer["user_id"])
    assert len((await _passed(client, viewer["token"]))["passed"]) == 1

    liked = await client.post(
        f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    assert liked.status_code == 200, liked.text

    assert await _passed(client, viewer["token"]) == {"passed": [], "has_more": False}


async def test_a_pass_about_the_reader_belongs_to_the_other_persons_list(
    client: AsyncClient,
) -> None:
    """One-way on purpose: the rows this account wrote, and only those.

    Somebody else's answer about the reader is that account's own record; reading it here would let
    one person see who passed whom.
    """
    reader = await _account(client, "dir_r", name="Вера")
    other = await _account(client, "dir_o", name="Пётр")

    await _pass(client, other, reader["user_id"])

    assert await _passed(client, reader["token"]) == {"passed": [], "has_more": False}
    assert [c["user_id"] for c in (await _passed(client, other["token"]))["passed"]] == [
        reader["user_id"]
    ]


async def test_undoing_a_pass_takes_that_person_off_the_list(
    client: AsyncClient,
) -> None:
    """The door that answers also answers back, with the list that is left."""
    viewer = await _account(client, "undo_v", name="Вера")
    first = await _account(client, "undo_a", name="Пётр")
    second = await _account(client, "undo_b", name="Игорь")

    await _pass(client, viewer, first["user_id"])
    await _pass(client, viewer, second["user_id"])

    body = await _undo(client, viewer, first["user_id"])
    assert [card["user_id"] for card in body["passed"]] == [second["user_id"]], (
        "the undo did not answer with the list the screen has to paint"
    )
    assert (await _passed(client, viewer["token"]))["passed"] == body["passed"]


async def test_undoing_a_pass_opens_the_deck_again(
    client: AsyncClient,
) -> None:
    """The whole point of the door: a person the reader dismissed can be met again.

    Both records have to go. The `passes` row is what the deck's anti-join reads, and the
    `discovery_queue` row is what `new_candidate_ids` reads before it ranks anybody at all.
    """
    viewer = await _account(client, "back_v", name="Вера")
    peer = await _account(client, "back_p", name="Пётр")

    # The walk first, so the pair has both records by the time the undo is asked to clear them.
    assert peer["user_id"] in await _deck(client, viewer["token"])
    await _pass(client, viewer, peer["user_id"])
    assert peer["user_id"] not in await _deck(client, viewer["token"])

    await _undo(client, viewer, peer["user_id"])

    assert peer["user_id"] in await _deck(client, viewer["token"])


async def test_the_queue_row_alone_is_enough_to_keep_a_person_out(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """Why the undo must clear two rows: deleting only the answer restores nothing.

    Shot against the tree before this stage, where that is all the product does. It stays in the file
    afterwards as the reason: a release that removed just the `passes` row would answer 200, name the
    person on nobody's list, and keep them out of every deck forever.
    """
    viewer = await _account(client, "trap_v", name="Вера")
    peer = await _account(client, "trap_p", name="Пётр")

    assert peer["user_id"] in await _deck(client, viewer["token"])
    await _pass(client, viewer, peer["user_id"])
    assert await _queue_rows(session, viewer["user_id"], peer["user_id"]), (
        "the shown card left no queue row, so this test's premise is gone"
    )

    await session.execute(
        delete(Pass).where(
            Pass.from_user_id == uuid.UUID(viewer["user_id"]),
            Pass.to_user_id == uuid.UUID(peer["user_id"]),
        )
    )
    await session.commit()

    assert peer["user_id"] not in await _deck(client, viewer["token"])


async def test_a_released_person_waits_at_the_end_of_the_deck(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """A release re-queues through the normal refill, and the deck's ranks are never reassigned.

    Cutting the released person back to the front would move cards the viewer has not seen yet — the
    one thing the stored rank exists to prevent. So the ceiling the newcomer has to clear is the
    highest rank the queue still holds for anybody else.
    """
    viewer = await _account(client, "tail_v", name="Вера")
    peer = await _account(client, "tail_p", name="Пётр")
    other = await _account(client, "tail_o", name="Игорь")

    assert set(await _deck(client, viewer["token"])) == {peer["user_id"], other["user_id"]}
    await _pass(client, viewer, peer["user_id"])
    ceiling = await _highest_rank(session, viewer["user_id"], excluding=peer["user_id"])

    await _undo(client, viewer, peer["user_id"])
    assert peer["user_id"] in await _deck(client, viewer["token"])

    rows = await _queue_rows(session, viewer["user_id"], peer["user_id"])
    assert len(rows) == 1, f"a release wrote {len(rows)} queue rows for one pair"
    assert rows[0][0] > ceiling, (
        f"the released person was queued at rank {rows[0][0]}, ahead of the rank {ceiling} "
        "the deck still held for another card"
    )


async def test_undone_passes_leave_the_other_answers_alone(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """Undoing one row does not release the ones beside it.

    The pair key of `discovery_queue` is per viewer and candidate; a release that deleted the viewer's
    whole queue would hand back every card the deck already served and re-rank a deck that was fine.
    """
    viewer = await _account(client, "kept_v", name="Вера")
    undone = await _account(client, "kept_a", name="Пётр")
    kept = await _account(client, "kept_b", name="Игорь")

    await _deck(client, viewer["token"])
    await _pass(client, viewer, undone["user_id"])
    await _pass(client, viewer, kept["user_id"])

    await _undo(client, viewer, undone["user_id"])

    assert [c["user_id"] for c in (await _passed(client, viewer["token"]))["passed"]] == [
        kept["user_id"]
    ]
    assert kept["user_id"] not in await _deck(client, viewer["token"])
    assert await _queue_rows(session, viewer["user_id"], kept["user_id"]), (
        "a person still passed had their queue row taken away by somebody else's undo"
    )


async def test_the_undo_only_releases_answers_this_account_wrote(
    client: AsyncClient,
) -> None:
    """Direction decides, the same rule that makes unblocking safe: one account cannot free another's.

    Пётр passed Вера; Вера undoing that pass would delete a row she never wrote and put Пётр's answer
    out of existence. She gets the same 404 as a stranger does.
    """
    reader = await _account(client, "own_r", name="Вера")
    writer = await _account(client, "own_w", name="Пётр")

    await _pass(client, writer, reader["user_id"])

    resp = await client.delete(
        f"/api/v1/users/{writer['user_id']}/pass", headers=auth_headers(reader["token"])
    )
    assert resp.status_code == 404, resp.text
    assert [c["user_id"] for c in (await _passed(client, writer["token"]))["passed"]] == [
        reader["user_id"]
    ]


async def test_an_undo_nobody_made_and_a_stranger_answer_alike(
    client: AsyncClient,
) -> None:
    """404 for both, with one message: the route cannot be used to ask whether two others are decided.

    A number this account never passed and a number that belongs to nobody are the same answer,
    the way stage 101 made unblocking somebody you never blocked indistinguishable.
    """
    viewer = await _account(client, "miss_v", name="Вера")
    stranger = await _account(client, "miss_s", name="Пётр")

    never = await client.delete(
        f"/api/v1/users/{stranger['user_id']}/pass", headers=auth_headers(viewer["token"])
    )
    gone = await client.delete(
        f"/api/v1/users/{uuid.uuid4()}/pass", headers=auth_headers(viewer["token"])
    )

    assert never.status_code == 404, never.text
    assert gone.status_code == 404, gone.text
    assert never.json() == gone.json(), (
        f"the two answers differ and tell the caller which id exists: {never.json()} vs {gone.json()}"
    )


async def test_undoing_your_own_answer_is_named_rather_than_404(
    client: AsyncClient,
) -> None:
    """Self is an input error, not an absent row — the same split as blocking yourself.

    A pass aimed at yourself can never have been written (`ck_pass_not_self`), so answering 404 would
    tell the caller to look for the row they just tried to undo.
    """
    viewer = await _account(client, "self_v", name="Вера")

    resp = await client.delete(
        f"/api/v1/users/{viewer['user_id']}/pass", headers=auth_headers(viewer["token"])
    )
    assert resp.status_code == 422, resp.text
    assert "your own" in resp.json()["error"]["message"].lower(), resp.text


async def test_two_simultaneous_undos_release_the_answer_once(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """A retry racing the first request cannot make two queue rows or a phantom release.

    The pair lock is what the like route, the block route and this one share; here it decides which of
    the two DELETEs is the one that took the row.
    """
    viewer = await _account(client, "race_v", name="Вера")
    peer = await _account(client, "race_p", name="Пётр")

    await _deck(client, viewer["token"])
    await _pass(client, viewer, peer["user_id"])
    assert await _queue_rows(session, viewer["user_id"], peer["user_id"]), (
        "the shown card left no queue row, so this test has nothing to release"
    )

    first, second = await asyncio.gather(
        client.delete(
            f"/api/v1/users/{peer['user_id']}/pass", headers=auth_headers(viewer["token"])
        ),
        client.delete(
            f"/api/v1/users/{peer['user_id']}/pass", headers=auth_headers(viewer["token"])
        ),
    )
    codes = sorted([first.status_code, second.status_code])
    assert codes == [200, 404], f"two undos answered {codes}"
    assert await _queue_rows(session, viewer["user_id"], peer["user_id"]) == [], (
        "the pair is still held in the deck after the answer was released"
    )


async def test_a_person_who_deleted_their_account_leaves_the_list(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """The card is built from a profile that still belongs to somebody who is here.

    Deleted accounts leave the blocked list on this rule too, and the deck's own conditions drop them
    long before a card is built.
    """
    viewer = await _account(client, "gone_v")
    [gone_id] = await _seed_people(session, viewer["user_id"], 1, tag="gone")

    assert len((await _passed(client, viewer["token"]))["passed"]) == 1

    await session.execute(
        update(User).where(User.id == uuid.UUID(gone_id)).values(is_deleted=True)
    )
    await session.commit()

    assert await _passed(client, viewer["token"]) == {"passed": [], "has_more": False}


async def test_an_anonymous_reader_is_turned_away_from_both_doors(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """401 on the list and on the undo, and no name of anybody's reaches the body."""
    viewer = await _account(client, "anon_v")
    [peer_id] = await _seed_people(session, viewer["user_id"], 1, tag="anon")

    listing = await client.get(PASSED)
    undoing = await client.delete(f"/api/v1/users/{peer_id}/pass")

    assert listing.status_code == 401, listing.text
    assert undoing.status_code == 401, undoing.text
    assert peer_id not in listing.text


async def test_reading_the_passed_list_writes_nothing(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """The door only reads: a page asked for twice answers twice and leaves the table alone."""
    viewer = await _account(client, "quiet_v")
    await _seed_people(session, viewer["user_id"], 2, tag="quiet")
    before = len((await session.execute(select(Pass.id))).all())

    first = await _passed(client, viewer["token"])
    second = await _passed(client, viewer["token"])

    assert first == second
    after = len((await session.execute(select(Pass.id))).all())
    assert after == before, "reading the list of passes changed the table of passes"


async def test_the_page_pays_one_read_per_concern_whatever_it_carries(
    client: AsyncClient, session: AsyncSession,
) -> None:
    """Three statements for the whole page: the answers, their cards, their leading photos.

    The bound is on repeats, not on the total. A loop that asked per card would show it here: the same
    three reads for one answer and for a dozen, the shape stage 33 fixed for the match list and
    stage 112 held for the inbox.
    """
    one_viewer = await _account(client, "batch_one", name="Вера")
    many_viewer = await _account(client, "batch_many", name="Вера")
    await _seed_people(session, one_viewer["user_id"], 1, tag="batch_one")
    await _seed_people(session, many_viewer["user_id"], 12, tag="batch_many")

    single_body, single_counts = await _counted_page(client, one_viewer["token"])
    page_body, page_counts = await _counted_page(client, many_viewer["token"])

    assert len(single_body["passed"]) == 1 and len(page_body["passed"]) == 12
    for name in _MARKERS:
        assert single_counts[name] == page_counts[name] == 1, (
            f"{name} read {single_counts[name]} times for one pass and {page_counts[name]} for twelve"
        )
