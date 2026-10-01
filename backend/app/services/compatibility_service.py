from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.compatibility.engine import CompatibilityInput, CompatibilityResult, compute_compatibility
from app.compatibility.explanation import CompatibilityExplanation, build_explanation
from app.compatibility.weights import DEFAULT_WEIGHT_CONFIG, WeightConfig
from app.core.exceptions import NotFoundError
from app.repositories.test_repo import TestRepository
from app.repositories.user_repo import UserRepository


class CompatibilityService:
    def __init__(self, session: AsyncSession, weight_config: WeightConfig = DEFAULT_WEIGHT_CONFIG) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.tests = TestRepository(session)
        self.weight_config = weight_config

    async def build_input(self, user_id: uuid.UUID) -> CompatibilityInput:
        profile = await self.users.get_profile(user_id)
        if profile is None:
            raise NotFoundError("Profile not found.")
        cp = await self.tests.get_compatibility_profile(user_id)
        vector = cp.vector if cp and isinstance(cp.vector, dict) else {}
        interests = {i.slug for i in profile.interests}
        return CompatibilityInput(
            vector=vector,
            interests=interests,
            dating_goal=profile.dating_goal,
        )

    async def score_pair(self, a_id: uuid.UUID, b_id: uuid.UUID) -> CompatibilityResult:
        a = await self.build_input(a_id)
        b = await self.build_input(b_id)
        return compute_compatibility(a, b, self.weight_config)

    async def explain_pair(self, a_id: uuid.UUID, b_id: uuid.UUID) -> tuple[CompatibilityResult, CompatibilityExplanation]:
        a = await self.build_input(a_id)
        b = await self.build_input(b_id)
        result = compute_compatibility(a, b, self.weight_config)
        explanation = build_explanation(a, b, result)
        return result, explanation
