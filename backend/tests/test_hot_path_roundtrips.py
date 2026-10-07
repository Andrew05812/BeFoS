"""The deck page, the pass, the match list and the recommendation page pay per concern.

Stage 19 removed a repeated read from the profile card; the same class of waste sat in four
other places, found by counting the statements each screen sends rather than by timing them:

* ``GET /discover`` read the viewer's profile row and interest list twice — once for the
  preferences that filter the deck, once again inside the compatibility input;
* ``POST /users/{id}/pass`` and the pre-lock check of ``POST /users/{id}/like`` loaded a whole
  person — name, city, every interest — to answer a question about four boolean columns;
* ``GET /matches`` let the default interest loader run on peers whose interests it never shows;
* a cold ``GET /matches/{id}/recommendations`` wrote its eight cards one INSERT at a time.

The bounds below are about repeats, not about totals: one read per concern per page, one write
per page. Each is paired with the answer staying the same, because a shortcut that changes what
the screen shows is not a shortcut.
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Callable

from httpx import AsyncClient
from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models import Profile, Recommendation
from app.repositories.user_repo import UserRepository
from app.services.compatibility_service import CompatibilityService

from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)

_MARKERS = {
    "profile": "profiles.name",
    "vector": "compatibility_profiles.vector",
    "interests": "interests.slug",
    "photos": "photos.url",
}


def _listener(seen: list[tuple[str, str]]) -> Callable[..., None]:
    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append((" ".join(statement.lower().split()), str(parameters)))

    return _record


def _reads(seen: list[tuple[str, str]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for statement, _ in seen:
        for name, marker in _MARKERS.items():
            if marker in statement:
                counts[name] += 1
    return counts


def _writes(seen: list[tuple[str, str]], table: str) -> int:
    prefix = f"insert into {table}"
    return sum(1 for statement, _ in seen if statement.startswith(prefix))


def _person_reads(seen: list[tuple[str, str]], marker: str, person_id: str) -> int:
    """Reads of one table that bind this particular person.

    Counting rows of a batch would let the strangers on the page stand in for the viewer's own
    row and hide a repeat; the id in the parameters says whose row this statement fetched.
    """
    return sum(
        1
        for statement, parameters in seen
        if marker in statement and person_id in parameters
    )


def _statements(seen: list[tuple[str, str]], prefix: str) -> int:
    """Statements that begin with this SQL, so a result set can be counted without a marker."""
    return sum(1 for statement, _ in seen if statement.startswith(prefix))


async def _account(client: AsyncClient, email: str, *, name: str, gender: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, gender=gender)
    await answer_all_questions(client, creds["token"])
    return creds


async def _peers(client: AsyncClient, count: int, prefix: str) -> list[dict]:
    return [
        await _account(client, f"{prefix}{i}@befos.app", name=f"Пётр{i}", gender="male")
        for i in range(count)
    ]


async def _counted(client: AsyncClient, coro):
    seen: list[tuple[str, str]] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        resp = await coro
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    return resp, seen


async def _matched_pair(client: AsyncClient, prefix: str) -> tuple[dict, str]:
    """Two onboarded, answered accounts and the match between them."""
    viewer = await _account(client, f"{prefix}_viewer@befos.app", name="Вера", gender="female")
    peer = await _account(client, f"{prefix}_peer@befos.app", name="Пётр", gender="male")
    await client.post(
        f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    back = await client.post(
        f"/api/v1/users/{viewer['user_id']}/like", headers=auth_headers(peer["token"])
    )
    assert back.status_code == 200, back.text
    match_id = back.json()["match_id"]
    assert match_id
    return viewer, match_id


async def test_a_deck_page_reads_the_viewer_once(client: AsyncClient) -> None:
    """One page: the viewer's row, their interests and their answers are each read once."""
    viewer = await _account(client, "s20_viewer@befos.app", name="Вера", gender="female")
    await _peers(client, 6, "s20-c")

    resp, seen = await _counted(
        client, client.get("/api/v1/discover?limit=3", headers=auth_headers(viewer["token"]))
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 3

    # The viewer's id is bound into exactly one read of each of their own rows. Both of these
    # carried it twice before: the preferences came from one read of the profile, the
    # compatibility input from a second one.
    assert _person_reads(seen, _MARKERS["profile"], viewer["user_id"]) == 1, (
        "the deck read the viewer's profile row more than once"
    )
    assert _person_reads(seen, _MARKERS["vector"], viewer["user_id"]) == 1, (
        "the deck read the viewer's answers more than once"
    )


async def test_a_deck_page_reads_each_concern_once_per_batch(client: AsyncClient) -> None:
    """Three batches per page at most — the viewer, the ranked candidates, the delivered ones.

    A page in a test population is also a rebuild: the deck holds fewer than the floor of 40
    undelivered cards, so candidates get ranked here and delivered here too. That is three
    profile reads for three concerns, and the fourth of any kind would be a loader wired into
    this path without being counted.
    """
    viewer = await _account(client, "s20_batch_viewer@befos.app", name="Вера", gender="female")
    await _peers(client, 6, "s20-batch")

    resp, seen = await _counted(
        client, client.get("/api/v1/discover?limit=3", headers=auth_headers(viewer["token"]))
    )
    assert resp.status_code == 200, resp.text

    counts = _reads(seen)
    assert counts["profile"] == 3, f"profile rows read {counts['profile']} times"
    assert counts["interests"] == 3, f"interest lists read {counts['interests']} times"
    assert counts["vector"] == 3, f"answer vectors read {counts['vector']} times"
    assert counts["photos"] == 1, f"photos read {counts['photos']} times"


async def test_the_deck_page_scores_the_people_it_served(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Fewer reads may not change the page: each card's percent is the engine's own answer."""
    viewer = await _account(client, "s20_ref_viewer@befos.app", name="Вера", gender="female")
    await _peers(client, 4, "s20-ref")

    resp, _ = await _counted(
        client, client.get("/api/v1/discover?limit=3", headers=auth_headers(viewer["token"]))
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 3

    service = CompatibilityService(session)
    mine = {
        i.name
        for i in (await UserRepository(session).get_profile(uuid.UUID(viewer["user_id"]))).interests
    }
    for card in items:
        reference = await service.score_pair(
            uuid.UUID(viewer["user_id"]), uuid.UUID(card["user_id"])
        )
        assert card["compatibility"] == reference.overall_percent
        # Six interests each, and the card shows all of them, so the count on the card is
        # comparable with what the viewer is listed as liking.
        assert card["shared_interests_count"] == len(mine & set(card["interests"]))


async def test_a_pass_asks_only_whether_the_person_is_available(client: AsyncClient) -> None:
    """A refusal needs four boolean columns, not a person and their whole interest list."""
    viewer = await _account(client, "s20_pass_viewer@befos.app", name="Вера", gender="female")
    peer = await _account(client, "s20_pass_peer@befos.app", name="Пётр", gender="male")

    resp, seen = await _counted(
        client,
        client.post(
            f"/api/v1/users/{peer['user_id']}/pass", headers=auth_headers(viewer["token"])
        ),
    )
    assert resp.status_code == 200, resp.text
    counts = _reads(seen)
    assert counts["profile"] == 0, "a pass loaded a profile row to decide a yes-or-no"
    assert counts["interests"] == 0, "a pass loaded an interest list to decide a yes-or-no"
    # auth + availability + block check + the pass itself.
    assert len(seen) <= 4, f"{len(seen)} trips to the database to record a pass"


async def test_a_hidden_peer_still_refuses_a_pass(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The boolean check is the deck's rule, so it refuses what the row check refused."""
    viewer = await _account(client, "s20_hide_viewer@befos.app", name="Вера", gender="female")
    peer = await _account(client, "s20_hide_peer@befos.app", name="Пётр", gender="male")

    await session.execute(
        update(Profile).where(Profile.user_id == uuid.UUID(peer["user_id"])).values(
            is_hidden=True
        )
    )
    await session.commit()

    resp, _ = await _counted(
        client,
        client.post(
            f"/api/v1/users/{peer['user_id']}/pass", headers=auth_headers(viewer["token"])
        ),
    )
    assert resp.status_code == 404, resp.text


async def test_the_match_list_never_reads_the_interest_table(client: AsyncClient) -> None:
    """Two pairs, one batch of peers, and no interest list anywhere on the screen.

    ``Profile.interests`` loads by default, so before this was counted the list spent its widest
    query — a scan of `user_interests` on volume — on rows it then did not look at. The screen
    answers with a name, a city, a photo and the percent stored at the like.
    """
    viewer = await _account(client, "s20_list_viewer@befos.app", name="Вера", gender="female")
    for i in range(2):
        peer = await _account(client, f"s20_list_peer{i}@befos.app", name=f"Пётр{i}", gender="male")
        await client.post(
            f"/api/v1/users/{peer['user_id']}/like", headers=auth_headers(viewer["token"])
        )
        await client.post(
            f"/api/v1/users/{viewer['user_id']}/like", headers=auth_headers(peer["token"])
        )

    resp, seen = await _counted(
        client, client.get("/api/v1/matches", headers=auth_headers(viewer["token"]))
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["matches"]) == 2, f"only {len(body['matches'])} pairs came back"

    counts = _reads(seen)
    assert counts["interests"] == 0, "the match list read interest lists it does not show"
    assert counts["vector"] == 0, "the match list rescores pairs it could read off the rows"
    assert counts["profile"] == 1, f"peers read in {counts['profile']} batches"
    assert counts["photos"] == 1, f"photos read in {counts['photos']} batches"

    for row in body["matches"]:
        assert row["name"].startswith("Пётр")
        assert 0 <= row["compatibility"] <= 100


async def test_a_cold_recommendation_page_is_written_once(client: AsyncClient) -> None:
    """Eight cards in one INSERT, and the page still comes back ordered and complete."""
    viewer, match_id = await _matched_pair(client, "s20_rec")

    resp, seen = await _counted(
        client,
        client.get(
            f"/api/v1/matches/{match_id}/recommendations?force=true",
            headers=auth_headers(viewer["token"]),
        ),
    )
    assert resp.status_code == 200, resp.text
    recs = resp.json()["recommendations"]
    assert len(recs) >= 3, f"only {len(recs)} activities came back for a pair"
    assert _writes(seen, "recommendations") == 1, (
        "the recommendation page wrote its cards one INSERT per card"
    )

    positions = [r["position"] for r in recs]
    assert positions == sorted(positions) and len(set(positions)) == len(recs)
    assert all(r["activity"]["title"] for r in recs)
    assert all(0 <= r["score"] <= 100 for r in recs)

    # A write that lost a row would show up as the cached page differing from the cold one.
    cached = await client.get(
        f"/api/v1/matches/{match_id}/recommendations", headers=auth_headers(viewer["token"])
    )
    assert cached.status_code == 200, cached.text
    assert [r["activity"]["id"] for r in cached.json()["recommendations"]] == [
        r["activity"]["id"] for r in recs
    ]


async def test_a_recomputed_page_asks_for_each_half_of_the_pair_once(client: AsyncClient) -> None:
    """A pair is two rows, so its signals are two batches rather than two reads of each concern.

    Scoring the pair needed both profiles, both interest lists and both answer vectors, and asked
    for them one person at a time. The deck already reads a page of people in one statement per
    concern; the same batch over two ids is what this path was missing.
    """
    viewer, match_id = await _matched_pair(client, "s24_pair")

    resp, seen = await _counted(
        client,
        client.get(
            f"/api/v1/matches/{match_id}/recommendations?force=true",
            headers=auth_headers(viewer["token"]),
        ),
    )
    assert resp.status_code == 200, resp.text

    counts = _reads(seen)
    assert counts["profile"] == 1, f"profile rows read {counts['profile']} times for two people"
    assert counts["interests"] == 1, f"interest lists read {counts['interests']} times"
    assert counts["vector"] == 1, f"answer vectors read {counts['vector']} times"


async def test_a_recomputed_page_answers_from_the_rows_it_just_wrote(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Nothing is read back on a path that wrote the page and still holds the catalogue.

    The recomputation ended by SELECTing the page it had INSERTed two statements earlier and by
    SELECTing the catalogue rows it had read to score it. Both result sets belong to this request,
    so the guard is the answer: what comes back has to be what the rows say.
    """
    viewer, match_id = await _matched_pair(client, "s24_back")

    resp, seen = await _counted(
        client,
        client.get(
            f"/api/v1/matches/{match_id}/recommendations?force=true",
            headers=auth_headers(viewer["token"]),
        ),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["recommendations"]
    assert len(body) >= 3, f"only {len(body)} cards came back for a pair"

    # One read of `recommendations` — the cache probe — and one of `activities`, the catalogue.
    assert _statements(seen, "select recommendations.") == 1, (
        "the page was written and read back inside the same request"
    )
    assert _statements(seen, "select activities.") == 1, (
        "the catalogue was read twice for one page"
    )
    assert len(seen) <= 11, f"{len(seen)} trips to the database to rebuild a pair's page"

    await session.rollback()
    stored = list(
        (
            await session.execute(
                select(
                    Recommendation.activity_id,
                    Recommendation.score,
                    Recommendation.position,
                    Recommendation.explanation,
                )
                .where(Recommendation.match_id == uuid.UUID(match_id))
                .order_by(Recommendation.position)
            )
        ).all()
    )
    assert [row[0] for row in stored] == [card["activity"]["id"] for card in body]
    assert [row[2] for row in stored] == [card["position"] for card in body]
    assert [int(round(row[1] * 100)) for row in stored] == [card["score"] for card in body]
    assert [row[3]["reasons"] for row in stored] == [card["reasons"] for card in body]
