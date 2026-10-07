from __future__ import annotations

import uuid
from typing import Sequence

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
        return await self.input_for(profile)

    async def input_for(self, profile: Profile) -> CompatibilityInput:
        """The input for a profile that is already in hand: its row is not read a second time.

        Callers that fetched the profile for their own reasons — the deck's rule, the card the
        response is built from — otherwise pay a fresh ``SELECT profiles`` plus its interests
        loader for numbers they were about to compute from data they already hold.
        """
        cp = await self.tests.get_compatibility_profile(profile.user_id)
        return self.input_from(profile, cp)

    @staticmethod
    def input_from(profile: Profile, cp: CompatibilityProfile | None) -> CompatibilityInput:
        vector = cp.vector if cp and isinstance(cp.vector, dict) else {}
        return CompatibilityInput(
            vector=vector,
            interests={i.slug for i in profile.interests},
            dating_goal=profile.dating_goal,
        )

    def score_inputs(self, a: CompatibilityInput, b: CompatibilityInput) -> CompatibilityResult:
        return compute_compatibility(a, b, self.weight_config)

    async def score_pair(self, a_id: uuid.UUID, b_id: uuid.UUID) -> CompatibilityResult:
        a = await self.build_input(a_id)
        b = await self.build_input(b_id)
        return self.score_inputs(a, b)

    async def inputs_from(self, profiles: Sequence[Profile]) -> dict[uuid.UUID, CompatibilityInput]:
        """The input for every profile already in hand, from one read of the answer vectors.

        ``input_for`` is right for a single row. A caller holding two of them — a pair on the
        compatibility screen, a like that scores itself against the person it likes — paid one
        ``SELECT compatibility_profiles`` per person for a table keyed by ``user_id`` with a
        unique index that fits both ids in one statement, which is how the deck has always read
        a whole page of vectors.
        """
        vectors = await self.tests.get_compatibility_profiles([p.user_id for p in profiles])
        return {p.user_id: self.input_from(p, vectors.get(p.user_id)) for p in profiles}

    async def pair_inputs(
        self, a_id: uuid.UUID, b_id: uuid.UUID
    ) -> tuple[CompatibilityInput, CompatibilityInput]:
        """Both halves of a pair from one read per concern, the way the deck reads a page.

        ``build_input`` asks for one person: their row, their interest list, their answer vector.
        Called twice it made the pair screen pay six times for what one batch of profiles carries
        for both and one batch of vectors answers for both — the deck has always read a page of
        people in two statements and one.
        """
        ids = [a_id, b_id]
        profiles = {p.user_id: p for p in await self.users.get_profiles_by_ids(ids)}
        if a_id not in profiles or b_id not in profiles:
            raise NotFoundError("Profile not found.")
        inputs = await self.inputs_from([profiles[a_id], profiles[b_id]])
        return inputs[a_id], inputs[b_id]

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
        # This user is one of the people whose row the loop needs, and the peers are the rest, so
        # both halves of every pair come from the same two batch reads.
        ids = [user_id, *other_ids]
        profiles = {p.user_id: p for p in await self.users.get_profiles_by_ids(ids)}
        me_profile = profiles.get(user_id)
        if me_profile is None:
            raise NotFoundError("Profile not found.")
        peers = [profiles[other_id] for other_id in other_ids if other_id in profiles]
        inputs = await self.inputs_from([me_profile, *peers])
        me = inputs[user_id]
        for match in matches:
            other_id = match.other_user(user_id)
            other = inputs.get(other_id)
            if other is None:
                continue
            score = compute_compatibility(me, other, self.weight_config).overall
            if match.compatibility_score != score:
                match.compatibility_score = score

    async def explain_pair(self, a_id: uuid.UUID, b_id: uuid.UUID) -> tuple[CompatibilityResult, CompatibilityExplanation]:
        a, b = await self.pair_inputs(a_id, b_id)
        result = self.score_inputs(a, b)
        explanation = build_explanation(a, b, result)
        return result, explanation
