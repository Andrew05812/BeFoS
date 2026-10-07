"""A write that races the peer's account deletion must not crash and must not outlive the deletion.

``SafetyService.delete_account`` calls ``SocialRepository.purge_social_graph``, which deletes every
``Match`` row involving the caller and lets the schema's ON DELETE CASCADE take their messages and
read receipts with them. Unlike ``SafetyService.block``, the purge did not take the pair advisory
lock that ``ChatService._require_membership_for_write`` and ``MatchService.like`` both serialise on,
so it could land in the window between the send's post-lock ``match_still_present`` re-check and its
own ``INSERT INTO messages`` — the child row references a ``match_id`` that is already gone, asyncpg
raises ``ForeignKeyViolationError``, and the caller gets HTTP 500 for the act of sending a message
while the peer was deleting their account. The same gap in principle lets a like from a peer who had
already been liked back commit a fresh ``Match`` row whose FK points at a soft-deleted user; no
future cascade cleans it, and every later chat write on that row is refused by membership while the
row itself sits in ``matches`` forever.

The fix has the purge take the same pair advisory lock the writes already serialise on, in a
canonical order across the pairs so two simultaneous deletions cannot interleave. Whichever side
commits first wins cleanly: a send that landed first is cascaded away by the later purge (HTTP 200,
then a follow-up 404 when the caller checks), or the purge lands first and the send's re-check
answers 404 with nothing written. For the like, ``MatchService.like`` re-runs its own target check
under the pair lock, so a deletion that committed while it was waiting turns the like into a 404;
and because the purge now holds the same lock over the DELETE, any like that got its Match written
first is cascaded away by the later purge. Either way the invariant holds: no ``Match`` row
references a soft-deleted user after both tasks finish.
"""

from __future__ import annotations

import asyncio
import uuid

from httpx import AsyncClient
from sqlalchemy import or_, select

from app.core.database import AsyncSessionLocal
from app.models import Match
from app.repositories.chat_repo import ChatRepository
from app.repositories.social_repo import SocialRepository
from .conftest import auth_headers, complete_onboarding, register_and_auth


async def _matched_pair(client: AsyncClient, prefix: str) -> tuple[dict, dict, str]:
    a = await register_and_auth(client, f"{prefix}-a@befos.app")
    b = await register_and_auth(client, f"{prefix}-b@befos.app")
    await complete_onboarding(client, a["token"], name="Аня", gender="female")
    await complete_onboarding(client, b["token"], name="Боря", gender="male")
    await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    second = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    assert second.status_code == 200, second.text
    assert second.json()["match"] is True
    return a, b, second.json()["match_id"]


async def _matches_involving(*user_ids: uuid.UUID) -> list[uuid.UUID]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Match.id).where(
                    or_(Match.user_a_id.in_(user_ids), Match.user_b_id.in_(user_ids))
                )
            )
        ).all()
    return [r[0] for r in rows]


async def test_a_send_racing_the_delete_that_dissolves_its_match_is_refused_not_crashed(
    client: AsyncClient, monkeypatch
) -> None:
    """The purge, unlike block, did not hold the pair lock — the send's INSERT saw an absent match.

    Reproduced by holding the send right after its post-lock ``match_still_present`` re-check, so
    the delete gets a clean window to commit its DELETE FROM matches before the send's own INSERT.
    Pre-fix, ``session.flush`` inside ``add_message`` raises ``asyncpg.ForeignKeyViolationError``
    against ``messages_match_id_fkey``, the generic exception handler returns 500, and the send
    body is a stack trace rather than a message id.
    """
    a, b, match_id = await _matched_pair(client, "deletepurge-send")

    send_reached_recheck = asyncio.Event()
    purge_committed = asyncio.Event()
    original = ChatRepository.match_still_present
    state = {"fired": False}

    async def gated(self, mid):  # type: ignore[no-untyped-def]
        # The re-check is the last moment at which this transaction can still see the match.
        # Hold the send right after it returns, so the delete has to commit — or, once the
        # purge takes the pair lock, fail to commit — before the child INSERT runs. Pre-fix
        # the next step is a bare `INSERT INTO messages` and a foreign-key violation.
        result = await original(self, mid)
        if not state["fired"]:
            state["fired"] = True
            send_reached_recheck.set()
            try:
                await asyncio.wait_for(purge_committed.wait(), timeout=1.5)
            except asyncio.TimeoutError:
                pass
        return result

    monkeypatch.setattr(ChatRepository, "match_still_present", gated)

    responses: dict[str, object] = {}

    async def do_send() -> None:
        responses["send"] = await client.post(
            f"/api/v1/matches/{match_id}/messages",
            json={"body": "привет"},
            headers=auth_headers(b["token"]),
        )

    async def do_delete() -> None:
        await asyncio.wait_for(send_reached_recheck.wait(), timeout=6.0)
        responses["delete"] = await client.delete(
            "/api/v1/users/me", headers=auth_headers(a["token"])
        )
        purge_committed.set()

    await asyncio.wait_for(asyncio.gather(do_send(), do_delete()), timeout=30.0)

    delete = responses["delete"]
    assert delete.status_code == 200, delete.text

    send = responses["send"]
    # Pre-fix: the send's INSERT lands against a match_id the purge has already deleted
    # and the FK violation surfaces as 500. Post-fix: either the send writes under the
    # pair lock and the later purge cascades its row away (201), or the purge lands
    # first and the send's post-lock re-check answers 404. Neither is a crash.
    assert send.status_code in (201, 404), send.text

    # And the deletion still dissolves the pair: nothing survives it, not the match,
    # not any child row that slipped in during the race.
    listed = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(b["token"])
    )
    assert listed.status_code == 404, listed.text
    survivors = await _matches_involving(uuid.UUID(a["user_id"]), uuid.UUID(b["user_id"]))
    assert survivors == [], f"a match outlived the deletion of one side: {survivors}"


async def test_a_like_racing_the_peers_delete_leaves_no_match_pointing_at_the_deleted_account(
    client: AsyncClient, monkeypatch
) -> None:
    """Invariant regression on the like side: whatever order the two commit in, no Match references
    the account that just deleted itself. Pre-fix the crash class is the send one above; the like
    gap is the same missing pair lock, and asyncio's cooperative scheduling on this tree happens to
    let A's purge reach its list after B's write commits, so the pre-fix run passes on the
    invariant while still being a structurally unsafe window. What this test guarantees is the
    post-fix property: the purge either acquires the pair lock before B's like commits and sees
    her row, or waits on the lock and B's post-lock target check turns her like into a 404.
    """
    a = await register_and_auth(client, "deletepurge-like-a@befos.app")
    b = await register_and_auth(client, "deletepurge-like-b@befos.app")
    await complete_onboarding(client, a["token"], name="Вера", gender="female")
    await complete_onboarding(client, b["token"], name="Глеб", gender="male")
    # A liked B first, so B's next like is the one that forms the match — the flow that
    # ends in ``ensure_match``. A's concurrent DELETE is the writer we are racing.
    first = await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    assert first.status_code == 200, first.text
    assert first.json()["match"] is False

    like_reached_mutual = asyncio.Event()
    purge_listed = asyncio.Event()
    original_back = SocialRepository.has_liked_back
    original_list = SocialRepository.list_match_ids_for_user
    state = {"fired": False}
    list_state = {"fired": False}

    async def list_then_signal(self, user_id):  # type: ignore[no-untyped-def]
        result = await original_list(self, user_id)
        if not list_state["fired"]:
            list_state["fired"] = True
            purge_listed.set()
        return result

    async def gated_back(self, from_id, to_id):  # type: ignore[no-untyped-def]
        # The mutual check is the last read that decides whether this like is about to
        # write a Match row. Firing the gate here forces the two tasks to interleave:
        # A's DELETE is not started until B has committed to writing a match.
        result = await original_back(self, from_id, to_id)
        if not state["fired"] and result:
            state["fired"] = True
            like_reached_mutual.set()
            try:
                await asyncio.wait_for(purge_listed.wait(), timeout=1.5)
            except asyncio.TimeoutError:
                pass
        return result

    monkeypatch.setattr(SocialRepository, "has_liked_back", gated_back)
    monkeypatch.setattr(SocialRepository, "list_match_ids_for_user", list_then_signal)

    responses: dict[str, object] = {}

    async def do_like() -> None:
        responses["like"] = await client.post(
            f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
        )

    async def do_delete() -> None:
        await asyncio.wait_for(like_reached_mutual.wait(), timeout=6.0)
        responses["delete"] = await client.delete(
            "/api/v1/users/me", headers=auth_headers(a["token"])
        )

    await asyncio.wait_for(asyncio.gather(do_like(), do_delete()), timeout=30.0)

    like = responses["like"]
    delete = responses["delete"]
    assert delete.status_code == 200, delete.text
    # Post-fix, a peer whose account committed first is invisible to the like's post-lock
    # target check, so the like answers 404 rather than 500; if the like commits first the
    # purge now cascades its Match away under the lock and the like answered 200.
    assert like.status_code in (200, 404), like.text

    survivors = await _matches_involving(uuid.UUID(a["user_id"]))
    assert survivors == [], f"a match outlived the deletion of one side: {survivors}"
