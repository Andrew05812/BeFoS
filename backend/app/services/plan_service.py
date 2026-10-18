from __future__ import annotations

"""The pair's plans: one row per arrangement, one writer for every door that changes it.

Until this service existed, "the pair's plan" was a reading rather than a thing. Two
`activity_preferences` rows whose instants happened to line up made a plan, the conversation kept its
own copy of that reading as journal lines, and nothing else in the product could point at an
arrangement — so a list of plans, a reschedule, a cancellation and a completed meeting had no subject
to act on. `SharedPlan` is the subject and this service is the only place that moves it.

What the plan says about the hour is projected from the pair's rows, never negotiated here: the two
rows stay the record of what each half named and what each half agreed to (the contract
`docs/API.md` has carried since stage 81), and `sync_pair` re-reads them so the plan cannot outlive
what the rows say. The verbs below write those rows through the same repository primitives the card
page writes them with, so "arrange an hour from the card" and "arrange an hour from the plan" are one
code path rather than two that have to be kept in agreement.

One fact is the plan's own rather than the rows': *which hour the pair is being asked about*. The
rows say what each half last named and what each half last agreed to, and the moment one of them
moves an evening the pair stood on, they name two different instants — which is also what a pair
talking past each other looks like. The plan knows the difference because it has stood on an hour
before, so `offer_hour` records its own question and `sync_pair` keeps that record only while the row
of the person who asked still names the instant. Everything else about the hour stays a projection.

Journal lines are written on state moves, not on taps, for the reason `docs/DATABASE.md` already
gives: the retry of a request whose response was lost has to leave one line behind rather than two,
and a tap that moved nothing has to leave none.
"""

import uuid
from collections import namedtuple
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.tracker import Event, tracker
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import Activity, Match, SharedPlan, SharedPlanMember
from app.models.base import utcnow
from app.models.chat import (
    KIND_PLAN_ACCEPTED,
    KIND_PLAN_AGREED,
    KIND_PLAN_CANCELLED,
    KIND_PLAN_CHANGED,
    KIND_PLAN_COMPLETED,
    KIND_PLAN_DECLINED,
    KIND_PLAN_PROPOSED,
    KIND_PLAN_RESCHEDULED,
    KIND_PLAN_VOIDED,
)
from app.models.plan import (
    DECISION_DECLINED,
    DECISION_JOINED,
    DECISION_PENDING,
    STATUS_ACCEPTED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_DECLINED,
    STATUS_PLANNED,
    STATUS_PROPOSED,
    STATUS_RESCHEDULED,
)
from app.repositories.activity_repo import ActivityRepository, PreferenceLine
from app.repositories.chat_repo import ChatRepository
from app.repositories.plan_repo import PlanRepository
from app.repositories.social_repo import SocialRepository
from app.repositories.user_repo import UserRepository
from app.services.chat_service import message_dto
from app.services.plan_time import (
    agreed_instant,
    plan_change_sentence,
    plan_sentence,
    unmatched_offer,
    validate_meeting_time,
)

_EMPTY = PreferenceLine(False, False, None, None, None)

# The hour as the plan held it before this tap, and the moment it was being asked about. Read off the
# stored row rather than recomputed, because the journal answers what changed and the pair's chat
# already stands on whatever the last sync left here.
_Hour = namedtuple("_Hour", "agreed pending")


def _refuse_closed(plan: SharedPlan) -> None:
    """A plan the pair has closed is not arranged through the hour doors.

    `cancelled_at` outranks the rows in `_status`, so an hour landed on after a cancellation would put
    «вы договорились» in the chat about a plan the pair's list still shows as off. The way back is the
    plan's own restore, which is the one act that says the pair took the arrangement up again.

    A finished meeting is refused by the same door, and until this was measured it was not: tapping
    «перенести встречу» on a plan both halves had marked as happened answered 204 and rewrote the closed
    record — `starts_at` went from the evening they stood on to nothing, `pending_hour` and
    `pending_by` took the new instant and its author, and `hour_passed` turned false under a status that
    still read `completed`. Two readings of one plan at once, in the same row: the list said the meeting
    took place and the card said a question was waiting for an answer. An agreement that both halves
    have reported as lived through is not something to re-time, and the way to move it is the same one
    the answer doors already demand — first take back the word that it happened, which is a statement
    about the past, then arrange an hour that is still ahead.
    """
    if plan.status == STATUS_CANCELLED:
        raise ConflictError("This plan is called off, so its hour has to be restored first.")
    if plan.status == STATUS_COMPLETED:
        raise ConflictError("This meeting is over, so there is no hour left to arrange.")


def _refuse_answer_closed(plan: SharedPlan) -> None:
    """A plan that is called off or has already happened is not open for an answer.

    The hour doors have `_refuse_closed` and the words of the pair have their own refusal in `edit`;
    the answer doors had neither, so `POST /plans/{id}/accept` answered 204 over a cancelled plan and
    moved that person's row under an arrangement the pair had already called off — the next restore
    would then put the plan back standing on answers one half had given while it was closed.

    `declined` is deliberately absent from what this refuses. A refusal is an answer, and an answer is
    exactly what its author may still take back; a door closed behind it would leave the pair holding
    a plan neither of them can put right again.
    """
    if plan.status in (STATUS_CANCELLED, STATUS_COMPLETED):
        raise ConflictError("This plan is closed, so there is nothing left to answer.")


def _newest_last(frames: list[dict]) -> list[dict]:
    """Mark only the last line of one tap as the conversation's newest word about the idea.

    Each frame is built as the newest thing its line could be, because a single write cannot know
    whether another follows it. A socket that delivered both frames of a move would otherwise show the
    ended hour and the new question as current together, and the pair would read a promise as standing
    in the same screen that says it was taken back.
    """
    for index, frame in enumerate(frames):
        if frame["plan"] is not None:
            frame["plan"]["is_latest"] = index == len(frames) - 1
    return frames


def _decision(line: PreferenceLine) -> str:
    """What this person's row says about the idea, as the pair's plan answers it.

    `joined` when they put it to the pair and still stand behind it, `declined` when they pushed it
    away, `pending` when they have said nothing — and `pending` is a state rather than an absent row,
    because the pair's plan is about two named people and «ждёт подтверждения» has to name which of
    them is being asked.

    The refusal is read first, and that order is the whole of what makes a confirmation revocable.
    The card page keeps both flags standing when somebody who already proposed then pushes the idea
    away, because the sentence did go into the chat and the mark is what stops a second copy of it —
    so a plan answering from `proposed` first was reading a refusal that had been written, committed
    and forgotten by every screen: «подтверждена обоими» over a person who had said they were not
    coming. Taking the refusal back leaves the proposal it came after standing, so the way out of a
    refusal is the same tap that made it and the arrangement does not have to be negotiated again.
    """
    if line.declined:
        return DECISION_DECLINED
    if line.proposed:
        return DECISION_JOINED
    return DECISION_PENDING


def _instants(line: PreferenceLine) -> tuple[datetime | None, datetime | None]:
    return (line.meeting_time, line.accepted_time)


class PlanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.plans = PlanRepository(session)
        self.activities = ActivityRepository(session)
        self.chat = ChatRepository(session)
        self.social = SocialRepository(session)
        self.users = UserRepository(session)

    # ---------- guards ----------

    async def _require_match(self, match_id: uuid.UUID, user_id: uuid.UUID) -> Match:
        match = await self.session.get(Match, match_id)
        # The same refusal every route of this pair family gives: a 403 would say "this pair exists,
        # you are just not in it", which is the oracle stage 26 exists to keep closed.
        if match is None or not (match.user_a_id == user_id or match.user_b_id == user_id):
            raise NotFoundError("Match not found.")
        return match

    async def _require_plan(self, plan_id: uuid.UUID, user_id: uuid.UUID) -> tuple[Match, SharedPlan]:
        """The plan and its pair, or nothing — for a caller who names a plan by its id.

        The id arrives from the url, so it is a claim about somebody's plans rather than a fact about
        this viewer's. Membership is read off the pair the plan belongs to, and the refusal is the
        same 404 a plan that does not exist gets: an outsider told "not yours" has learned that the
        arrangement is real.
        """
        plan = await self.plans.get(plan_id)
        if plan is None:
            raise NotFoundError("Plan not found.")
        return await self._require_match(plan.match_id, user_id), plan

    async def _lock_pair(self, match: Match, match_id: uuid.UUID) -> None:
        """Serialise this write against a dissolve, the way every other write into a pair does.

        `shared_plans` is a child of `matches`, and so are the preference rows its projection reads.
        A `block` (stage 9) or a `delete_account` (stage 13) that commits its DELETE between this
        transaction's first read and its INSERT raises a foreign-key violation — an HTTP 500 to a
        person who only tapped a card. The re-check under the lock reads the database rather than the
        session's identity map, which still holds the match this connection loaded moments ago.
        """
        await self.social.lock_pair(match.user_a_id, match.user_b_id)
        if not await self.social.match_still_present(match_id):
            raise NotFoundError("Match not found.")

    @staticmethod
    def _partner_id(match: Match, user_id: uuid.UUID) -> uuid.UUID:
        return match.user_b_id if match.user_a_id == user_id else match.user_a_id

    @staticmethod
    def _member(plan: SharedPlan, user_id: uuid.UUID) -> SharedPlanMember | None:
        return next((m for m in plan.members if m.user_id == user_id), None)

    @staticmethod
    def _other_member(plan: SharedPlan, user_id: uuid.UUID) -> SharedPlanMember | None:
        return next((m for m in plan.members if m.user_id != user_id), None)

    # ---------- projection ----------

    @staticmethod
    def _status(plan: SharedPlan) -> str:
        """What the plan is, read off what the pair has said. Kept as one ordered rule.

        Ordered rather than spread across the verbs, because the verbs move different facts and the
        pair has to be shown one state for their plan: a cancellation outranks an hour that still
        sits in the rows, and an answer one half has changed outranks the hour it came after.

        The refusal of the half that did not make the plan therefore reads before `starts_at`. It did
        not used to, and could not: `_decision` answered `joined` for anybody whose row carried the
        proposal mark, so a refusal given after a confirmation never reached the pair's state at all,
        and the hour standing on the plan was always the newer of the two facts. «Не приду», said
        after «в семь», is now the pair's state — whatever the hour column still holds, and the hour
        it holds is what a taken-back refusal returns to.
        """
        if plan.cancelled_at is not None:
            return STATUS_CANCELLED
        if plan.members and all(m.attended_at is not None for m in plan.members):
            return STATUS_COMPLETED
        if any(
            member.user_id != plan.created_by and member.decision == DECISION_DECLINED
            for member in plan.members
        ):
            # A refusal from the half that did not make the plan is an answer to it. The creator
            # pushing their own idea away is a person editing their own page, which says nothing
            # about the pair and leaves the plan proposed.
            return STATUS_DECLINED
        if plan.starts_at is not None:
            return STATUS_PLANNED
        if plan.pending_hour is not None and plan.was_planned:
            return STATUS_RESCHEDULED
        if plan.members and all(m.decision == DECISION_JOINED for m in plan.members):
            return STATUS_ACCEPTED
        return STATUS_PROPOSED

    async def sync_pair(self, match: Match) -> list[SharedPlan]:
        """Bring the pair's plans up to date with what the pair's rows say, and return them.

        One statement over `activity_preferences` for the whole pair, so a plan list across several
        pairs pays one read per pair rather than two per plan. The projection writes only the fields
        the rows answer — the hour, the hour being asked about, the decisions, the status and the
        idea's current name — and never touches `note`, `place`, `attended_at` or `cancelled_at`,
        which are the plan's own record of what the pair said about the arrangement rather than about
        the idea.

        A plan is *created* for an idea one of the two has put to the pair. A row that only pushed a
        card away is a person editing their own page and names no arrangement, so the page of plans
        stays a list of ideas the pair took up rather than a list of things one of them did not want.

        It never writes a journal line either. Lines belong to the verbs that moved the state, so a
        plan discovered here — an idea the pair arranged before this table existed — cannot be
        re-announced to their chat every time one of them opens a screen.
        """
        rows = await self.activities.pair_decisions(match.id)
        plans = {plan.activity_id: plan for plan in await self.plans.list_for_match(match.id)}
        taken_up = {
            activity_id
            for activity_id, lines in rows.items()
            if any(line.proposed for line in lines.values())
        }
        # An idea that has left the catalogue gets no plan: `shared_plans.activity_id` is CASCADE, so
        # the arrangement of a card that goes leaves with it, while the conversation keeps its own
        # lines — `messages.plan_activity_id` is SET NULL — so what the pair was said is not rewritten
        # by what the catalogue did afterwards. The read is asked for the ids rather than assumed to
        # hold them because the pair's rows and this table are written in different statements.
        catalogue = await self.activities.get_by_ids(sorted(taken_up))

        for activity_id in sorted(taken_up):
            lines = rows[activity_id]
            plan = plans.get(activity_id)
            if plan is None:
                activity = catalogue.get(activity_id)
                if activity is None:
                    continue
                plan = await self._create_plan(match, activity, lines)
                plans[activity_id] = plan
            else:
                activity = catalogue.get(activity_id)
                if activity is not None and plan.title != activity.title:
                    plan.title = activity.title

            agreed = agreed_instant(
                _instants(lines.get(match.user_a_id, _EMPTY)),
                _instants(lines.get(match.user_b_id, _EMPTY)),
            )
            plan.starts_at = agreed
            if agreed is not None:
                plan.was_planned = True
                plan.pending_hour = None
                plan.pending_by = None
            else:
                plan.pending_hour, plan.pending_by = self._ask_of(plan, lines)
            for user_id, line in lines.items():
                member = self._member(plan, user_id)
                if member is not None:
                    member.decision = _decision(line)
            plan.status = self._status(plan)

        await self.session.flush()
        return sorted(plans.values(), key=lambda p: p.created_at, reverse=True)

    @staticmethod
    def _ask_of(
        plan: SharedPlan, lines: dict[uuid.UUID, PreferenceLine]
    ) -> tuple[datetime | None, uuid.UUID | None]:
        """Which hour the pair is being asked about, and who is asking.

        The plan's own record holds the question while the row of the person who asked it still names
        that instant — and nothing else. The rows are read for that, not trusted blindly: a half who
        has since moved their own offer has withdrawn the question with the same tap, and a stored ask
        nobody still stands behind would keep the other half's card asking a question that was never
        asked.

        Where there is no live record, the rows answer on their own — see `unmatched_offer`, which
        finds the single hour one half has named and the other has not confirmed. That reading is what
        a first offer is, and it is enough while nobody has moved a shared hour; the moment one half
        moves the hour the pair stood on, the two rows hold two different instants and the difference
        between a pair talking past each other and a pair one answer from a new evening is not in the
        rows any more. It is in `_record_ask`.
        """
        author = plan.pending_by
        if plan.pending_hour is not None and author is not None:
            line = lines.get(author)
            if line is not None and line.meeting_time == plan.pending_hour:
                return plan.pending_hour, author
        return unmatched_offer({user_id: _instants(line) for user_id, line in lines.items()})

    @classmethod
    def _record_ask(cls, plan: SharedPlan, actor_id: uuid.UUID, when: datetime) -> None:
        """Say on the plan itself which hour this tap is asking the other half about.

        Called after the projection, by the one verb that names an hour, and it changes nothing when
        the pair has landed on a moment (the agreement is the answer to the question) or when the plan
        already asks about this one.

        The rows cannot carry this. Two halves naming two different instants is either a pair that has
        not settled on an evening yet or a pair that stood on one and has just had it moved by the half
        who had only agreed to it — and the second reading is a reschedule, whose question has to reach
        the other half's card or the tap lands nowhere. What tells them apart is that the plan has
        stood on an hour before, which is the plan's own history rather than a fact about the rows.
        """
        if plan.starts_at is not None or plan.pending_hour == when:
            return
        plan.pending_hour = when
        plan.pending_by = actor_id
        plan.status = cls._status(plan)

    async def _create_plan(
        self,
        match: Match,
        activity: Activity,
        lines: dict[uuid.UUID, PreferenceLine],
    ) -> SharedPlan:
        """The plan of an idea the pair has taken up, named by whoever took it up first.

        `created_by` is read off the rows rather than taken from the caller: the caller of a read is
        whoever opened the screen, and a plan they never proposed would then be reported as theirs —
        including in the rule that only the person who made a plan may take it back.
        """
        proposals = sorted(
            (line.created_at, str(user_id), user_id)
            for user_id, line in lines.items()
            if line.proposed and line.created_at is not None
        )
        created_by = proposals[0][2]
        # The two answer rows are built through the relationship rather than inserted beside it: the
        # projection reads `plan.members` in the same statement that creates the plan, and a
        # collection the session never populated is loaded on access — which an async session
        # refuses.
        plan = SharedPlan(
            match_id=match.id,
            activity_id=activity.id,
            created_by=created_by,
            title=activity.title,
            members=[SharedPlanMember(user_id=user_id) for user_id in (match.user_a_id, match.user_b_id)],
        )
        self.session.add(plan)
        await self.session.flush()
        return plan

    # ---------- reads ----------

    async def _dto_many(self, plans: list[SharedPlan], viewer_id: uuid.UUID) -> list[dict]:
        """Plan rows as the API answers them, with the partner named once for the page."""
        if not plans:
            return []
        matches = await self.plans.matches_for(plans)
        peer_ids = [match.other_user(viewer_id) for match in matches.values()]
        profiles = {p.user_id: p for p in await self.users.get_profile_cards(peer_ids)}
        photos = await self.users.get_primary_photos(peer_ids)
        catalogue = await self.activities.get_by_ids([plan.activity_id for plan in plans])
        return [
            self._dto(plan, matches[plan.match_id], viewer_id, profiles, photos, catalogue)
            for plan in plans
            if plan.match_id in matches
        ]

    def _dto(
        self,
        plan: SharedPlan,
        match: Match,
        viewer_id: uuid.UUID,
        profiles: dict,
        photos: dict,
        catalogue: dict[int, Activity],
    ) -> dict:
        mine = self._member(plan, viewer_id)
        theirs = self._other_member(plan, viewer_id)
        activity = catalogue.get(plan.activity_id)
        peer = None if theirs is None else theirs.user_id
        profile = profiles.get(peer) if peer is not None else None
        # Who is being asked, said as one answer rather than as three fields the client would have to
        # combine: the buckets of «Наши планы» divide on exactly this question, and a screen that
        # re-derived it would be a second implementation of the state machine above.
        #
        # The question is asked of the person whose own word is missing. Reading it as «the partner
        # has not answered» made the card of the person who had not answered say that somebody else
        # was being asked — so the half whose confirmation the plan is waiting for was told, by both
        # screens, that nothing was waiting for them, and a pair could only find out who had not
        # spoken by comparing two cards. What the other half still owes the plan is in
        # `partner_decision`, which says it directly.
        my_answer = mine.decision if mine is not None else DECISION_PENDING
        hour_for_me_to_confirm = (
            plan.pending_hour is not None and (plan.pending_by is None or plan.pending_by != viewer_id)
        )
        return {
            "id": str(plan.id),
            "match_id": str(plan.match_id),
            "activity_id": plan.activity_id,
            "activity_slug": activity.slug if activity else None,
            "activity_category": activity.category if activity else None,
            "title": plan.title,
            "description": activity.description if activity else None,
            "note": plan.note,
            "place": plan.place,
            "status": plan.status,
            "starts_at": plan.starts_at,
            "pending_hour": plan.pending_hour,
            "pending_by": None if plan.pending_by is None else str(plan.pending_by),
            "created_by": str(plan.created_by),
            "cancelled_at": plan.cancelled_at,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
            "my_decision": my_answer,
            "i_attended": mine.attended_at is not None if mine else False,
            "partner_id": None if peer is None else str(peer),
            "partner_name": None if profile is None else profile.name,
            "partner_photo_url": None if peer is None else photos.get(peer),
            "partner_decision": theirs.decision if theirs else DECISION_PENDING,
            "partner_attended": theirs.attended_at is not None if theirs else False,
            # The hour has come and gone and neither of them has said the meeting happened. Not a
            # fact the plan stores: `completed` belongs to the two of them, and a card that called a
            # passed hour a kept one would report a meeting the product has no record of.
            "hour_passed": plan.starts_at is not None and plan.starts_at < utcnow(),
            "needs_my_answer": plan.status
            in (STATUS_PROPOSED, STATUS_RESCHEDULED, STATUS_PLANNED, STATUS_ACCEPTED)
            and (my_answer == DECISION_PENDING or hour_for_me_to_confirm),
            "can_cancel": plan.status not in (STATUS_CANCELLED, STATUS_COMPLETED, STATUS_DECLINED),
        }

    async def list_for_match(self, match_id: uuid.UUID, user_id: uuid.UUID) -> list[dict]:
        match = await self._require_match(match_id, user_id)
        return await self._dto_many(await self.sync_pair(match), user_id)

    async def list_for_viewer(self, user_id: uuid.UUID) -> list[dict]:
        """Every plan of every pair this person is in — the «Наши планы» screen.

        Synced pair by pair: the projection reads the rows, so a list that skipped it would report
        the hours the pair stood on as the rows said them at the last write and would go on offering
        an agreement one of them has since moved.
        """
        plans: list[SharedPlan] = []
        for match in await self.social.list_matches_for_user(user_id):
            plans.extend(await self.sync_pair(match))
        dto = await self._dto_many(plans, user_id)
        dto.sort(key=lambda item: item["created_at"], reverse=True)
        return dto

    async def detail(self, plan_id: uuid.UUID, user_id: uuid.UUID) -> dict:
        match, plan = await self._require_plan(plan_id, user_id)
        synced = await self.sync_pair(match)
        plan = next(p for p in synced if p.id == plan_id)
        items = await self._dto_many([plan], user_id)
        events = await self.plans.events(plan_id)
        titles = await self.activities.get_by_ids(
            sorted({line.plan_activity_id for line in events if line.plan_activity_id})
        )
        mine = self._member(plan, user_id)
        return {
            "plan": items[0],
            # This person's own remark about their own plan, and only ever in their own read:
            # `personal_note` is not part of the shared fields above for exactly that reason.
            "my_note": mine.personal_note if mine else None,
            "events": [
                message_dto(
                    line,
                    user_id,
                    is_read=True,
                    activity=titles.get(line.plan_activity_id),
                    is_latest=index == len(events) - 1,
                )
                for index, line in enumerate(events)
            ],
        }

    # ---------- the journal ----------

    async def _journal(
        self,
        match: Match,
        plan: SharedPlan,
        actor_id: uuid.UUID,
        kind: str,
        when: datetime | None,
        body: str | None = None,
    ) -> dict:
        """Say in the pair's chat what this tap did to their plan, as itself, and hand back the frame.

        The line is written in the caller's transaction, so a plan that did not land leaves no line
        behind, and a line that landed describes an hour the database holds. `sender_id` names the
        person whose tap produced it and is not the author of the sentence — which is why `kind`
        exists, and why a client must read it rather than group this by author.

        `body` replaces the sentence the kind is born with, and only a caller that knows more than the
        kind does passes one: `edit` has just diffed the pair's own words and can say which field moved
        from what to what, which is what the plan's history is asked to answer.
        """
        activity = (await self.activities.get_by_ids([plan.activity_id])).get(plan.activity_id)
        msg = await self.chat.add_plan_event(
            match.id,
            actor_id,
            kind=kind,
            activity_id=plan.activity_id,
            when=when,
            body=body or plan_sentence(kind, plan.title, when),
            plan_id=plan.id,
        )
        return message_dto(msg, actor_id, is_read=False, activity=activity, is_latest=True)

    # ---------- verbs ----------

    async def propose_idea(
        self, match_id: uuid.UUID, user_id: uuid.UUID, activity_id: int
    ) -> list[dict]:
        """Put an idea to the pair, or join one the other half already put — and say which happened.

        The card's «выбрать» and the plan's «подтвердить» are this one verb, because to the pair they
        are the same act: the idea is now one this person stands behind. The row write is the
        repository's `set_preference`, the same primitive the card page uses, so a tap from either
        door leaves the pair's rows in the same shape.

        The line this writes is the reason the idea is in the conversation at all: a proposal the pair
        reads as a card rather than as a sentence somebody typed carries the plan's own id, so the tap
        that opens the arrangement's details is there from the first moment of it.

        A plan the pair has called off or already lived through is not open for this tap. Standing
        behind an idea is an answer, and an answer written while the plan was closed would come back as
        one of the pair's two words the moment the plan was restored — a confirmation nobody was
        waiting for at the time they gave it.
        """
        match = await self._require_match(match_id, user_id)
        known = await self.activities.get_by_ids([activity_id])
        if activity_id not in known:
            raise NotFoundError("Activity not found.")
        await self._lock_pair(match, match_id)
        before = await self.plans.for_pair(match_id, activity_id)
        if before is not None:
            _refuse_answer_closed(before)
        before_status = None if before is None else before.status

        await self.activities.set_preference(user_id, activity_id, 1.0, match_id)
        after = {p.activity_id: p for p in await self.sync_pair(match)}[activity_id]
        frames: list[dict] = []
        if before_status is None:
            frames.append(await self._journal(match, after, user_id, KIND_PLAN_PROPOSED, None))
        elif after.status == STATUS_ACCEPTED and before_status != STATUS_ACCEPTED:
            # The pair now both stands behind the idea — reached whether the second half joined at
            # once or took a refusal back, because to the conversation those are the same news.
            frames.append(await self._journal(match, after, user_id, KIND_PLAN_ACCEPTED, None))
        await self.session.commit()
        tracker.track(
            Event.RECOMMENDATION_SELECTED, str(user_id), match=str(match_id), activity=activity_id
        )
        return _newest_last(frames)

    async def set_declined(
        self, match_id: uuid.UUID, user_id: uuid.UUID, activity_id: int, declined: bool
    ) -> list[dict]:
        """Push an idea out of this person's page, or bring it back, and say what the pair now has.

        A refusal by the half that did not make the plan is an answer to it, and the plan is then
        `declined` — which is why this goes through the plan rather than staying a private edit of a
        list. A refusal by the creator says nothing about the pair, and no line is written for it.

        The two directions of this tap are not equally closed by a plan the pair no longer holds.
        Pushing the card away stays possible over any plan: it is this person's own page, and a door
        locked there would leave an idea they cannot move. Bringing it back is refused over a called-off
        or lived-through plan, because that answer joins the pair's two words as soon as the plan comes
        back — and the plan would return standing on a confirmation that was given while nobody was
        asking.
        """
        match = await self._require_match(match_id, user_id)
        known = await self.activities.get_by_ids([activity_id])
        if activity_id not in known:
            raise NotFoundError("Activity not found.")
        await self._lock_pair(match, match_id)
        before = await self.plans.for_pair(match_id, activity_id)
        if before is not None and not declined:
            _refuse_answer_closed(before)
        before_status = None if before is None else before.status

        await self.activities.set_declined(user_id, activity_id, match_id, declined)
        after = {p.activity_id: p for p in await self.sync_pair(match)}.get(activity_id)
        frames: list[dict] = []
        if after is not None and before_status is not None:
            if declined and after.status == STATUS_DECLINED and before_status != STATUS_DECLINED:
                frames.append(await self._journal(match, after, user_id, KIND_PLAN_DECLINED, None))
            elif not declined and before_status == STATUS_DECLINED:
                # A plan that came back is a plan the pair has to see again, and the honest kind for
                # that is the one that says the card changed — the idea was never newly proposed.
                frames.append(await self._journal(match, after, user_id, KIND_PLAN_CHANGED, None))
                if after.status == STATUS_ACCEPTED:
                    frames.append(
                        await self._journal(match, after, user_id, KIND_PLAN_ACCEPTED, None)
                    )
        await self.session.commit()
        return _newest_last(frames)

    async def offer_hour(
        self, match_id: uuid.UUID, user_id: uuid.UUID, activity_id: int, when: datetime
    ) -> list[dict]:
        """Name the moment this person would meet for this idea, or move the one they named.

        The rules the card page has always applied, because the same page shows the answer: the idea
        has to have gone into this pair's chat first, the instant has to be one they can meet at, and
        the chat hears about the agreement this tap ended or made. What it does not hear about is the
        offer itself while the pair has never stood on an hour — that is a question the other half
        answers on the card, and a line per offer would fill the conversation with hours that were
        never agreed on. Once the pair has stood on one, moving it is said as a question too: the chat
        that kept the old moment as its newest word would otherwise report a plan nobody is waiting for.

        This is the door both halves walk through, and it used to be open for only one of them. The
        half who named the evening could move it; the half who had agreed to it could not — their tap
        wrote a new instant into their own row and left their standing acceptance beside it, so the
        projection kept reading the old pair as a promise, the plan went on reporting the hour it had
        been asked to leave, and the chat said nothing about the tap at all. Naming a different moment
        now withdraws that acceptance where it is written (`set_meeting_time`) and asks the other half
        about the new one where the question belongs (`_record_ask`), which is the same pair of moves
        the naming half always had.
        """
        match = await self._require_match(match_id, user_id)
        validate_meeting_time(when)
        known = await self.activities.get_by_ids([activity_id])
        activity = known.get(activity_id)
        if activity is None:
            raise NotFoundError("Activity not found.")
        await self._lock_pair(match, match_id)
        plan = await self.plans.for_pair(match_id, activity_id)
        if plan is None:
            raise ConflictError("Send this idea to the chat before arranging a time for it.")
        _refuse_closed(plan)
        proposed, _declined, _times = await self.activities.decisions_by_pair(match_id, [activity_id])
        if activity_id not in proposed.get(user_id, set()):
            raise ConflictError("Send this idea to the chat before arranging a time for it.")
        before = _Hour(plan.starts_at, plan.pending_hour)

        await self.activities.set_meeting_time(user_id, activity_id, match_id, when)
        after = {p.activity_id: p for p in await self.sync_pair(match)}[activity_id]
        self._record_ask(after, user_id, when)
        frames = await self._hour_lines(match, after, user_id, before)
        await self.session.commit()
        return _newest_last(frames)

    async def confirm_hour(
        self, match_id: uuid.UUID, user_id: uuid.UUID, activity_id: int, when: datetime
    ) -> list[dict]:
        """Agree to the moment the other half named.

        The instant arrives from the client rather than being read off the partner's row here, and
        that is the point: it is the value the person saw when they tapped. If the partner has moved
        it in the meantime the answer is a conflict, not a silent agreement to something nobody
        offered — the same reason the chat refuses a message built on a pair that dissolved.
        """
        match = await self._require_match(match_id, user_id)
        validate_meeting_time(when)
        known = await self.activities.get_by_ids([activity_id])
        if activity_id not in known:
            raise NotFoundError("Activity not found.")
        await self._lock_pair(match, match_id)
        _proposed, _declined, times = await self.activities.decisions_by_pair(match_id, [activity_id])
        partner_time = times.get(self._partner_id(match, user_id), {}).get(activity_id, (None, None))[0]
        if partner_time is None:
            raise ConflictError("The other half has not named a time for this idea yet.")
        if partner_time != when:
            raise ConflictError("That time is no longer the one being offered.")
        plan = await self.plans.for_pair(match_id, activity_id)
        if plan is None:
            raise ConflictError("Send this idea to the chat before arranging a time for it.")
        _refuse_closed(plan)
        before = _Hour(plan.starts_at, plan.pending_hour)

        await self.activities.set_accepted_time(user_id, activity_id, match_id, when)
        after = {p.activity_id: p for p in await self.sync_pair(match)}[activity_id]
        frames = await self._hour_lines(match, after, user_id, before)
        await self.session.commit()
        return _newest_last(frames)

    async def _hour_lines(
        self, match: Match, plan: SharedPlan, actor_id: uuid.UUID, before: _Hour
    ) -> list[dict]:
        """What this tap did to the hour, if anything — the journal is a diff, not a tap counter.

        Three answers, and which of them is right is decided by what changed rather than by which verb
        ran: an agreement the pair no longer stands on is ended, an agreement they now stand on is said,
        and a moment they are being asked about is named as a question. A tap that left all three as
        they were — the retry of an accept whose response was lost, an offer that trades one unanswered
        hour for another while the agreed one still stands — writes nothing, which is what keeps a
        repeated request from saying the same promise twice.

        A move that both ends an hour and asks for a new one writes two lines, the end first. Folding
        them into one sentence would leave the moment the pair no longer holds unsaid, and a chat that
        showed only the new question would show the promise as still standing.
        """
        frames: list[dict] = []
        if before.agreed is not None and before.agreed != plan.starts_at:
            frames.append(await self._journal(match, plan, actor_id, KIND_PLAN_VOIDED, before.agreed))
        if plan.starts_at is not None and plan.starts_at != before.agreed:
            frames.append(await self._journal(match, plan, actor_id, KIND_PLAN_AGREED, plan.starts_at))
        elif (
            plan.starts_at is None
            and plan.status == STATUS_RESCHEDULED
            and plan.pending_by == actor_id
            and plan.pending_hour is not None
            and plan.pending_hour != before.pending
        ):
            frames.append(
                await self._journal(match, plan, actor_id, KIND_PLAN_RESCHEDULED, plan.pending_hour)
            )
        return frames

    # ---------- the same verbs, named by plan id ----------

    async def match_of(self, plan_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID:
        """The pair whose open chats a write to this plan has to be told about.

        Membership is proven here rather than assumed from the url: the route that broadcasts is
        naming a pair from a plan id a client sent, and an outsider told nothing is the answer an
        outsider gets everywhere else in this family.
        """
        _, plan = await self._require_plan(plan_id, user_id)
        return plan.match_id

    async def _pair_of(self, plan_id: uuid.UUID, user_id: uuid.UUID) -> tuple[uuid.UUID, int]:
        """The pair and the idea behind a plan the caller names by its id.

        The card page and the plan screen are two doors onto one arrangement, so the second door
        calls the verb the first one already has rather than carrying a second implementation of it.
        The pair and the idea are read off the plan's own row, never taken from the request: a body
        that named a `match_id` alongside a `plan_id` would be asking this route to believe a claim
        about somebody else's pair.
        """
        _, plan = await self._require_plan(plan_id, user_id)
        return plan.match_id, plan.activity_id

    async def accept_by_id(self, plan_id: uuid.UUID, user_id: uuid.UUID) -> list[dict]:
        """Stand behind the idea the plan is about — the plan screen's word for the card's «выбрать»."""
        match_id, activity_id = await self._pair_of(plan_id, user_id)
        return await self.propose_idea(match_id, user_id, activity_id)

    async def decline_by_id(self, plan_id: uuid.UUID, user_id: uuid.UUID, declined: bool) -> list[dict]:
        match_id, activity_id = await self._pair_of(plan_id, user_id)
        return await self.set_declined(match_id, user_id, activity_id, declined)

    async def offer_by_id(self, plan_id: uuid.UUID, user_id: uuid.UUID, when: datetime) -> list[dict]:
        match_id, activity_id = await self._pair_of(plan_id, user_id)
        return await self.offer_hour(match_id, user_id, activity_id, when)

    async def confirm_by_id(self, plan_id: uuid.UUID, user_id: uuid.UUID, when: datetime) -> list[dict]:
        match_id, activity_id = await self._pair_of(plan_id, user_id)
        return await self.confirm_hour(match_id, user_id, activity_id, when)

    async def edit(
        self,
        plan_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        place: str | None = None,
        note: str | None = None,
        my_note: str | None = None,
        clear_place: bool = False,
        clear_note: bool = False,
    ) -> list[dict]:
        """Change what the pair wrote about the arrangement: its place, its own note.

        Only those two fields, and only here. The hour is not edited by this verb because it is not
        this person's to edit — an hour the pair stands on is the other half's answer as much as
        their own, so moving it goes through `offer_hour` and waits for that answer. A plan whose
        meeting is over or called off has nothing left to arrange, and saying so is the refusal.

        Unknown fields stay absent rather than filled: a plan with no place written is the truth, and
        writing one to make a card look complete would put an address in somebody's evening that no
        conversation named.
        """
        match, plan = await self._require_plan(plan_id, user_id)
        if plan.status in (STATUS_CANCELLED, STATUS_COMPLETED, STATUS_DECLINED):
            raise ConflictError("This plan is closed, so there is nothing left to change.")
        await self._lock_pair(match, plan.match_id)
        if place is not None and not place.strip():
            raise ValidationError("A place has to be a place, or it should be left unwritten.")
        if note is not None and len(note) > 500:
            raise ValidationError("A note to the pair is at most 500 characters.")

        before = (plan.place, plan.note)
        if place is not None or clear_place:
            plan.place = None if clear_place else place.strip()
        if note is not None or clear_note:
            plan.note = None if clear_note else (note.strip() or None)
        if my_note is not None:
            await self._set_personal_note(plan, user_id, my_note)
        frames: list[dict] = []
        if (plan.place, plan.note) != before:
            # The pair's chat holds a card about this plan, and the older word on it must not be left
            # reading as current: what changed is said as its own line rather than by editing a
            # message the other half may already have read. The line names both edges of each field
            # that moved, because the history of the plan is the reader that asks what it *was* — the
            # plan's own fields already answer what it is.
            changes = [
                (field, was, now)
                for field, was, now in (("place", before[0], plan.place), ("note", before[1], plan.note))
                if was != now
            ]
            frames.append(
                await self._journal(
                    match,
                    plan,
                    user_id,
                    KIND_PLAN_CHANGED,
                    plan.starts_at,
                    body=plan_change_sentence(plan.title, plan.starts_at, changes),
                )
            )
        await self.session.commit()
        return _newest_last(frames)

    async def cancel(self, plan_id: uuid.UUID, user_id: uuid.UUID) -> list[dict]:
        """Call the plan off, and end the hour the pair was standing on in their chat.

        Either half may do it: a plan is a promise two people made, and either of them is allowed to
        take it back. What neither may do is leave the other reading a live card, which is why the
        line carries the moment when one stood — the chat that said «договорились» has to become the
        chat that says it is off, and say it about the same hour.
        """
        match, plan = await self._require_plan(plan_id, user_id)
        if plan.cancelled_at is not None:
            return []  # already called off: the retry of a lost response says it once, not twice
        if plan.status == STATUS_COMPLETED:
            raise ConflictError("A meeting that is over is not a plan to cancel.")
        await self._lock_pair(match, plan.match_id)
        ended = plan.starts_at
        plan.cancelled_at = utcnow()
        plan.cancelled_by = user_id
        plan.status = self._status(plan)
        # One line rather than two. The moment the pair stood on is named inside it: a chat that said
        # «договорённость отменена» and then «план отменён» about one tap would report the same end
        # twice, in two sentences that differ only in how much of the plan they name.
        frames = [await self._journal(match, plan, user_id, KIND_PLAN_CANCELLED, ended)]
        await self.session.commit()
        return _newest_last(frames)

    async def restore(self, plan_id: uuid.UUID, user_id: uuid.UUID) -> list[dict]:
        """Take a cancellation back — by the half that called it off, and by nobody else.

        The other person's tap would reopen an arrangement the first one just ended and leave them
        answering a question they did not ask, so the act belongs to whoever wrote `cancelled_by`.
        The hour the pair stood on is still in their rows, so it comes back with the plan rather than
        having to be negotiated again.
        """
        match, plan = await self._require_plan(plan_id, user_id)
        if plan.cancelled_at is None:
            return []
        if plan.cancelled_by != user_id:
            raise ConflictError("Only the person who called this plan off can take it back.")
        await self._lock_pair(match, plan.match_id)
        plan.cancelled_at = None
        plan.cancelled_by = None
        after = {p.activity_id: p for p in await self.sync_pair(match)}[plan.activity_id]
        # One line, in whichever kind says what the pair now has: an hour they stand on again is
        # reported as the agreement it is, and an idea taken up without one is simply back.
        frames = [
            await self._journal(
                match,
                after,
                user_id,
                KIND_PLAN_AGREED if after.starts_at is not None else KIND_PLAN_CHANGED,
                after.starts_at,
            )
        ]
        await self.session.commit()
        return _newest_last(frames)

    async def set_attended(self, plan_id: uuid.UUID, user_id: uuid.UUID, attended: bool) -> list[dict]:
        """This person's own word that the meeting happened — or that they spoke too soon.

        Not automatic, and not derivable from the clock: an hour passing is not evidence about the
        physical world, and a plan that read «состоялось» because a timestamp went by would put a
        meeting into the record that nobody confirmed. The plan is `completed` only when both halves
        have said it, which is also why the answer lives on the member row rather than on the plan.
        """
        match, plan = await self._require_plan(plan_id, user_id)
        if plan.status == STATUS_CANCELLED:
            raise ConflictError("A plan called off is not a meeting to mark as done.")
        if plan.status == STATUS_DECLINED:
            raise ConflictError("This idea was declined, so there was nothing to attend.")
        if plan.starts_at is None:
            raise ConflictError("There is no hour for this plan, so there is nothing to confirm.")
        member = self._member(plan, user_id)
        if member is None:
            raise NotFoundError("Plan not found.")
        if attended:
            if plan.starts_at > utcnow():
                raise ConflictError("The hour has not come yet.")
            if member.attended_at is not None:
                return []
            member.attended_at = utcnow()
        elif member.attended_at is None:
            return []
        else:
            member.attended_at = None

        was_completed = plan.status == STATUS_COMPLETED
        after = {p.activity_id: p for p in await self.sync_pair(match)}[plan.activity_id]
        frames: list[dict] = []
        if attended and not was_completed and after.status == STATUS_COMPLETED:
            frames.append(
                await self._journal(match, after, user_id, KIND_PLAN_COMPLETED, after.starts_at)
            )
        elif not attended and was_completed and after.status != STATUS_COMPLETED:
            # Taking the word back is said as a change rather than as a voided hour: the pair still
            # stands on the moment they arranged, they have simply stopped claiming it happened.
            frames.append(
                await self._journal(match, after, user_id, KIND_PLAN_CHANGED, after.starts_at)
            )
        await self.session.commit()
        return _newest_last(frames)

    async def set_personal_note(
        self, plan_id: uuid.UUID, user_id: uuid.UUID, note: str | None
    ) -> None:
        """This person's own remark about their own plan, read back only to them."""
        _, plan = await self._require_plan(plan_id, user_id)
        await self._set_personal_note(plan, user_id, note)
        await self.session.commit()

    async def _set_personal_note(
        self, plan: SharedPlan, user_id: uuid.UUID, note: str | None
    ) -> None:
        """The write behind both doors that take a personal note.

        A safe storage model is what makes this field exist at all: it lives on the member row rather
        than on the plan, so the pair's shared card cannot carry it, and the only read that returns it
        is its author's own `detail`. Nothing about the other half is written here, and nothing of
        theirs is read here.
        """
        if note is not None and len(note) > 500:
            raise ValidationError("A personal note is at most 500 characters.")
        member = self._member(plan, user_id)
        if member is None:
            raise NotFoundError("Plan not found.")
        member.personal_note = None if note is None else (note.strip() or None)
