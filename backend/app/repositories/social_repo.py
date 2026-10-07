from __future__ import annotations

import calendar
import uuid
from datetime import date

from sqlalchemy import and_, or_, select, func, delete, update, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Block, DiscoveryQueue, Like, Match, Pass, Report, User, Profile
from app.models.base import utcnow, utc_today
from app.models.discovery import READY, SEEN


def ordered_pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Return the pair sorted so matches are direction-independent & unique."""
    return (a, b) if str(a) <= str(b) else (b, a)


def shift_years(today: date, years: int) -> date:
    """The calendar date ``years`` before ``today``, keeping month and day when they exist.

    ``date(today.year - years, today.month, today.day)`` is a crash waiting for Feb 29:
    subtracting years lands on a February that has only 28 days, and the constructor raises
    ``ValueError`` out of the discovery query that backs the app's main screen. The day is
    clamped to the last real day of the target month, so a leap-day viewer still gets a deck.
    """
    year = today.year - years
    return date(year, today.month, min(today.day, calendar.monthrange(year, today.month)[1]))


class SocialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Likes / Passes ---
    # Every "has it already?" check below is advisory: two requests for the same gesture
    # (a double tap, a retry after a dropped connection) can both pass it and then both
    # try to insert. The writes therefore go through ON CONFLICT DO NOTHING against the
    # same unique constraint the schema already enforces, so the second one is a no-op
    # instead of an IntegrityError that surfaces to the user as a failed action.
    async def lock_pair(self, a: uuid.UUID, b: uuid.UUID) -> None:
        """Serialize the like that could form this pair for the life of the transaction.

        ``like()`` reads-then-writes: it checks for a mutual like and only then creates the
        match. Two people liking each other at the same instant is the one schedule that
        breaks that — each transaction inserts its own like and then asks whether the other
        liked back, and under READ COMMITTED neither sees the other's still-uncommitted row.
        Both answer "not mutual", no match is made, and the two likes sit in the table
        belonging to nobody. Nothing re-runs the check: liking removes each person from the
        other's deck, so the match is lost silently and for good.

        A transaction-scoped advisory lock keyed on the unordered pair makes the two likes
        take turns. The second one starts its read only after the first has committed, so it
        sees the first's like and forms the pair — once, since the first already answered no.
        The lock is released by the same COMMIT that ends the request, and a different pair
        never waits on it.
        """
        ua, ub = ordered_pair(a, b)
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:ua), hashtext(:ub))"),
            {"ua": str(ua), "ub": str(ub)},
        )

    async def add_like(
        self, from_id: uuid.UUID, to_id: uuid.UUID, score: float | None
    ) -> uuid.UUID | None:
        """Write the like and say whether this request is the one that wrote it.

        The caller used to ask first with a separate `SELECT likes` and insert only when the row
        was missing. The conflict clause already refuses a second row for the pair, so `RETURNING`
        answers the same question in the statement that writes it — and answers it for the race
        this path takes a pair lock over, where a pre-read can be stale by the time it is acted on.
        """
        stmt = (
            pg_insert(Like)
            .values(from_user_id=from_id, to_user_id=to_id, compatibility_score=score)
            .on_conflict_do_nothing(constraint="uq_like_pair")
            .returning(Like.id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_pass(self, from_id: uuid.UUID, to_id: uuid.UUID) -> Pass | None:
        stmt = select(Pass).where(Pass.from_user_id == from_id, Pass.to_user_id == to_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add_pass(self, from_id: uuid.UUID, to_id: uuid.UUID) -> None:
        await self.session.execute(
            pg_insert(Pass)
            .values(from_user_id=from_id, to_user_id=to_id)
            .on_conflict_do_nothing(constraint="uq_pass_pair")
        )

    async def delete_pass(self, from_id: uuid.UUID, to_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(Pass).where(Pass.from_user_id == from_id, Pass.to_user_id == to_id)
        )

    async def has_liked_back(self, from_id: uuid.UUID, to_id: uuid.UUID) -> bool:
        """True if `to_id` already liked `from_id` (i.e. a mutual like exists)."""
        stmt = select(Like.id).where(Like.from_user_id == to_id, Like.to_user_id == from_id)
        return (await self.session.execute(stmt)).first() is not None

    # --- Matches ---
    async def get_match(self, match_id: uuid.UUID) -> Match | None:
        return await self.session.get(Match, match_id)

    async def match_still_present(self, match_id: uuid.UUID) -> bool:
        """Ask the database, not the identity map, whether the match row is still there.

        Same reason ``ChatRepository.match_still_present`` exists (see the note on stage 11):
        ``session.get`` hands back an object this session already loaded without re-querying,
        so after a concurrent writer on another connection has committed a DELETE that took
        this row away — block (stage 9) via ``add_block`` or ``delete_account`` (stage 13)
        via ``purge_social_graph`` — the cached ``Match`` is a phantom. Reading the id
        column asks the current snapshot, which is what a post-lock re-check has to see.
        """
        stmt = select(Match.id).where(Match.id == match_id)
        return (await self.session.execute(stmt)).first() is not None

    async def get_match_between(self, a: uuid.UUID, b: uuid.UUID) -> Match | None:
        ua, ub = ordered_pair(a, b)
        stmt = select(Match).where(Match.user_a_id == ua, Match.user_b_id == ub)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def ensure_match(self, a: uuid.UUID, b: uuid.UUID, score: float) -> tuple[uuid.UUID, bool]:
        """Return (match_id, created_now) for the pair, creating it only once."""
        ua, ub = ordered_pair(a, b)
        stmt = (
            pg_insert(Match)
            .values(user_a_id=ua, user_b_id=ub, compatibility_score=score)
            .on_conflict_do_nothing(constraint="uq_match_pair")
            .returning(Match.id)
        )
        created = (await self.session.execute(stmt)).scalar()
        if created is not None:
            return created, True
        existing = await self.get_match_between(a, b)
        # The conflict can only have come from a concurrent like, whose row is now visible.
        return existing.id, False

    async def list_match_ids_for_user(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(Match.id).where(
            or_(Match.user_a_id == user_id, Match.user_b_id == user_id)
        )
        return [row[0] for row in (await self.session.execute(stmt)).all()]

    async def list_matches_for_user(self, user_id: uuid.UUID) -> list[Match]:
        stmt = select(Match).where(
            or_(Match.user_a_id == user_id, Match.user_b_id == user_id)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    # --- Blocks ---
    async def is_blocked_either(self, a: uuid.UUID, b: uuid.UUID) -> bool:
        stmt = select(Block.id).where(
            or_(
                and_(Block.blocker_id == a, Block.blocked_id == b),
                and_(Block.blocker_id == b, Block.blocked_id == a),
            )
        )
        return (await self.session.execute(stmt)).first() is not None

    async def add_block(self, blocker_id: uuid.UUID, blocked_id: uuid.UUID) -> uuid.UUID | None:
        await self.session.execute(
            pg_insert(Block)
            .values(blocker_id=blocker_id, blocked_id=blocked_id)
            .on_conflict_do_nothing(constraint="uq_block_pair")
        )
        # Blocking dissolves any existing match between the two users.
        ua, ub = ordered_pair(blocker_id, blocked_id)
        dissolved = (
            await self.session.execute(
                delete(Match)
                .where(Match.user_a_id == ua, Match.user_b_id == ub)
                .returning(Match.id)
            )
        ).scalar()
        return dissolved

    async def _purge_lock_targets(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        """Every peer whose pair lock a purge has to hold before reading or deleting edges.

        The set is read from what has been committed *now*: an edge to a peer that appears
        later is not something this transaction can serialise against, but it is also not
        a race — a like or a block arriving after the reading only succeeds against an
        account that is still live, and the post-lock ``_available_target`` re-check inside
        ``MatchService.like`` turns a like whose peer has committed its deletion into a 404.
        Sorting by ``str(uuid)`` gives every purge the same global order, so two
        simultaneous deletions of peers who liked each other cannot take their locks in
        opposite orders and deadlock.
        """
        partners: set[uuid.UUID] = set()
        for row in (
            await self.session.execute(
                select(Match.user_a_id, Match.user_b_id).where(
                    or_(Match.user_a_id == user_id, Match.user_b_id == user_id)
                )
            )
        ).all():
            a, b = row
            partners.add(b if a == user_id else a)
        for row in (
            await self.session.execute(
                select(Like.from_user_id, Like.to_user_id).where(
                    or_(Like.from_user_id == user_id, Like.to_user_id == user_id)
                )
            )
        ).all():
            f, t = row
            partners.add(t if f == user_id else f)
        for row in (
            await self.session.execute(
                select(Pass.from_user_id, Pass.to_user_id).where(
                    or_(Pass.from_user_id == user_id, Pass.to_user_id == user_id)
                )
            )
        ).all():
            f, t = row
            partners.add(t if f == user_id else f)
        for row in (
            await self.session.execute(
                select(Block.blocker_id, Block.blocked_id).where(
                    or_(Block.blocker_id == user_id, Block.blocked_id == user_id)
                )
            )
        ).all():
            blocker, blocked = row
            partners.add(blocked if blocker == user_id else blocker)
        partners.discard(user_id)
        return sorted(partners, key=str)

    async def purge_social_graph(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        """Delete every edge that points at an account which no longer represents a person.

        Deletion is a soft delete of the user row, so the database cascade never fires.
        Without this the ex-partner keeps a match whose chat still accepts messages, and a
        leftover like can turn into a match with an account that has already been deleted.
        Matches take their messages, read receipts and recommendations with them via the
        schema's ON DELETE CASCADE.

        The purge is a writer: it deletes Match rows and lets their CASCADE take child
        messages and read receipts. ``ChatService._require_membership_for_write`` and
        ``MatchService.like`` both serialise on the pair advisory lock, and
        ``SafetyService.block`` does too — a purge that skipped that lock could land in the
        window between a chat write's post-lock ``match_still_present`` re-check and its own
        ``INSERT INTO messages`` and produce a foreign-key violation, or miss a Match row
        whose parent like committed after the purge had already listed. Holding the same
        lock, in a canonical order across the pairs, makes the two take turns.
        """
        for other in await self._purge_lock_targets(user_id):
            await self.lock_pair(user_id, other)
        match_ids = await self.list_match_ids_for_user(user_id)
        if match_ids:
            await self.session.execute(delete(Match).where(Match.id.in_(match_ids)))
        pair = or_(Like.from_user_id == user_id, Like.to_user_id == user_id)
        await self.session.execute(delete(Like).where(pair))
        await self.session.execute(
            delete(Pass).where(or_(Pass.from_user_id == user_id, Pass.to_user_id == user_id))
        )
        await self.session.execute(
            delete(Block).where(or_(Block.blocker_id == user_id, Block.blocked_id == user_id))
        )
        return match_ids

    # --- Reports ---
    async def add_report(
        self, reporter_id: uuid.UUID, reported_id: uuid.UUID, reason: str, details: str | None
    ) -> bool:
        """Insert a report; False means an identical report already exists."""
        stmt = (
            pg_insert(Report)
            .values(reporter_id=reporter_id, reported_id=reported_id, reason=reason, details=details)
            .on_conflict_do_nothing(constraint="uq_report")
            .returning(Report.id)
        )
        return (await self.session.execute(stmt)).scalar() is not None



class DiscoveryRepository:
    """The reads behind discovery.

    Two rules shape everything here. A candidate is excluded by *predicate*, never by an
    id list carried from Python: the list grows with every swipe (5 000 of them made a
    190 KB statement whose planning alone cost 15 ms) while the anti-join stays the same
    size however long the viewer has been swiping. And the deck is stored, not recomputed:
    ``rank`` is written once, so a page cannot shift under someone who likes or passes
    between requests.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- eligibility -----------------------------------------------------------
    @staticmethod
    def _candidate_conditions(viewer_id: uuid.UUID, subject) -> list:
        """Facts about a candidate that hold regardless of what the viewer prefers."""
        return [
            User.is_deleted.is_(False),
            User.is_active.is_(True),
            Profile.is_hidden.is_(False),
            # An account that registered and never answered the setup questions still owns
            # a profile row -- the shell registration writes it, with the email local part
            # as the name and a placeholder birth date. It is not a person somebody agreed
            # to be shown, and a compatibility score read off a shell is a number about
            # nothing, so the deck waits for onboarding to have happened.
            Profile.onboarding_completed_at.is_not(None),
            subject != viewer_id,
        ]

    @staticmethod
    def _acted_conditions(viewer_id: uuid.UUID, subject) -> list:
        """The viewer's own gestures and the mutual block, as anti-joins."""
        return [
            ~select(Like.id).where(Like.from_user_id == viewer_id, Like.to_user_id == subject).exists(),
            ~select(Pass.id).where(Pass.from_user_id == viewer_id, Pass.to_user_id == subject).exists(),
            ~select(Block.id)
            .where(
                or_(
                    and_(Block.blocker_id == viewer_id, Block.blocked_id == subject),
                    and_(Block.blocker_id == subject, Block.blocked_id == viewer_id),
                )
            )
            .exists(),
            ~select(Match.id)
            .where(
                or_(
                    and_(Match.user_a_id == viewer_id, Match.user_b_id == subject),
                    and_(Match.user_b_id == viewer_id, Match.user_a_id == subject),
                )
            )
            .exists(),
        ]

    @staticmethod
    def _preference_conditions(
        gender_pref: list[str], age_min: int, age_max: int, city: str | None
    ) -> list:
        today = utc_today()
        # age >= age_min  <=>  birth_date <= today - age_min years.
        # age <= age_max  <=>  birth_date >  today - (age_max + 1) years, strictly: a
        # candidate whose birthday lands exactly on that lower bound turns age_max + 1
        # today, so an inclusive `>=` showed them at 31 to a viewer who asked for 30.
        max_birth = shift_years(today, age_min)
        min_birth = shift_years(today, age_max + 1)
        conds = [Profile.birth_date <= max_birth, Profile.birth_date > min_birth]
        if gender_pref:
            conds.append(Profile.gender.in_(gender_pref))
        if city:
            conds.append(func.lower(Profile.city) == city.lower())
        return conds

    def _still_showlable(self, viewer_id: uuid.UUID) -> select:
        """EXISTS-form of the full predicate, correlated on Profile.user_id.

        Used both to pick new deck rows and to ask whether any candidate is still
        waiting outside the deck, so ``has_more`` never contradicts the next request.
        """
        return (
            select(Profile.user_id)
            .join(User, User.id == Profile.user_id)
            .where(
                *self._candidate_conditions(viewer_id, Profile.user_id),
                *self._acted_conditions(viewer_id, Profile.user_id),
            )
        )

    def _never_queued(self, viewer_id: uuid.UUID):
        """A candidate the deck has never held, correlated on the candidate.

        An EXISTS that only names viewer_id would ask "does this viewer have a deck at
        all" — true from the second page on, which refuses every refill and ends a deck of
        thousands after one batch.
        """
        return (
            select(DiscoveryQueue.candidate_id)
            .where(
                DiscoveryQueue.viewer_id == viewer_id,
                DiscoveryQueue.candidate_id == Profile.user_id,
            )
            .exists()
        )

    async def new_candidate_ids(
        self,
        *,
        viewer_id: uuid.UUID,
        gender_pref: list[str],
        age_min: int,
        age_max: int,
        city: str | None,
        limit: int,
    ) -> list[uuid.UUID]:
        """Candidates nobody has been shown yet: eligible, matching preferences, not in the deck."""
        stmt = (
            self._still_showlable(viewer_id)
            .where(
                *self._preference_conditions(gender_pref, age_min, age_max, city),
                ~self._never_queued(viewer_id),
            )
            .order_by(Profile.created_at.desc(), Profile.user_id)
            .limit(limit)
        )
        return [row[0] for row in (await self.session.execute(stmt)).all()]

    async def total_candidates(
        self,
        *,
        viewer_id: uuid.UUID,
        gender_pref: list[str],
        age_min: int,
        age_max: int,
        city: str | None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(self._still_showlable(viewer_id).where(
                *self._preference_conditions(gender_pref, age_min, age_max, city)
            ).subquery())
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def has_unqueued_candidate(
        self,
        *,
        viewer_id: uuid.UUID,
        gender_pref: list[str],
        age_min: int,
        age_max: int,
        city: str | None,
    ) -> bool:
        """Is there anybody left to add to the deck? Cheap enough to ask per page."""
        stmt = (
            select(1)
            .select_from(self._still_showlable(viewer_id).where(
                *self._preference_conditions(gender_pref, age_min, age_max, city),
                ~self._never_queued(viewer_id),
            ).subquery())
            .limit(1)
        )
        return (await self.session.execute(stmt)).first() is not None

    # --- the deck --------------------------------------------------------------
    async def deck_ready_count(self, viewer_id: uuid.UUID, *, cap: int) -> int:
        """How many undelivered cards the deck holds, up to ``cap``.

        The caller only asks in order to decide whether to refill, so counting past the
        threshold answers nothing: an uncapped count over a 10 000-row deck cost 11 ms
        of heap fetches, while a capped one reads 41 index entries and stops.
        """
        stmt = (
            select(func.count())
            .select_from(
                select(DiscoveryQueue.rank)
                .where(
                    DiscoveryQueue.viewer_id == viewer_id,
                    DiscoveryQueue.status == READY,
                )
                .order_by(DiscoveryQueue.rank)
                .limit(cap)
                .subquery()
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def deck_next_rank(self, viewer_id: uuid.UUID) -> int:
        stmt = select(func.coalesce(func.max(DiscoveryQueue.rank), -1)).where(
            DiscoveryQueue.viewer_id == viewer_id
        )
        return int((await self.session.execute(stmt)).scalar_one()) + 1

    async def deck_append(
        self, viewer_id: uuid.UUID, ranked: list[tuple[uuid.UUID, int]], *, first_rank: int
    ) -> None:
        """Add one batch to the end of the deck. A concurrent build loses quietly.

        "Quietly" covers both collisions a concurrent refill can produce, so no constraint
        is named as the arbiter: the same candidate queued twice by two builds (the pair
        key), and a candidate landing on a rank another build already occupies (the rank
        key). Losing the rank is the survivable half — the row never gets written, the
        candidate stays outside the deck, and the next refill picks it up again, whereas a
        duplicate rank would put it behind a cursor step that already passed.
        """
        if not ranked:
            return
        values = [
            {
                "viewer_id": viewer_id,
                "candidate_id": candidate_id,
                "rank": first_rank + offset,
                "score": score,
                "status": READY,
                "queued_at": utcnow(),
            }
            for offset, (candidate_id, score) in enumerate(ranked)
        ]
        await self.session.execute(
            pg_insert(DiscoveryQueue).values(values).on_conflict_do_nothing()
        )

    async def deck_claim(
        self, viewer_id: uuid.UUID, *, after_rank: int, limit: int
    ) -> list[tuple[uuid.UUID, int, int]]:
        """Take the next ``limit`` rows and mark them seen in the same breath.

        ``SKIP LOCKED`` keeps two overlapping requests from handing the same card to
        both: the second one waits for neither, it simply gets what the first did not.
        """
        stmt = (
            select(DiscoveryQueue.candidate_id, DiscoveryQueue.rank, DiscoveryQueue.score)
            .where(
                DiscoveryQueue.viewer_id == viewer_id,
                DiscoveryQueue.status == READY,
                DiscoveryQueue.rank > after_rank,
            )
            .order_by(DiscoveryQueue.rank)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = (await self.session.execute(stmt)).all()
        if not rows:
            return []
        await self.session.execute(
            update(DiscoveryQueue)
            .where(
                DiscoveryQueue.viewer_id == viewer_id,
                DiscoveryQueue.candidate_id.in_([r[0] for r in rows]),
            )
            .values(status=SEEN, seen_at=utcnow())
        )
        return [(r[0], r[1], r[2]) for r in rows]

    async def deck_has_more(self, viewer_id: uuid.UUID, *, beyond_rank: int) -> bool:
        stmt = (
            select(DiscoveryQueue.candidate_id)
            .where(
                DiscoveryQueue.viewer_id == viewer_id,
                DiscoveryQueue.status == READY,
                DiscoveryQueue.rank > beyond_rank,
            )
            # Ordered, so the paging index answers it. Unordered, the planner walks the
            # table in whatever order the rows sit in and stopped after 4.8 ms of
            # filtering 20 000 seen rows to find one ready card.
            .order_by(DiscoveryQueue.rank)
            .limit(1)
        )
        return (await self.session.execute(stmt)).first() is not None

    async def deck_fresh_ids(self, viewer_id: uuid.UUID, candidate_ids: list[uuid.UUID]) -> list[uuid.UUID]:
        """Which of these queued candidates may still be shown, in the order given.

        A queued row is a promise made about a person who may have hidden, deleted their
        account or been blocked since. Checking the whole deck on every request costs two
        sequential scans of ``profiles`` and ``users`` (338 ms on a 120k copy), while the
        page being claimed is at most ``limit`` rows: the same promise kept per page is
        read as a handful of primary-key lookups. Rows found stale are deleted here, so
        they never occupy the deck a second time.
        """
        if not candidate_ids:
            return []
        still_ok = self._still_showlable(viewer_id).where(
            Profile.user_id.in_(candidate_ids)
        )
        ok = {row[0] for row in (await self.session.execute(still_ok)).all()}
        stale = [cid for cid in candidate_ids if cid not in ok]
        if stale:
            await self.session.execute(
                delete(DiscoveryQueue).where(
                    DiscoveryQueue.viewer_id == viewer_id,
                    DiscoveryQueue.candidate_id.in_(stale),
                )
            )
        return [cid for cid in candidate_ids if cid in ok]

    async def deck_invalidate(self, viewer_id: uuid.UUID) -> int:
        """Forget the undelivered part of the deck: the viewer changed what they want.

        Seen rows stay, because they are the memory of what was already shown — the
        rebuild must rank the new filters without ever repeating a card.
        """
        stmt = delete(DiscoveryQueue).where(
            DiscoveryQueue.viewer_id == viewer_id, DiscoveryQueue.status == READY
        )
        return (await self.session.execute(stmt)).rowcount or 0
