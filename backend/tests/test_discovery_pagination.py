"""Discovery paging (§3 of the production pass).

The feed used to page by position over a pool that was re-ranked on every request, and
that pool shrank whenever the viewer liked or passed. The position then pointed at a
different card than it had a moment ago, so candidates were skipped silently.

Every test here pages a deck to the end and asserts the same thing: each eligible
candidate arrives exactly once, whatever the viewer does between the pages.
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Interest, Profile, User, UserInterest
from app.models.base import utcnow
from app.models.discovery import DiscoveryQueue
from app.repositories.social_repo import DiscoveryRepository
from app.services.discovery_service import DECK_BATCH

from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)

BIRTH = date(1994, 3, 12)


async def _viewer(client: AsyncClient, tag: str) -> dict:
    creds = await register_and_auth(client, f"deck_{tag}_v@befos.app")
    await complete_onboarding(client, creds["token"], name="Вера", gender="female")
    await answer_all_questions(client, creds["token"])
    return creds


async def _seed_candidates(session: AsyncSession, count: int, *, tag: str) -> list[str]:
    """Insert candidates directly: paging is about the set, not about signing up."""
    ids = [uuid.uuid4() for _ in range(count)]
    await session.execute(
        insert(User),
        [
            {
                "id": uid,
                "email": f"deck_{tag}_c{i}@befos.app",
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
                "name": f"Кандидат {i}",
                "birth_date": BIRTH,
                "gender": "male",
                "city": "Москва",
                "dating_goal": "relationship",
                "lifestyle": {},
                "is_hidden": False,
                # These rows stand in for people who finished signing up; the deck only
                # serves profiles carrying this stamp.
                "onboarding_completed_at": utcnow(),
            }
            for i, uid in enumerate(ids)
        ],
    )
    await session.commit()
    return [str(uid) for uid in ids]


async def _give_interests(
    session: AsyncSession, candidate_ids: list[str], viewer_id: str, n: int = 4
) -> None:
    """Give these candidates interests the viewer actually has, so a ranked deck must put
    them above the candidates left with none."""
    interest_ids = [
        row[0]
        for row in (
            await session.execute(
                select(UserInterest.interest_id)
                .join(Profile, Profile.id == UserInterest.profile_id)
                .where(Profile.user_id == uuid.UUID(viewer_id))
                .limit(n)
            )
        ).all()
    ]
    assert len(interest_ids) == n, "the viewer has too few interests to rank on"
    profile_ids = [
        row[0]
        for row in (
            await session.execute(
                select(Profile.id).where(
                    Profile.user_id.in_([uuid.UUID(i) for i in candidate_ids])
                )
            )
        ).all()
    ]
    await session.execute(
        insert(UserInterest),
        [
            {"profile_id": pid, "interest_id": iid}
            for pid in profile_ids
            for iid in interest_ids
        ],
    )
    await session.commit()


async def _page(
    client: AsyncClient, token: str, *, limit: int = 20, cursor: str | None = None
) -> dict:
    params: dict = {"limit": limit}
    if cursor:
        params["cursor"] = cursor
    resp = await client.get("/api/v1/discover", params=params, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _swipe(client: AsyncClient, token: str, user_id: str, action: str) -> None:
    resp = await client.post(
        f"/api/v1/users/{user_id}/{action}", json={}, headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text


async def _ready_rows(session: AsyncSession, viewer_id: str) -> list[str]:
    """Undelivered deck rows, read on a connection the request never touched."""
    return [
        str(row[0])
        for row in (
            await session.execute(
                select(DiscoveryQueue.candidate_id).where(
                    DiscoveryQueue.viewer_id == uuid.UUID(viewer_id),
                    DiscoveryQueue.status == "ready",
                )
            )
        ).all()
    ]


async def _serve_all(
    client: AsyncClient, token: str, *, limit: int
) -> list[tuple[str, int]]:
    """Page to the end the way a client does, and return (id, compatibility) in the order
    the cards arrived."""
    served: list[tuple[str, int]] = []
    cursor: str | None = None
    for _ in range(100):
        body = await _page(client, token, limit=limit, cursor=cursor)
        served.extend((c["user_id"], c["compatibility"]) for c in body["items"])
        if not body["has_more"]:
            return served
        assert body["next_cursor"], "has_more promised another page but gave no cursor"
        cursor = body["next_cursor"]
    raise AssertionError("the deck never ended")


# ---------- the shape of a page ----------
async def test_nothing_to_show_promises_nothing(client: AsyncClient):
    viewer = await _viewer(client, "empty")
    body = await _page(client, viewer["token"])
    assert body["items"] == []
    assert body["has_more"] is False
    assert body["next_cursor"] is None


async def test_one_candidate_is_served_once(
    client: AsyncClient, session: AsyncSession
):
    viewer = await _viewer(client, "one")
    [only] = await _seed_candidates(session, 1, tag="one")

    first = await _page(client, viewer["token"])
    assert [c["user_id"] for c in first["items"]] == [only]
    assert first["has_more"] is False

    # Asking again — which is what a refresh does — must not serve them a second time.
    assert (await _page(client, viewer["token"]))["items"] == []


async def test_exactly_a_page_then_the_end(client: AsyncClient, session: AsyncSession):
    viewer = await _viewer(client, "exact")
    seeded = await _seed_candidates(session, 20, tag="exact")

    served = [uid for uid, _ in await _serve_all(client, viewer["token"], limit=20)]
    assert len(served) == 20
    assert sorted(served) == sorted(seeded)


async def test_one_over_a_page_spills_over(client: AsyncClient, session: AsyncSession):
    viewer = await _viewer(client, "spill")
    seeded = await _seed_candidates(session, 21, tag="spill")

    served = [uid for uid, _ in await _serve_all(client, viewer["token"], limit=20)]
    assert len(served) == 21
    assert len(set(served)) == 21
    assert sorted(served) == sorted(seeded)


# ---------- the defect this replaced ----------
async def test_more_than_the_old_pool_pages_without_repeats_or_skips(
    client: AsyncClient, session: AsyncSession
):
    """120 candidates: more than twice the 50-card pool the old feed re-ranked per request."""
    viewer = await _viewer(client, "many")
    seeded = await _seed_candidates(session, 120, tag="many")

    served = [uid for uid, _ in await _serve_all(client, viewer["token"], limit=20)]
    assert len(served) == 120
    assert len(set(served)) == 120
    assert sorted(served) == sorted(seeded)


async def test_a_deck_longer_than_one_batch_keeps_filling(
    client: AsyncClient, session: AsyncSession
):
    """More candidates than one refill ranks, so the deck has to be refilled mid-run.

    The first draft of the refill asked "does this viewer have any deck rows?" instead of
    "is this candidate in the deck?", which is true from the second page on: the deck
    stopped at one batch and then promised the viewer there was nobody left. A thousand
    people in the city and 150 cards is exactly what that mistake looks like from outside.
    """
    viewer = await _viewer(client, "long")
    seeded = await _seed_candidates(session, DECK_BATCH * 2 + 7, tag="long")

    served = [uid for uid, _ in await _serve_all(client, viewer["token"], limit=20)]
    assert len(served) == len(set(served)) == DECK_BATCH * 2 + 7
    assert sorted(served) == sorted(seeded)


async def _swipe_across_pages(
    client: AsyncClient, session: AsyncSession, *, tag: str, action: str, count: int
) -> None:
    """Act on cards while paging, and assert the whole deck still arrived exactly once.

    This is what position paging could not promise: each swipe removes a candidate from
    the selection, so the offset the next request asks for names a different card.
    """
    viewer = await _viewer(client, tag)
    seeded = await _seed_candidates(session, count, tag=tag)

    served: list[str] = []
    cursor: str | None = None
    while True:
        body = await _page(client, viewer["token"], limit=10, cursor=cursor)
        cards = body["items"]
        served.extend(c["user_id"] for c in cards)
        if not body["has_more"]:
            break
        cursor = body["next_cursor"]
        for card in cards[:3]:
            await _swipe(client, viewer["token"], card["user_id"], action)

    assert len(served) == len(set(served)) == count
    assert sorted(served) == sorted(seeded)


async def test_like_between_pages_shifts_nothing(client: AsyncClient, session: AsyncSession):
    await _swipe_across_pages(client, session, tag="like", action="like", count=45)


async def test_pass_between_pages_shifts_nothing(client: AsyncClient, session: AsyncSession):
    await _swipe_across_pages(client, session, tag="pass", action="pass", count=45)


async def test_block_between_pages_removes_only_the_blocked(
    client: AsyncClient, session: AsyncSession
):
    viewer = await _viewer(client, "block")
    seeded = await _seed_candidates(session, 30, tag="block")

    served: list[str] = []
    cursor: str | None = None
    blocked: str | None = None
    while True:
        body = await _page(client, viewer["token"], limit=10, cursor=cursor)
        cards = body["items"]
        served.extend(c["user_id"] for c in cards)
        if not body["has_more"]:
            break
        cursor = body["next_cursor"]
        if blocked is None:
            # Block someone from the page just delivered: they must stay gone, and nobody
            # else may be dragged out of the deck with them.
            blocked = cards[0]["user_id"]
            await _swipe(client, viewer["token"], blocked, "block")

    assert blocked is not None
    assert served.count(blocked) == 1
    assert sorted(served) == sorted(seeded)


async def test_hidden_between_pages_is_never_served(
    client: AsyncClient, session: AsyncSession
):
    """A queued candidate who hides must not arrive from the stale deck row."""
    viewer = await _viewer(client, "hidden")
    seeded = await _seed_candidates(session, 25, tag="hidden")

    first = await _page(client, viewer["token"], limit=5)
    delivered = {c["user_id"] for c in first["items"]}
    to_hide = next(uid for uid in seeded if uid not in delivered)  # queued, not yet delivered
    await session.execute(
        update(Profile)
        .where(Profile.user_id == uuid.UUID(to_hide))
        .values(is_hidden=True)
    )
    await session.commit()

    served = [c["user_id"] for c in first["items"]]
    cursor = first["next_cursor"]
    while cursor:
        body = await _page(client, viewer["token"], limit=5, cursor=cursor)
        served.extend(c["user_id"] for c in body["items"])
        cursor = body["next_cursor"] if body["has_more"] else None

    assert to_hide not in served
    assert sorted(served) == sorted(set(seeded) - {to_hide})


async def test_a_page_of_stale_rows_refills_itself_from_behind(
    client: AsyncClient, session: AsyncSession
):
    """More than a whole page went stale: the next request must still deliver a page.

    Dropping stale rows is only half the promise. If the deck held ten people who had all
    hidden and the page asked for five, serving the first five and finding none of them
    showable would read to the viewer as "nobody left" while five more waited behind.
    """
    viewer = await _viewer(client, "stalepage")
    seeded = await _seed_candidates(session, 25, tag="stalepage")

    first = await _page(client, viewer["token"], limit=5)
    assert len(first["items"]) == 5
    # Ten of the rows the deck still holds behind this page, read from the deck itself so
    # the arithmetic below is about undelivered cards and not about seed order.
    to_hide = (await _ready_rows(session, viewer["user_id"]))[:10]
    await session.execute(
        update(Profile).where(Profile.user_id.in_([uuid.UUID(i) for i in to_hide])).values(
            is_hidden=True
        )
    )
    await session.commit()

    second = await _page(client, viewer["token"], limit=5, cursor=first["next_cursor"])
    assert len(second["items"]) == 5, "a page of stale rows came back short instead of refilling"
    assert set(c["user_id"] for c in second["items"]) & set(to_hide) == set()

    served = [c["user_id"] for c in first["items"] + second["items"]]
    cursor = second["next_cursor"]
    while cursor and second["has_more"]:
        second = await _page(client, viewer["token"], limit=5, cursor=cursor)
        served.extend(c["user_id"] for c in second["items"])
        cursor = second["next_cursor"] if second["has_more"] else None

    assert len(served) == len(set(served)) == 15
    assert sorted(served) == sorted(set(seeded) - set(to_hide))


async def test_ranking_change_between_pages_repeats_nothing(
    client: AsyncClient, session: AsyncSession
):
    """Retaking the test re-ranks the whole deck; what was already shown must not return."""
    viewer = await _viewer(client, "rerank")
    seeded = await _seed_candidates(session, 40, tag="rerank")

    served: list[str] = []
    cursor: str | None = None
    for page_index in range(20):
        body = await _page(client, viewer["token"], limit=6, cursor=cursor)
        served.extend(c["user_id"] for c in body["items"])
        if not body["has_more"]:
            break
        cursor = body["next_cursor"]
        if page_index in (1, 3):
            await answer_all_questions(client, viewer["token"], option_index=page_index)

    assert len(served) == len(set(served))
    assert sorted(served) == sorted(seeded)


# ---------- the deck keeps its other promises ----------
async def test_pages_arrive_in_ranked_order(client: AsyncClient, session: AsyncSession):
    """Compatibility ranking survives paging: the better matches come first, page after page."""
    viewer = await _viewer(client, "rank")
    shared = await _seed_candidates(session, 10, tag="rank")
    plain = await _seed_candidates(session, 10, tag="rankplain")
    await _give_interests(session, shared, viewer["user_id"])

    served = await _serve_all(client, viewer["token"], limit=5)
    assert len(served) == 20
    scores = [score for _, score in served]
    assert scores == sorted(scores, reverse=True), "the deck stopped being ranked"
    by_id = dict(served)
    assert min(by_id[who] for who in shared) > max(by_id[who] for who in plain)


async def test_two_requests_at_once_get_different_cards(
    client: AsyncClient, session: AsyncSession
):
    """One deck, the same moment: claiming must not hand the same card to both."""
    viewer = await _viewer(client, "dual")
    await _seed_candidates(session, 40, tag="dual")

    a, b = await asyncio.gather(
        _page(client, viewer["token"], limit=10),
        _page(client, viewer["token"], limit=10),
    )
    ids_a = {c["user_id"] for c in a["items"]}
    ids_b = {c["user_id"] for c in b["items"]}
    assert ids_a and ids_b
    assert ids_a & ids_b == set()


async def test_tampered_cursor_is_refused_as_input(client: AsyncClient, session: AsyncSession):
    viewer = await _viewer(client, "tamper")
    await _seed_candidates(session, 3, tag="tamper")

    forged_number = base64.urlsafe_b64encode(b"123").decode().rstrip("=")
    for forged in ("not-a-cursor", "!!!!", uuid.uuid4().hex, forged_number):
        resp = await client.get(
            "/api/v1/discover",
            params={"cursor": forged},
            headers=auth_headers(viewer["token"]),
        )
        assert resp.status_code == 422, (forged, resp.text)
        assert resp.json()["error"]["code"] == "validation_error"


async def test_a_rebuilt_deck_survives_the_request_that_rebuilt_it(
    client: AsyncClient, session: AsyncSession
):
    """Invalidating the deck is a write, and nothing commits it but the service.

    The request session rolls back on error and commits nowhere else, so an invalidation
    issued after the last commit is simply lost: the viewer retakes the test, the old
    ranking keeps being served, and every assertion about the new one still passes because
    the seen rows already prevent repeats. This reads the table from a second connection to
    catch the case the paging responses cannot see.
    """
    viewer = await _viewer(client, "persist")
    await _seed_candidates(session, 30, tag="persist")
    await _page(client, viewer["token"], limit=5)
    assert len(await _ready_rows(session, viewer["user_id"])) == 25

    await answer_all_questions(client, viewer["token"], option_index=1)
    assert await _ready_rows(session, viewer["user_id"]) == []


async def test_an_edited_preference_survives_the_request_that_edited_it(
    client: AsyncClient, session: AsyncSession
):
    viewer = await _viewer(client, "persist2")
    await _seed_candidates(session, 30, tag="persist2")
    await _page(client, viewer["token"], limit=5)
    assert len(await _ready_rows(session, viewer["user_id"])) == 25

    resp = await client.patch(
        "/api/v1/users/me", json={"age_max": 30}, headers=auth_headers(viewer["token"])
    )
    assert resp.status_code == 200, resp.text
    assert await _ready_rows(session, viewer["user_id"]) == []


async def test_seen_rows_are_what_survives(client: AsyncClient, session: AsyncSession):
    """The seen rows are the memory that keeps a rebuilt deck from repeating."""
    viewer = await _viewer(client, "memory")
    seeded = await _seed_candidates(session, 12, tag="memory")

    served = await _serve_all(client, viewer["token"], limit=5)
    assert len(served) == 12

    statuses = {
        row[0]
        for row in (
            await session.execute(
                select(DiscoveryQueue.status).where(
                    DiscoveryQueue.viewer_id == uuid.UUID(viewer["user_id"])
                )
            )
        ).all()
    }
    assert statuses == {"seen"}
    # Asking again now must not bring any of them back.
    assert await _page(client, viewer["token"], limit=20) == {
        "items": [],
        "next_cursor": None,
        "has_more": False,
    }
    assert sorted(uid for uid, _ in served) == sorted(seeded)


async def test_answering_the_setup_questions_drops_the_deck_ranked_before_them(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Onboarding changes what the viewer wants, so it has to invalidate like any change.

    The feed starts answering as soon as a profile row exists, which means a viewer who
    opens discovery before finishing signup is handed a deck built from the defaults —
    18 to 60, any gender. The claim path re-checks hiding, blocking and deletion, and
    nothing else, so a card the real answers now exclude is still delivered. Every other
    write of these fields goes through ``ProfileService.update``, which drops the deck;
    onboarding writes the same fields and did not.

    The first page asks for two of six candidates on purpose: rows still queued are the
    ones the fix has to throw away, and a page that consumed the whole deck would pass
    for the wrong reason.
    """
    await _seed_candidates(session, 6, tag="pre_onb")
    creds = await register_and_auth(client, "deck_pre_onb_v@befos.app")

    before = await _page(client, creds["token"], limit=2)
    assert len(before["items"]) == 2, "a shell profile must still be served a deck"
    assert before["has_more"], "two of six candidates have to leave the rest queued"

    onboarded = await client.post(
        "/api/v1/users/me/onboarding",
        headers=auth_headers(creds["token"]),
        json={
            "name": "Вера",
            "birth_date": "1996-05-10",
            "city": "Москва",
            "gender": "female",
            "dating_goal": "relationship",
            "interests": [],
            "lifestyle": {},
            # Every seeded candidate was born in 1994, so from this answer on nothing that
            # is still queued is somebody this viewer could be shown.
            "age_min": 18,
            "age_max": 20,
            "gender_preference": ["male"],
        },
    )
    assert onboarded.status_code == 200, onboarded.text

    after = await _page(client, creds["token"], limit=20)
    assert after["items"] == [], (
        "cards the new age band excludes are still being served: "
        f"{[c['name'] for c in after['items']]}"
    )


async def test_a_refill_landing_on_an_occupied_rank_loses_the_row_not_the_person(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Two builds of one deck may not put two cards on the same cursor step.

    This is what happens when a viewer's second request starts before the first has
    written: both read the same `max(rank) + 1` ceiling, and their candidate sets differ by
    one row because the first one had already queued somebody the second then shifts past.
    The batch is inserted `ON CONFLICT DO NOTHING`, so the pair collisions disappear on
    their own — and the row that survives the shift lands on a rank the first batch already
    used. `deck_claim` pages with `rank > :after`, so one of the two cards on that rank is
    behind a step the cursor has already taken: a person vanishes from the deck with no
    error, no log and nothing left to retry.
    """
    viewer = await _viewer(client, "rank_race")
    seeded = await _seed_candidates(session, 6, tag="rank_race")
    repo = DiscoveryRepository(session)
    viewer_id = uuid.UUID(viewer["user_id"])
    ids = [uuid.UUID(candidate) for candidate in seeded]

    await repo.deck_append(
        viewer_id, [(ids[0], 91), (ids[1], 90), (ids[2], 89)], first_rank=0
    )
    await session.commit()
    # The second build saw ids[0] already queued, so its list is one shorter and starts at
    # the same ceiling: ids[3] arrives on rank 2, where ids[2] already sits.
    await repo.deck_append(
        viewer_id, [(ids[1], 90), (ids[2], 89), (ids[3], 88)], first_rank=0
    )
    await session.commit()

    rows = (
        await session.execute(
            select(DiscoveryQueue.rank, DiscoveryQueue.candidate_id)
            .where(DiscoveryQueue.viewer_id == viewer_id)
            .order_by(DiscoveryQueue.rank)
        )
    ).all()
    ranks = [rank for rank, _ in rows]
    assert len(ranks) == len(set(ranks)), f"two cards share a rank, so one is never served: {rows}"

    # Losing the rank is survivable precisely because the loser is not queued at all: the
    # next refill still considers it a person nobody has been shown.
    assert ids[3] not in {candidate for _, candidate in rows}
    fresh = await repo.new_candidate_ids(
        viewer_id=viewer_id,
        gender_pref=[],
        age_min=18,
        age_max=60,
        city=None,
        limit=DECK_BATCH,
    )
    assert ids[3] in fresh, "the candidate whose row was dropped left the deck for good"

    served = await _serve_all(client, viewer["token"], limit=5)
    assert len(served) == len(set(uid for uid, _ in served)), "a card arrived twice"
