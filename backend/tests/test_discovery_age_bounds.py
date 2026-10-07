"""Two boundaries in the discovery age filter that the inclusive bound used to get wrong.

The deck turns the viewer's age band into a birth-date window computed from today's month
and day. Run on Feb 29 that arithmetic asked for a February 29 in a non-leap target year and
raised ``ValueError`` out of the query that backs the app's main screen. And a candidate who
turned ``age_max + 1`` on the very day of the request sat exactly on the lower bound, which
an inclusive ``>=`` let through — so it showed a 31-year-old to a viewer who asked for 30.
"""

from __future__ import annotations

import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Profile, User
from app.models.base import utc_today, utcnow
from app.repositories.social_repo import DiscoveryRepository, shift_years

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth


def test_shift_years_clamps_to_the_last_real_day():
    assert shift_years(date(2028, 2, 29), 25) == date(2003, 2, 28)  # 2003 is not a leap year
    assert shift_years(date(2028, 2, 29), 4) == date(2024, 2, 29)   # 2024 is, day kept
    assert shift_years(date(2025, 3, 31), 1) == date(2024, 3, 31)


def test_preference_conditions_survive_a_february_29(monkeypatch):
    monkeypatch.setattr("app.repositories.social_repo.utc_today", lambda: date(2028, 2, 29))
    conds = DiscoveryRepository._preference_conditions([], 25, 40, None)
    assert len(conds) == 2  # age_min upper bound + age_max lower bound; no gender, no city


async def _candidate(session: AsyncSession, *, tag: str, birth: date) -> str:
    uid = uuid.uuid4()
    await session.execute(
        insert(User).values(
            id=uid, email=f"ageband_{tag}@befos.app", password_hash="x",
            is_active=True, is_deleted=False,
        )
    )
    await session.execute(
        insert(Profile).values(
            id=uuid.uuid4(), user_id=uid, name=f"Кандидат {tag}", birth_date=birth,
            gender="male", city="Москва", dating_goal="relationship", lifestyle={},
            is_hidden=False, onboarding_completed_at=utcnow(),
        )
    )
    await session.commit()
    return str(uid)


async def test_candidate_turning_age_max_plus_one_today_is_excluded(
    client: AsyncClient, session: AsyncSession
):
    creds = await register_and_auth(client, "ageband_v@befos.app")
    await complete_onboarding(client, creds["token"], name="Вера", gender="female")
    await answer_all_questions(client, creds["token"])
    patch = await client.patch(
        "/api/v1/users/me", json={"age_min": 18, "age_max": 30},
        headers=auth_headers(creds["token"]),
    )
    assert patch.status_code == 200, patch.text

    today = utc_today()
    # Born exactly today's month/day N years ago, so their age is precisely N on this request.
    over = await _candidate(session, tag="over", birth=date(today.year - 31, today.month, today.day))
    within = await _candidate(session, tag="within", birth=date(today.year - 30, today.month, today.day))

    feed = await client.get("/api/v1/discover?limit=50", headers=auth_headers(creds["token"]))
    assert feed.status_code == 200, feed.text
    ids = {card["user_id"] for card in feed.json()["items"]}
    assert within in ids, "a candidate who is exactly age_max must be shown"
    assert over not in ids, "a candidate turning age_max + 1 today is one year past the ask"
