from __future__ import annotations

import uuid

from sqlalchemy import and_, or_, select, func, delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Block, DiscoveryQueue, Like, Match, Pass, Report, User, Profile
from app.models.base import utcnow
from app.models.discovery import READY, SEEN


def ordered_pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Return the pair sorted so matches are direction-independent & unique."""
    return (a, b) if str(a) <= str(b) else (b, a)


class SocialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Likes / Passes ---
    # Every "has it already?" check below is advisory: two requests for the same gesture
    # (a double tap, a retry after a dropped connection) can both pass it and then both
    # try to insert. The writes therefore go through ON CONFLICT DO NOTHING against the
    # same unique constraint the schema already enforces, so the second one is a no-op
    # instead of an IntegrityError that surfaces to the user as a failed action.
    async def get_like(self, from_id: uuid.UUID, to_id: uuid.UUID) -> Like | None:
        stmt = select(Like).where(Like.from_user_id == from_id, Like.to_user_id == to_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add_like(self, from_id: uuid.UUID, to_id: uuid.UUID, score: float | None) -> None:
        await self.session.execute(
            pg_insert(Like)
            .values(from_user_id=from_id, to_user_id=to_id, compatibility_score=score)
            .on_conflict_do_nothing(constraint="uq_like_pair")
        )

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

    async def list_blocked_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        stmt = select(Block.blocked_id).where(Block.blocker_id == user_id)
        ids = {row[0] for row in (await self.session.execute(stmt)).all()}
        stmt2 = select(Block.blocker_id).where(Block.blocked_id == user_id)
        ids |= {row[0] for row in (await self.session.execute(stmt2)).all()}
        return ids

    async def purge_social_graph(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        """Delete every edge that points at an account which no longer represents a person.

        Deletion is a soft delete of the user row, so the database cascade never fires.
        Without this the ex-partner keeps a match whose chat still accepts messages, and a
        leftover like can turn into a match with an account that has already been deleted.
        Matches take their messages, read receipts and recommendations with them via the
        schema's ON DELETE CASCADE.
        """
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
        from datetime import date

        today = date.today()
        # birth_date <= today - age_min years  AND  birth_date >= today - (age_max+1) years
        max_birth = date(today.year - age_min, today.month, today.day)
        min_birth = date(today.year - (age_max + 1), today.month, today.day)
        conds = [Profile.birth_date <= max_birth, Profile.birth_date >= min_birth]
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
        """Add one batch to the end of the deck. A concurrent build loses quietly."""
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
            pg_insert(DiscoveryQueue).values(values).on_conflict_do_nothing(
                constraint="uq_discovery_queue_pair"
            )
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
