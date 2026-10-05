from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.compatibility.engine import CompatibilityInput, CompatibilityResult, compute_compatibility
from app.compatibility.explanation import CompatibilityExplanation, build_explanation
from app.compatibility.weights import DEFAULT_WEIGHT_CONFIG, WeightConfig
from app.core.exceptions import NotFoundError
from app.models import CompatibilityProfile, Profile
from app.repositories.social_repo import SocialRepository
from app.repositories.test_repo import TestRepository
from app.repositories.user_repo import UserRepository


class CompatibilityService:
    def __init__(self, session: AsyncSession, weight_config: WeightConfig = DEFAULT_WEIGHT_CONFIG) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.tests = TestRepository(session)
        self.social = SocialRepository(session)
        self.weight_config = weight_config

    async def build_input(self, user_id: uuid.UUID) -> CompatibilityInput:
        profile = await self.users.get_profile(user_id)
        if profile is None:
            raise NotFoundError("Profile not found.")
        cp = await self.tests.get_compatibility_profile(user_id)
        return self.input_from(profile, cp)

    @staticmethod
    def input_from(profile: Profile, cp: CompatibilityProfile | None) -> CompatibilityInput:
        vector = cp.vector if cp and isinstance(cp.vector, dict) else {}
        return CompatibilityInput(
            vector=vector,
            interests={i.slug for i in profile.interests},
            dating_goal=profile.dating_goal,
        )

    async def score_pair(self, a_id: uuid.UUID, b_id: uuid.UUID) -> CompatibilityResult:
        a = await self.build_input(a_id)
        b = await self.build_input(b_id)
        return compute_compatibility(a, b, self.weight_config)

    async def refresh_pair_scores(self, user_id: uuid.UUID) -> None:
        """Rewrite the stored percent of every match this user is in.

        A match row carries one number for the pair, and the match list and the pair
        header read it back. Nothing wrote it after the like landed, so a retake moved
        the compatibility screen — which computes live — and left the list promising the
        old percent. One pair has one score: the engine is symmetric, so refreshing it
        from either side of the pair gives the same answer.
        """
        matches = await self.social.list_matches_for_user(user_id)
        if not matches:
            return
        other_ids = [match.other_user(user_id) for match in matches]
        profiles = {p.user_id: p for p in await self.users.get_profiles_by_ids(other_ids)}
        vectors = await self.tests.get_compatibility_profiles(other_ids)
        me = await self.build_input(user_id)
        for match in matches:
            other_id = match.other_user(user_id)
            profile = profiles.get(other_id)
            if profile is None:
                continue
            other = self.input_from(profile, vectors.get(other_id))
            score = compute_compatibility(me, other, self.weight_config).overall
            if match.compatibility_score != score:
                match.compatibility_score = score

    async def explain_pair(self, a_id: uuid.UUID, b_id: uuid.UUID) -> tuple[CompatibilityResult, CompatibilityExplanation]:
        a = await self.build_input(a_id)
        b = await self.build_input(b_id)
        result = compute_compatibility(a, b, self.weight_config)
        explanation = build_explanation(a, b, result)
        return result, explanation
