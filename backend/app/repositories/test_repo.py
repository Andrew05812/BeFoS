from __future__ import annotations

import uuid

from sqlalchemy import select, func, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    CompatibilityProfile,
    TestAnswer,
    TestQuestion,
    TestResult,
)


class TestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_active_questions(self) -> list[TestQuestion]:
        stmt = (
            select(TestQuestion)
            .options(selectinload(TestQuestion.options))
            .where(TestQuestion.is_active.is_(True))
            .order_by(TestQuestion.position, TestQuestion.id)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_active_questions(self) -> int:
        stmt = select(func.count(TestQuestion.id)).where(TestQuestion.is_active.is_(True))
        return int((await self.session.execute(stmt)).scalar_one())

    async def get_active_questions(self, question_ids: set[int]) -> list[TestQuestion]:
        """The catalog rows a batch of answers names, in one read.

        The options come along by loader, not by a second query per question: validation
        only asks whether an option belongs to the question it was sent with.
        """
        if not question_ids:
            return []
        stmt = (
            select(TestQuestion)
            .options(selectinload(TestQuestion.options))
            .where(TestQuestion.id.in_(question_ids), TestQuestion.is_active.is_(True))
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_answers(self, user_id: uuid.UUID) -> list[TestAnswer]:
        # Ordered by question, not left to the heap: re-tapping one answer writes a new
        # tuple version and the row lands at the end of the table, so an unordered read
        # hands the vector builder the same answers in a different order. Its sums are
        # floats, and a float sum changes with the order of its terms.
        stmt = (
            select(TestAnswer)
            .where(TestAnswer.user_id == user_id)
            .order_by(TestAnswer.question_id)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def upsert_answers(
        self, user_id: uuid.UUID, rows: list[tuple[int, int]]
    ) -> None:
        """Write a whole batch of answers in one statement.

        One statement, decided by the unique constraint: a re-tap sends a second insert
        before the first has committed, so a prior read cannot be the gate. The caller
        collapses repeated questions — Postgres refuses an ON CONFLICT statement whose
        own rows collide.
        """
        if not rows:
            return
        # Sorted by question: two batches sent at once then take their row locks in the same
        # order, so the second waits for the first instead of deadlocking against it.
        stmt = pg_insert(TestAnswer).values(
            [
                {"user_id": user_id, "question_id": question_id, "option_id": option_id}
                for question_id, option_id in sorted(rows)
            ]
        )
        await self.session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_user_question_answer",
                set_={"option_id": stmt.excluded.option_id},
            )
        )

    async def count_answered(self, user_id: uuid.UUID) -> int:
        stmt = select(func.count(TestAnswer.id)).where(TestAnswer.user_id == user_id)
        return int((await self.session.execute(stmt)).scalar_one())

    async def get_compatibility_profile(self, user_id: uuid.UUID) -> CompatibilityProfile | None:
        stmt = select(CompatibilityProfile).where(CompatibilityProfile.user_id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_compatibility_profiles(
        self, user_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, CompatibilityProfile]:
        if not user_ids:
            return {}
        stmt = select(CompatibilityProfile).where(CompatibilityProfile.user_id.in_(user_ids))
        return {cp.user_id: cp for cp in (await self.session.execute(stmt)).scalars()}

    async def upsert_compatibility_profile(
        self, user_id: uuid.UUID, vector: dict, version: int
    ) -> None:
        await self.session.execute(
            pg_insert(CompatibilityProfile)
            .values(user_id=user_id, vector=vector, version=version)
            .on_conflict_do_update(
                index_elements=[CompatibilityProfile.user_id],
                set_={"vector": vector, "version": version},
            )
        )

    async def replace_results(
        self, user_id: uuid.UUID, category_scores: dict[str, float]
    ) -> None:
        await self.session.execute(delete(TestResult).where(TestResult.user_id == user_id))
        if not category_scores:
            return
        # Same reason as upsert_answers: two completes in flight both write the category
        # rows, and the constraint — not a prior read — decides.
        stmt = pg_insert(TestResult).values(
            [
                {"user_id": user_id, "category": category, "score": score}
                for category, score in category_scores.items()
            ]
        )
        await self.session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_user_category_result",
                set_={"score": stmt.excluded.score},
            )
        )

    async def list_results(self, user_id: uuid.UUID) -> list[TestResult]:
        stmt = select(TestResult).where(TestResult.user_id == user_id)
        return list((await self.session.execute(stmt)).scalars().all())
