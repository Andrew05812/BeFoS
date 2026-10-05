"""What stays behind when a person asks to be deleted.

«Удалить аккаунт» is the one promise in this app that cannot be walked back by the user, so
the claim it makes has to be about the data, not about the screen. The account is soft-deleted
— the schema never hard-deletes a user, so its ON DELETE CASCADE clauses never fire — which
means anything the erasure does not name out loud survives the tap. These tests draw the
line: what describes the person goes, what another person reported stays.
"""
from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import func, insert, select

from app.models import (
    Activity,
    ActivityPreference,
    CompatibilityProfile,
    DiscoveryQueue,
    Profile,
    Report,
)
from app.models import test as answer_rows
from app.services.safety_service import ERASED_BIRTH_DATE, ERASED_DATING_GOAL, ERASED_GENDER

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth


async def _rows(session, model, column, user_id: uuid.UUID) -> int:
    session.expire_all()
    stmt = select(func.count()).select_from(model).where(column == user_id)
    return (await session.execute(stmt)).scalar() or 0


async def _seed_activity_preference(session, user_id: uuid.UUID) -> None:
    """Save an affinity the way the recommendation engine does, over the API's own tables.

    Nothing on the questionnaire path writes this row, and it is part of the same portrait,
    so the erasure is asserted against a row put there by hand.
    """
    activity_id = (await session.execute(select(Activity.id).limit(1))).scalar_one()
    await session.execute(
        insert(ActivityPreference).values(user_id=user_id, activity_id=activity_id, score=0.8)
    )
    await session.commit()


async def test_deleting_an_account_leaves_nothing_that_describes_the_person(
    client: AsyncClient, session
) -> None:
    # A second finished account: the deck only has rows once there is somebody to show.
    shown = await register_and_auth(client, "erased-witness@befos.app")
    await complete_onboarding(client, shown["token"], name="Гриша", gender="male")
    a = await register_and_auth(client, "erased-answers@befos.app")
    await complete_onboarding(client, a["token"], name="Вера", gender="female")
    await answer_all_questions(client, a["token"])
    feed = await client.get("/api/v1/discover?limit=5", headers=auth_headers(a["token"]))
    assert feed.status_code == 200, feed.text
    uid = uuid.UUID(a["user_id"])
    await _seed_activity_preference(session, uid)

    # Before the tap: the answers exist, and so do the vector built from them, the affinity
    # the engine grew, and the deck that records who this person was shown.
    assert await _rows(session, answer_rows.TestAnswer, answer_rows.TestAnswer.user_id, uid) > 0
    assert await _rows(session, answer_rows.TestResult, answer_rows.TestResult.user_id, uid) > 0
    assert await _rows(session, CompatibilityProfile, CompatibilityProfile.user_id, uid) == 1
    assert await _rows(session, ActivityPreference, ActivityPreference.user_id, uid) == 1
    assert await _rows(session, DiscoveryQueue, DiscoveryQueue.viewer_id, uid) > 0

    deleted = await client.delete("/api/v1/users/me", headers=auth_headers(a["token"]))
    assert deleted.status_code == 200, deleted.text

    # After it: nothing left that says how this person answered, or whom they saw.
    assert await _rows(session, answer_rows.TestAnswer, answer_rows.TestAnswer.user_id, uid) == 0
    assert await _rows(session, answer_rows.TestResult, answer_rows.TestResult.user_id, uid) == 0
    assert await _rows(session, CompatibilityProfile, CompatibilityProfile.user_id, uid) == 0
    assert await _rows(session, ActivityPreference, ActivityPreference.user_id, uid) == 0
    assert await _rows(session, DiscoveryQueue, DiscoveryQueue.viewer_id, uid) == 0

    # The person who was shown is untouched: erasure is about the account that asked.
    assert await _rows(session, Profile, Profile.user_id, uuid.UUID(shown["user_id"])) == 1


async def test_deleting_erases_the_date_of_birth_and_the_rest_of_the_identity(
    client: AsyncClient, session
) -> None:
    a = await register_and_auth(client, "erased-identity@befos.app")
    await complete_onboarding(
        client, a["token"], name="Пётр", city="Санкт-Петербург", gender="male",
        goal="marriage", birth_date="1968-03-07",
    )

    deleted = await client.delete("/api/v1/users/me", headers=auth_headers(a["token"]))
    assert deleted.status_code == 200, deleted.text

    session.expire_all()
    profile = (
        await session.execute(select(Profile).where(Profile.user_id == uuid.UUID(a["user_id"])))
    ).scalar_one()

    # These columns cannot be NULL, so erasure writes a value that is no one's real answer:
    # a date nobody was born on in this app's range, a gender the form never offers.
    assert profile.birth_date == ERASED_BIRTH_DATE
    assert profile.gender == ERASED_GENDER
    assert profile.dating_goal == ERASED_DATING_GOAL
    assert profile.name == "Deleted User"
    assert profile.city == ""
    assert profile.about is None
    assert profile.lifestyle == {}
    assert profile.gender_preference == []
    assert profile.city_preference is None
    # The preferences were a statement about who this person wanted to meet.
    assert (profile.age_min, profile.age_max) == (18, 18)


async def test_a_report_survives_the_departure_of_the_account_it_describes(
    client: AsyncClient, session
) -> None:
    """Leaving the app must not undo what somebody else reported.

    The report is the reporter's statement about an incident, and it does not become false
    because the account it names was deleted. Erasing it would make «Удалить аккаунт» a way
    to escape a harassment report, so the boundary of the erasure is drawn here on purpose:
    what describes the person goes, what another person filed stays.
    """
    reporter = await register_and_auth(client, "reporter@befos.app")
    target = await register_and_auth(client, "reported@befos.app")

    filed = await client.post(
        f"/api/v1/users/{target['user_id']}/report",
        headers=auth_headers(reporter["token"]),
        json={"reason": "harassment", "details": "письма не прекращаются"},
    )
    assert filed.status_code == 200, filed.text

    gone = await client.delete("/api/v1/users/me", headers=auth_headers(target["token"]))
    assert gone.status_code == 200, gone.text

    rows = (
        await session.execute(
            select(Report).where(Report.reported_id == uuid.UUID(target["user_id"]))
        )
    ).scalars().all()
    assert [r.reason for r in rows] == ["harassment"]
    assert [r.details for r in rows] == ["письма не прекращаются"]
