from __future__ import annotations

import uuid
from collections import namedtuple
from datetime import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity, ActivityPreference, Match, Recommendation

# One person's whole answer about one idea of one pair, as the row of `activity_preferences` holds it.
# A shape rather than seven positional values because two readers now consume this read and one of
# them (the pair's plans) asks about the instant the row was written too — which half named an idea
# first is a fact about the plan, not about the card.
PreferenceLine = namedtuple(
    "PreferenceLine", "proposed declined meeting_time accepted_time created_at"
)


class ActivityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[Activity]:
        stmt = select(Activity).order_by(Activity.id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_by_ids(self, activity_ids: list[int]) -> dict[int, Activity]:
        """One read for a page of ids, keyed so the caller keeps its own order."""
        if not activity_ids:
            return {}
        stmt = select(Activity).where(Activity.id.in_(activity_ids))
        return {a.id: a for a in (await self.session.execute(stmt)).scalars().all()}

    async def get_by_slug(self, slug: str) -> Activity | None:
        stmt = select(Activity).where(Activity.slug == slug)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_cities(self, cities: list[str]) -> list[Activity]:
        """Activities available in any of the given cities, plus city-agnostic ones."""
        stmt = select(Activity).order_by(Activity.id)
        rows = list((await self.session.execute(stmt)).scalars().all())
        lowered = {c.lower() for c in cities}
        return [a for a in rows if not a.cities or any(c.lower() in lowered for c in a.cities)]

    async def set_preference(
        self, user_id: uuid.UUID, activity_id: int, score: float, match_id: uuid.UUID
    ) -> None:
        # Constraint-decided write: tapping the same activity twice reaches the server
        # before the first insert commits.
        await self.session.execute(
            pg_insert(ActivityPreference)
            .values(
                user_id=user_id, activity_id=activity_id, score=score, match_id=match_id
            )
            .on_conflict_do_update(
                constraint="uq_activity_pref",
                set_={"score": score, "proposed": True},
            )
        )

    async def set_declined(
        self, user_id: uuid.UUID, activity_id: int, match_id: uuid.UUID, declined: bool
    ) -> None:
        """Record that this person pushed the card away — or took that back.

        The row is the same one a proposal writes, and `proposed` is left alone by the update:
        an idea that already went into the pair's chat stays an idea that went into the chat,
        whatever the person decides about it afterwards.
        """
        await self.session.execute(
            pg_insert(ActivityPreference)
            .values(
                user_id=user_id,
                activity_id=activity_id,
                match_id=match_id,
                proposed=False,
                declined=declined,
            )
            .on_conflict_do_update(constraint="uq_activity_pref", set_={"declined": declined})
        )

    async def set_meeting_time(
        self, user_id: uuid.UUID, activity_id: int, match_id: uuid.UUID, when: datetime
    ) -> None:
        """Name the moment this person would meet for this idea, or move the one they named.

        `proposed` is left out of the update: a time is an answer about when, and writing one must
        not mark an idea as sent to the pair's chat. `declined` is cleared, because the two cannot
        both stand — naming a moment to meet for an idea is engaging with it, and a card left
        marked «вы отклонили» beside «вы предложили 19:00» would make the page report a person who
        both refused a plan and arranged it.
        """
        await self.session.execute(
            pg_insert(ActivityPreference)
            .values(
                user_id=user_id,
                activity_id=activity_id,
                match_id=match_id,
                proposed=True,
                meeting_time=when,
            )
            .on_conflict_do_update(
                constraint="uq_activity_pref", set_={"meeting_time": when, "declined": False}
            )
        )

    async def set_accepted_time(
        self, user_id: uuid.UUID, activity_id: int, match_id: uuid.UUID, when: datetime
    ) -> None:
        """Agree to the moment the other half named.

        The insert branch carries `proposed=False`: the person accepting a time has not thereby
        proposed the idea into the chat, and a row that claimed both would hand the other half a
        «выбрали эту идею» mark nobody tapped — the defect stage 63 was opened to close.
        `declined` is cleared for the reason `set_meeting_time` gives.
        """
        await self.session.execute(
            pg_insert(ActivityPreference)
            .values(
                user_id=user_id,
                activity_id=activity_id,
                match_id=match_id,
                proposed=False,
                accepted_time=when,
            )
            .on_conflict_do_update(
                constraint="uq_activity_pref", set_={"accepted_time": when, "declined": False}
            )
        )

    async def decisions_by_pair(
        self, match_id: uuid.UUID, activity_ids: list[int]
    ) -> tuple[
        dict[uuid.UUID, set[int]],
        dict[uuid.UUID, set[int]],
        dict[uuid.UUID, dict[int, tuple[datetime | None, datetime | None]]],
    ]:
        """Which of these cards each half of the pair proposed, which this person pushed away, and
        what each of them named as the moment to meet.

        One statement answers for both people: the questions are the same shape — whose decisions
        does this table record for this pair — and asking them twice, once per person, would cost
        the page a second round trip to say what one row of the answer already says. Both are
        keyed by the person who acted, because a card one half proposed is not a card the other
        half has used: the page still answers per viewer, it just also names the other half's
        proposal. A refusal is keyed too and deliberately not sent out — see the service.

        The times ride along for the same reason: the card has to say «вы договорились на …» and
        «собеседник предлагает …» from the rows this read already fetched, and a second statement
        per card would cost the page the round trip its tap-invariant measures keep count of.
        """
        if not activity_ids:
            return {}, {}, {}
        stmt = (
            select(
                ActivityPreference.user_id,
                ActivityPreference.activity_id,
                ActivityPreference.proposed,
                ActivityPreference.declined,
                ActivityPreference.meeting_time,
                ActivityPreference.accepted_time,
            )
            .where(
                ActivityPreference.match_id == match_id,
                ActivityPreference.activity_id.in_(activity_ids),
            )
        )
        proposed: dict[uuid.UUID, set[int]] = {}
        declined: dict[uuid.UUID, set[int]] = {}
        times: dict[uuid.UUID, dict[int, tuple[datetime | None, datetime | None]]] = {}
        for (
            user_id,
            activity_id,
            was_proposed,
            was_declined,
            meeting_time,
            accepted_time,
        ) in (await self.session.execute(stmt)).all():
            if was_proposed:
                proposed.setdefault(user_id, set()).add(activity_id)
            if was_declined:
                declined.setdefault(user_id, set()).add(activity_id)
            if meeting_time is not None or accepted_time is not None:
                times.setdefault(user_id, {})[activity_id] = (meeting_time, accepted_time)
        return proposed, declined, times

    async def pair_decisions(self, match_id: uuid.UUID) -> dict[int, dict[uuid.UUID, PreferenceLine]]:
        """Every idea this pair has a word about, and what each half's row says about it.

        The unbounded version of `decisions_by_pair`, asked by the plan side of the product: a
        pair's list of plans is not the page of eight cards the engine happens to score today, it is
        every idea the two of them have taken up — including one that has since left the page, which
        is exactly the idea a plan they arranged would belong to. One statement over the pair, keyed
        activity then person, so the projection of every plan costs one round trip rather than two
        per plan.
        """
        stmt = select(
            ActivityPreference.user_id,
            ActivityPreference.activity_id,
            ActivityPreference.proposed,
            ActivityPreference.declined,
            ActivityPreference.meeting_time,
            ActivityPreference.accepted_time,
            ActivityPreference.created_at,
        ).where(ActivityPreference.match_id == match_id)
        out: dict[int, dict[uuid.UUID, PreferenceLine]] = {}
        for (
            user_id,
            activity_id,
            proposed,
            declined,
            meeting_time,
            accepted_time,
            created_at,
        ) in (await self.session.execute(stmt)).all():
            out.setdefault(activity_id, {})[user_id] = PreferenceLine(
                proposed, declined, meeting_time, accepted_time, created_at
            )
        return out

    async def replace_recommendations(
        self, match_id: uuid.UUID, recs: list[dict]
    ) -> None:
        await self.session.execute(delete(Recommendation).where(Recommendation.match_id == match_id))
        if not recs:
            return
        # One statement for the page. Inserting row by row sent eight round trips for the
        # eight cards a pair is shown, and a screen that regenerates its page on a cold cache
        # paid for them on every one of those reads.
        values = [
            {
                "match_id": match_id,
                "activity_id": item["activity_id"],
                "score": item["score"],
                "explanation": item["explanation"],
                "position": position,
            }
            for position, item in enumerate(recs)
        ]
        stmt = pg_insert(Recommendation).values(values)
        await self.session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_match_activity_rec",
                set_={
                    "score": stmt.excluded.score,
                    "explanation": stmt.excluded.explanation,
                    "position": stmt.excluded.position,
                },
            )
        )

    async def list_recommendations(self, match_id: uuid.UUID) -> list[Recommendation]:
        stmt = (
            select(Recommendation)
            .where(Recommendation.match_id == match_id)
            .order_by(Recommendation.position)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def invalidate_for_user(self, user_id: uuid.UUID) -> int:
        """Drop the cached recommendations of every match this user is in.

        A page of activities is scored once and then served from the database, which is
        only honest while both profiles still say what they said then. Once one of them
        moves city, re-takes the test or edits their interests, the stored reasons
        describe somebody who no longer exists on this pair.
        """
        matches = select(Match.id).where(or_(Match.user_a_id == user_id, Match.user_b_id == user_id))
        stmt = delete(Recommendation).where(Recommendation.match_id.in_(matches))
        return (await self.session.execute(stmt)).rowcount or 0
