from __future__ import annotations

import uuid

from sqlalchemy import and_, or_, select, func, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Block, Like, Match, Pass, Report, User, Profile


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
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def candidate_ids(
        self,
        *,
        viewer_id: uuid.UUID,
        gender_pref: list[str],
        age_min: int,
        age_max: int,
        city: str | None,
        exclude_ids: set[uuid.UUID],
        limit: int,
        offset: int,
    ) -> list[uuid.UUID]:
        """Return profile-visible candidate user ids matching filters.

        Excludes the viewer, hidden/deleted profiles, blocked users and anyone
        the viewer already liked or passed. Age is filtered via birth_date.
        """
        stmt = select(Profile.user_id).join(User, User.id == Profile.user_id).where(
            User.is_deleted.is_(False),
            User.is_active.is_(True),
            Profile.is_hidden.is_(False),
            Profile.user_id != viewer_id,
        )
        if gender_pref:
            stmt = stmt.where(Profile.gender.in_(gender_pref))
        if city:
            stmt = stmt.where(func.lower(Profile.city) == city.lower())

        # Age filter expressed through birth_date bounds.
        from datetime import date

        today = date.today()
        # birth_date <= today - age_min years  AND  birth_date >= today - (age_max+1) years
        max_birth = date(today.year - age_min, today.month, today.day)
        min_birth = date(today.year - (age_max + 1), today.month, today.day)
        stmt = stmt.where(Profile.birth_date <= max_birth, Profile.birth_date >= min_birth)

        if exclude_ids:
            stmt = stmt.where(Profile.user_id.not_in(list(exclude_ids)))

        stmt = stmt.order_by(Profile.created_at.desc(), Profile.user_id).limit(limit).offset(offset)
        return [row[0] for row in (await self.session.execute(stmt)).all()]

    async def total_candidates(
        self,
        *,
        viewer_id: uuid.UUID,
        gender_pref: list[str],
        age_min: int,
        age_max: int,
        city: str | None,
        exclude_ids: set[uuid.UUID],
    ) -> int:
        from datetime import date

        stmt = (
            select(func.count(Profile.user_id))
            .join(User, User.id == Profile.user_id)
            .where(
                User.is_deleted.is_(False),
                User.is_active.is_(True),
                Profile.is_hidden.is_(False),
                Profile.user_id != viewer_id,
            )
        )
        if gender_pref:
            stmt = stmt.where(Profile.gender.in_(gender_pref))
        if city:
            stmt = stmt.where(func.lower(Profile.city) == city.lower())
        today = date.today()
        max_birth = date(today.year - age_min, today.month, today.day)
        min_birth = date(today.year - (age_max + 1), today.month, today.day)
        stmt = stmt.where(Profile.birth_date <= max_birth, Profile.birth_date >= min_birth)
        if exclude_ids:
            stmt = stmt.where(Profile.user_id.not_in(list(exclude_ids)))
        return int((await self.session.execute(stmt)).scalar_one())
