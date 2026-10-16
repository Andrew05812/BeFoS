from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.tracker import Event, tracker
from app.core.exceptions import NotFoundError
from app.models import Match
from app.recommendations.engine import ActivitySignal, UserSignal, recommend
from app.repositories.activity_repo import ActivityRepository
from app.repositories.social_repo import SocialRepository
from app.repositories.user_repo import UserRepository
from app.services.plan_service import PlanService
from app.services.plan_time import agreed_instant


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


class RecommendationService:
    """The pair's page of ideas, and the door the card taps come in through.

    The page is this service's own: it scores the catalogue for the two people and caches the answer.
    Everything a tap does to an arrangement belongs to `PlanService`, and the four verbs at the bottom
    of this file are delegations rather than implementations — the same tap on a card and the same tap
    on the pair's plan have to leave the pair's rows in one shape, and a second implementation of the
    hour would be a second story about it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.activities = ActivityRepository(session)
        self.users = UserRepository(session)
        self.social = SocialRepository(session)
        self.plans = PlanService(session)

    async def _require_match(self, match_id: uuid.UUID, user_id: uuid.UUID) -> Match:
        match = await self.session.get(Match, match_id)
        # The same row answered through the same route family has to give the same refusal as
        # `ChatService._require_membership` and `GET /matches/{id}`; a 403 here would say "this
        # pair exists, you are just not in it".
        if match is None or not (match.user_a_id == user_id or match.user_b_id == user_id):
            raise NotFoundError("Match not found.")
        return match

    async def _signals(self, user_ids: list[uuid.UUID]) -> list[UserSignal]:
        """Both halves of the pair in two reads rather than two reads each.

        The deck already batches this: one profile read over a list of ids carries the interest
        loader of everyone in it, and one compatibility read carries all of their vectors. A
        pair is two people, so asking per person cost the same rows twice.
        """
        from app.repositories.test_repo import TestRepository

        profiles = {p.user_id: p for p in await self.users.get_profiles_by_ids(user_ids)}
        vectors = await TestRepository(self.session).get_compatibility_profiles(user_ids)
        signals: list[UserSignal] = []
        for user_id in user_ids:
            profile = profiles.get(user_id)
            cp = vectors.get(user_id)
            signals.append(
                UserSignal(
                    interests={i.slug for i in profile.interests} if profile else set(),
                    vector=cp.vector if cp and isinstance(cp.vector, dict) else {},
                    city=profile.city if profile else "",
                    dating_goal=profile.dating_goal if profile else "",
                    interest_titles={i.slug: i.name for i in profile.interests} if profile else {},
                )
            )
        return signals

    async def for_match(self, match_id: uuid.UUID, user_id: uuid.UUID, *, force: bool = False) -> list[dict]:
        match = await self._require_match(match_id, user_id)
        partner_id = match.user_b_id if match.user_a_id == user_id else match.user_a_id

        existing = await self.activities.list_recommendations(match_id)
        if existing and not force:
            tracker.track(Event.RECOMMENDATION_VIEWED, str(user_id), match=str(match_id))
            return await self._hydrate(existing, user_id, partner_id, match_id)

        a, b = await self._signals([match.user_a_id, match.user_b_id])

        cities = list({c for c in (a.city, b.city) if c})
        catalogue = await self.activities.list_for_cities(cities)
        signals = [
            ActivitySignal(
                activity_id=act.id,
                slug=act.slug,
                title=act.title,
                category=act.category,
                interests=list(act.interests),
                cities=list(act.cities),
                energy=act.energy,
                social=act.social,
            )
            for act in catalogue
        ]
        scored = recommend(signals, a, b, top_n=8)

        recs = [
            {
                "activity_id": s.activity_id,
                "score": round(s.score, 4),
                "explanation": {"reasons": s.reasons},
            }
            for s in scored
        ]
        # The pair advisory lock is the same one `block` (stage 9), `delete_account`'s purge
        # (stage 13) and every chat write (stages 11–12) already serialise on. Without it the
        # wide window between the initial membership read and the INSERT below is a
        # read-then-write race on `recommendations.match_id`, which FKs `matches.id ON DELETE
        # CASCADE`: a concurrent dissolve commits its `DELETE FROM matches` here, the child
        # INSERT references an absent parent, and asyncpg raises `ForeignKeyViolationError`
        # — HTTP 500 on `GET /matches/{id}/recommendations?force=true`. Taking the lock makes
        # the two writers take turns: whoever commits last either writes under the lock (and
        # the later dissolve cascades the row away, 200 then a follow-up 404) or lands first
        # and the post-lock re-check via `select(Match.id)` — fresh snapshot, not the
        # identity map — answers the same 404 that a write into an absent match already gives.
        await self.social.lock_pair(match.user_a_id, match.user_b_id)
        if not await self.social.match_still_present(match_id):
            raise NotFoundError("Match not found.")

        await self.activities.replace_recommendations(match_id, recs)
        await self.session.commit()
        tracker.track(Event.RECOMMENDATION_VIEWED, str(user_id), match=str(match_id), count=len(recs))
        chosen, partner_chosen, declined, times = await self._decisions(
            user_id, partner_id, match_id, [item["activity_id"] for item in recs]
        )
        # The page was just written by this session, with `position` equal to the enumerate order
        # below, and the catalogue rows behind it are the ones `list_for_cities` returned. Asking
        # the database for the page and for those rows again asked for two result sets this
        # request already owns. The conflict clause of `replace_recommendations` cannot fold a
        # card away here: the DELETE above removed every stored page of this match, and one page
        # scores each activity of the catalogue once.
        return self._render(
            [
                (item["activity_id"], item["score"], position, item["explanation"])
                for position, item in enumerate(recs)
            ],
            {act.id: act for act in catalogue},
            chosen,
            partner_chosen,
            declined,
            user_id,
            partner_id,
            times,
        )

    async def _decisions(
        self,
        user_id: uuid.UUID,
        partner_id: uuid.UUID,
        match_id: uuid.UUID,
        activity_ids: list[int],
    ) -> tuple[
        set[int],
        set[int],
        set[int],
        dict[uuid.UUID, dict[int, tuple[datetime | None, datetime | None]]],
    ]:
        """What each half proposed, what the person asking pushed away, and the times they named.

        One read answers for both people, so the page keeps the round trip the tap-invariant
        measures. Split here rather than in the repository: the three sets mean different things
        to the card — one is the viewer's own state, the other is the other half's, the third is
        the viewer's refusal — and the service is the place that knows which of the pair is asking.

        The partner's refusals are read out of the row and dropped here on purpose. A proposal is
        a message the pair already received, so naming it back says nothing new; a refusal never
        left the person's own page, and reporting it would turn a private edit of a list into a
        statement about them that no conversation carries. A named time is not dropped: it is a
        question the other half has to answer, and the card that hides it leaves the pair with no
        way to agree on one.
        """
        proposed, declined, times = await self.activities.decisions_by_pair(match_id, activity_ids)
        return (
            proposed.get(user_id, set()),
            proposed.get(partner_id, set()),
            declined.get(user_id, set()),
            times,
        )

    def _render(
        self,
        rows: list,
        by_id: dict,
        chosen: set[int],
        partner_chosen: set[int],
        declined: set[int],
        user_id: uuid.UUID,
        partner_id: uuid.UUID,
        times: dict[uuid.UUID, dict[int, tuple[datetime | None, datetime | None]]],
    ) -> list[dict]:
        out: list[dict] = []
        for activity_id, score, position, explanation in rows:
            act = by_id.get(activity_id)
            if act is None:
                continue
            reasons = explanation.get("reasons", []) if isinstance(explanation, dict) else []
            my_time, my_accept = times.get(user_id, {}).get(activity_id, (None, None))
            partner_time, partner_accept = times.get(partner_id, {}).get(activity_id, (None, None))
            out.append(
                {
                    "activity": {
                        "id": act.id,
                        "slug": act.slug,
                        "title": act.title,
                        "description": act.description,
                        "category": act.category,
                        "energy": act.energy,
                        "social": act.social,
                        "cost": act.cost,
                    },
                    "score": int(round(score * 100)),
                    "position": position,
                    "reasons": reasons,
                    "selected": activity_id in chosen,
                    "partner_selected": activity_id in partner_chosen,
                    # Kept in the page rather than filtered out of it: the person who pushed a card
                    # away still has to be able to take it back, and a list that hid it would leave
                    # that decision unreversible.
                    "declined": activity_id in declined,
                    "my_meeting_time": _iso(my_time),
                    "partner_meeting_time": _iso(partner_time),
                    "i_accepted_time": _iso(my_accept),
                    "agreed_time": _iso(agreed_instant(
                        (my_time, my_accept), (partner_time, partner_accept)
                    )),
                }
            )
        out.sort(key=lambda r: r["position"])
        return out

    async def _hydrate(
        self,
        stored: list,
        user_id: uuid.UUID,
        partner_id: uuid.UUID,
        match_id: uuid.UUID,
    ) -> list[dict]:
        # The catalogue rows are read once for the whole page: one round trip per card
        # made opening the tab cost eight queries to fetch eight rows of the same table.
        by_id = await self.activities.get_by_ids([rec.activity_id for rec in stored])
        chosen, partner_chosen, declined, times = await self._decisions(
            user_id, partner_id, match_id, [rec.activity_id for rec in stored]
        )
        return self._render(
            [(rec.activity_id, rec.score, rec.position, rec.explanation) for rec in stored],
            by_id,
            chosen,
            partner_chosen,
            declined,
            user_id,
            partner_id,
            times,
        )

    async def mark_selected(self, match_id: uuid.UUID, user_id: uuid.UUID, activity_id: int) -> list[dict]:
        """The card's «выбрать» — an idea put to the pair, which is a plan being made.

        The guards this verb used to carry itself (a url id is a claim about the catalogue rather than
        a fact from it; `activity_preferences.match_id` is a child of the match row that `block` and
        `delete_account` delete under the pair advisory lock) now live in `PlanService`, where the plan
        is written. They were learned the hard way here — an unchecked id reached a foreign key and the
        client saw a 500 — and a second copy of them would be a second door that can forget one.
        """
        return await self.plans.propose_idea(match_id, user_id, activity_id)

    async def set_declined(
        self, match_id: uuid.UUID, user_id: uuid.UUID, activity_id: int, declined: bool
    ) -> list[dict]:
        """Push an idea out of this person's page, or bring it back.

        Delegated for the same reason a proposal is: a refusal by the half that did not make the plan
        is an answer to that plan, so the card and the pair's plan have to be moved by one verb.
        """
        return await self.plans.set_declined(match_id, user_id, activity_id, declined)

    async def propose_time(
        self, match_id: uuid.UUID, user_id: uuid.UUID, activity_id: int, when: datetime
    ) -> list[dict]:
        """Name the moment this person would meet for this idea, or move the one they named.

        The lines this wrote into the conversation come back for the socket, the way a sent message
        does: moving the hour can end the plan the pair was standing on, and a chat that learned of
        it only at the next reload would go on offering a promise nobody holds.
        """
        return await self.plans.offer_hour(match_id, user_id, activity_id, when)

    async def accept_time(
        self, match_id: uuid.UUID, user_id: uuid.UUID, activity_id: int, when: datetime
    ) -> list[dict]:
        """Agree to the moment the other half named.

        The instant arrives from the client rather than being read off the partner's row here, and
        that is the point: it is the value the person saw when they tapped. `PlanService` keeps that
        rule, and the line the pair's chat gets for the hour it makes.
        """
        return await self.plans.confirm_hour(match_id, user_id, activity_id, when)

