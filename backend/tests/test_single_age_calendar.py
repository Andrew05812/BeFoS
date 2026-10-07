"""One calendar for age: the gate, the card and the deck must not disagree about "today".

Three paths turn a stored ``birth_date`` into a number of years: the 18+ gate at signup
(``profile_service._validate_age``), the age printed on a card (``Profile.age``, which every
profile read returns), and the birth-date window that fills the deck
(``DiscoveryRepository._preference_conditions``). They used to ask different clocks: the gate
and the deck took the server's own local calendar (``date.today()``), the card took the UTC
calendar through ``datetime.utcnow()``, which is deprecated in 3.12 and answers a naive value.
Whenever the machine's clock ran ahead of UTC (any timezone east of Greenwich, in the hours
after local midnight) the local sites were already a day further along: the product admitted a
person as an adult and then showed that same person a year younger than the gate had promised.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Profile, User
from app.models.base import utc_today, utcnow
from app.repositories.social_repo import DiscoveryRepository, shift_years
from app.services.profile_service import _validate_age

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

_APP = Path(__file__).resolve().parents[1] / "app"

_CLOCK_MODULES = ("app.models.user", "app.services.profile_service", "app.repositories.social_repo")

# What a module may use to ask for the current date. `utc_today()` and `utcnow()` live in
# app/models/base.py and read the UTC clock; every other spelling reaches for the machine.
_LOCAL_CLOCKS = (
    ("date.today()", "reads the server's own calendar"),
    ("datetime.utcnow()", "is deprecated in 3.12 and answers a naive value"),
    ("datetime.now()", "is naive about the timezone"),
    ("time.time()", "gives no calendar at all"),
)


def test_no_app_module_reads_the_machine_calendar() -> None:
    """Age asked of three clocks is three answers, so one module owns the clock and the rest ask it.

    ``app/models/base.py`` is that module: any file under ``app/`` other than it may not read a
    date or datetime from the machine.
    """
    offenders: list[str] = []
    for path in sorted(_APP.rglob("*.py")):
        if path.relative_to(_APP) == Path("models/base.py"):
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for spelling, why in _LOCAL_CLOCKS:
                if spelling in line:
                    offenders.append(f"{path.relative_to(_APP.parent)}:{line_no}: {why}")
    assert not offenders, (
        "ask app.models.base.utc_today() instead of the machine clock:\n" + "\n".join(offenders)
    )


def _one_calendar_ahead_of_every_clock() -> date:
    """A frozen "today" strictly ahead of both the UTC and the machine calendar.

    A site still reading a clock of its own is then guaranteed to be at least a day behind it,
    so the assertions below cannot pass by accident of the machine's timezone or hour.
    """
    return max(utc_today(), date.today()) + timedelta(days=1)


def _freeze(monkeypatch, shifted: date) -> None:
    """Put every path that asks for "today" on one calendar, ahead of the machine's own."""
    for module in _CLOCK_MODULES:
        monkeypatch.setattr(f"{module}.utc_today", lambda: shifted)


def _bound(conditions: list, index: int) -> date:
    return conditions[index].right.value


def test_the_gate_the_card_and_the_deck_share_one_calendar(monkeypatch) -> None:
    """One birthday answers 18 to all three paths, or the paths have drifted apart again."""
    shifted = _one_calendar_ahead_of_every_clock()
    _freeze(monkeypatch, shifted)

    turning_18_today = shift_years(shifted, 18)
    assert _validate_age(turning_18_today) == 18
    assert Profile(birth_date=turning_18_today).age == 18

    conditions = DiscoveryRepository._preference_conditions([], 18, 30, None)
    assert _bound(conditions, 0) == turning_18_today, "the deck's age_min bound is not the gate's"
    assert _bound(conditions, 1) == shift_years(shifted, 31)


async def _onboard(client: AsyncClient, token: str, *, name: str, birth: date):
    catalog = await client.get("/api/v1/users/interests", headers=auth_headers(token))
    assert catalog.status_code == 200, catalog.text
    items = catalog.json()
    slugs = (items if isinstance(items, list) else items.get("interests", []))[:6]
    return await client.post(
        "/api/v1/users/me/onboarding",
        json={
            "name": name,
            "birth_date": birth.isoformat(),
            "city": "Москва",
            "gender": "male",
            "about": "Проверка одного календаря",
            "dating_goal": "relationship",
            "interests": [s["slug"] for s in slugs],
            "lifestyle": {"smoking": "never", "alcohol": "rarely", "sport": "often"},
            "age_min": 18,
            "age_max": 40,
            "gender_preference": ["female", "male", "nonbinary", "other"],
        },
        headers=auth_headers(token),
    )


async def test_the_gate_admits_exactly_whom_the_card_then_labels_18(
    client: AsyncClient, monkeypatch
) -> None:
    """Signup says adult; the profile read says the same age; a day earlier it says child.

    All three answers come from the frozen calendar, so the pair holds on any host at any hour.
    """
    shifted = _one_calendar_ahead_of_every_clock()
    _freeze(monkeypatch, shifted)

    adult = await register_and_auth(client, "calendar_eighteen@befos.app")
    admitted = await _onboard(
        client, adult["token"], name="Саша", birth=shift_years(shifted, 18)
    )
    assert admitted.status_code == 200, admitted.text

    card = await client.get(
        f"/api/v1/users/{adult['user_id']}", headers=auth_headers(adult["token"])
    )
    assert card.status_code == 200, card.text
    assert card.json()["age"] == 18, "the card contradicts the gate that admitted this account"

    younger = await register_and_auth(client, "calendar_seventeen@befos.app")
    refused = await _onboard(
        client, younger["token"], name="Паша", birth=shift_years(shifted, 18) + timedelta(days=1)
    )
    assert refused.status_code == 422, f"{refused.status_code}: {refused.text[:200]}"


async def _candidate(session: AsyncSession, *, tag: str, birth: date) -> str:
    """A profile written straight to the table, past any gate, to ask only what the deck shows."""
    uid = uuid.uuid4()
    await session.execute(
        insert(User).values(
            id=uid, email=f"calendar_{tag}@befos.app", password_hash="x",
            is_active=True, is_deleted=False,
        )
    )
    await session.execute(
        insert(Profile).values(
            id=uuid.uuid4(), user_id=uid, name=f"Кандидат {tag}", birth_date=birth,
            gender="female", city="Москва", dating_goal="relationship", lifestyle={},
            is_hidden=False, onboarding_completed_at=utcnow(),
        )
    )
    await session.commit()
    return str(uid)


async def test_an_18_viewer_is_never_shown_a_younger_card(
    client: AsyncClient, session: AsyncSession, monkeypatch
) -> None:
    """A deck asked for 18+ carries no card whose own number says less, whoever wrote the row.

    The 17-year-old below is inserted past the gate on purpose: the deck's window is what
    protects the viewer, and it has to be measured on the calendar the card is printed from.
    """
    shifted = _one_calendar_ahead_of_every_clock()
    _freeze(monkeypatch, shifted)

    viewer = await register_and_auth(client, "calendar_viewer@befos.app")
    await complete_onboarding(client, viewer["token"], name="Вера", gender="female")
    await answer_all_questions(client, viewer["token"])
    patch = await client.patch(
        "/api/v1/users/me", json={"age_min": 18, "age_max": 30},
        headers=auth_headers(viewer["token"]),
    )
    assert patch.status_code == 200, patch.text

    adult = await _candidate(session, tag="adult", birth=shift_years(shifted, 18))
    child = await _candidate(session, tag="child", birth=shift_years(shifted, 17))

    feed = await client.get("/api/v1/discover?limit=50", headers=auth_headers(viewer["token"]))
    assert feed.status_code == 200, feed.text
    cards = {card["user_id"]: card["age"] for card in feed.json()["items"]}
    assert cards.get(adult) == 18, "the person who turned 18 on this calendar is missing or mislabelled"
    assert child not in cards, "a 17-year-old reached a viewer who asked for 18+"
    for user_id, age in cards.items():
        assert age >= 18, f"card {user_id} says {age} to a viewer who asked for 18+"
