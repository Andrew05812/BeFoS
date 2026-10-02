from __future__ import annotations

import uuid

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    CompatibilityProfile,
    TestAnswer,
    TestOption,
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

    async def get_question(self, question_id: int) -> TestQuestion | None:
        stmt = select(TestQuestion).options(selectinload(TestQuestion.options)).where(
            TestQuestion.id == question_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_option(self, option_id: int) -> TestOption | None:
        return await self.session.get(TestOption, option_id)

    async def list_answers(self, user_id: uuid.UUID) -> list[TestAnswer]:
        stmt = select(TestAnswer).where(TestAnswer.user_id == user_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def upsert_answer(
        self, user_id: uuid.UUID, question_id: int, option_id: int
    ) -> TestAnswer:
        stmt = select(TestAnswer).where(
            TestAnswer.user_id == user_id, TestAnswer.question_id == question_id
        )
        answer = (await self.session.execute(stmt)).scalar_one_or_none()
        if answer is None:
            answer = TestAnswer(user_id=user_id, question_id=question_id, option_id=option_id)
            self.session.add(answer)
        else:
            answer.option_id = option_id
        await self.session.flush()
        return answer

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
    ) -> CompatibilityProfile:
        profile = await self.get_compatibility_profile(user_id)
        if profile is None:
            profile = CompatibilityProfile(user_id=user_id, vector=vector, version=version)
            self.session.add(profile)
        else:
            profile.vector = vector
            profile.version = version
        await self.session.flush()
        return profile

    async def replace_results(
        self, user_id: uuid.UUID, category_scores: dict[str, float]
    ) -> None:
        await self.session.execute(delete(TestResult).where(TestResult.user_id == user_id))
        for category, score in category_scores.items():
            self.session.add(TestResult(user_id=user_id, category=category, score=score))
        await self.session.flush()

    async def list_results(self, user_id: uuid.UUID) -> list[TestResult]:
        stmt = select(TestResult).where(TestResult.user_id == user_id)
        return list((await self.session.execute(stmt)).scalars().all())
