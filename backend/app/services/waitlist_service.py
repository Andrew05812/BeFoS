"""The voluntary «скажите мне, когда рядом появятся люди» mark.

It exists because an empty deck has two honest answers now: *the product has nobody near you yet*
and *you asked us to tell you when that changes*. The second is a request, not a subscription — the
person can read it back on the same screen and take it away — so a row is the whole feature. The
account is the key (one mark per person, a second tap updates rather than duplicates), and
`cancelled_at` keeps a withdrawn request legible to an operator instead of erasing the history of
the tap.

What this file deliberately cannot do is notify anybody. There is no delivery channel for a
product notice in this build: mail exists for authentication letters the person asked for, and a
waitlist letter is a different consent. `notified_at` is a place a later stage writes only after
that channel and that consent exist; until then every screen says the mark is stored and promises
no letter, which is what `docs/RELEASE.md` §11 item 10 also records.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.tracker import Event, tracker
from app.core.exceptions import ValidationError
from app.models import Profile, User, WaitlistEntry

MAX_CITY_LENGTH = 120


class WaitlistService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _profile_city(self, user_id) -> str | None:
        city = (
            await self.session.execute(
                select(Profile.city).where(Profile.user_id == user_id)
            )
        ).scalar_one_or_none()
        return (city or "").strip() or None

    @staticmethod
    def _word(entry: WaitlistEntry | None) -> dict:
        joined = entry is not None and entry.cancelled_at is None
        return {
            "joined": joined,
            "city": entry.city if joined else None,
        }

    async def status(self, user: User) -> dict:
        return await self.status_for(user.id)

    async def status_for(self, user_id) -> dict:
        entry = (
            await self.session.execute(
                select(WaitlistEntry).where(WaitlistEntry.user_id == user_id)
            )
        ).scalars().first()
        return self._word(entry)

    async def join(self, user: User, city: str | None) -> dict:
        chosen = (city or "").strip() or await self._profile_city(user.id)
        if chosen is not None and len(chosen) > MAX_CITY_LENGTH:
            raise ValidationError("Название города слишком длинное.")

        # One statement, not read-then-write: two taps racing on a fresh account would otherwise
        # both see no row and both try to insert, and the unique key on `user_id` would turn the
        # second one into a 500 for a request that means exactly what the first one meant.
        await self.session.execute(
            pg_insert(WaitlistEntry)
            .values(user_id=user.id, city=chosen)
            .on_conflict_do_update(
                index_elements=[WaitlistEntry.user_id],
                set_={
                    "city": chosen,
                    "cancelled_at": None,
                    # A new request is not the old one answered: a later delivery stage starts
                    # it clean.
                    "notified_at": None,
                },
            )
        )
        await self.session.commit()
        tracker.track(Event.WAITLIST_JOINED, str(user.id))
        return {"joined": True, "city": chosen}

    async def leave(self, user: User) -> None:
        """Withdraw the mark. Idempotent: leaving twice is still «you are not waiting»."""
        entry = (
            await self.session.execute(
                select(WaitlistEntry).where(WaitlistEntry.user_id == user.id)
            )
        ).scalars().first()
        if entry is None or entry.cancelled_at is not None:
            return
        entry.cancelled_at = datetime.now(timezone.utc)
        await self.session.commit()
        tracker.track(Event.WAITLIST_LEFT, str(user.id))
