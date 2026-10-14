from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.tracker import Event, tracker
from app.compatibility.traits import CATEGORY_BY_KEY, TRAIT_CATEGORIES_BY_KEY
from app.compatibility.weights import ENGINE_VERSION
from app.core.exceptions import NotFoundError, ValidationError
from app.models import TestAnswer
from app.repositories.activity_repo import ActivityRepository
from app.repositories.social_repo import DiscoveryRepository
from app.repositories.test_repo import TestRepository
from app.services.compatibility_service import CompatibilityService


class TestService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = TestRepository(session)

    async def list_questions(self) -> list:
        return await self.repo.list_active_questions()

    async def answer_choices(self, user_id: uuid.UUID) -> dict[int, int]:
        """Which option this person stands on, per question — the read that lets the catalogue
        mark its own cards instead of asking the person to remember what they tapped."""
        return await self.repo.list_answer_choices(user_id)

    @staticmethod
    def category_summary(questions: list, choices: dict[int, int]) -> list[dict]:
        """Counts per category of the catalogue it is handed, in the order its sections appear.

        Rows or ORM objects — the count only reads ``id`` and ``category``, so the route sending
        the whole questionnaire and the route just counting it derive the sections from the same
        two reads and cannot hand the screens two different lists.

        A category nobody answered keeps its row with ``answered=0`` instead of dropping out: the
        screen uses this list to name the part of the profile that is still empty, and a missing
        row cannot be told from a finished one.
        """
        totals: dict[str, int] = {}
        answered: dict[str, int] = {}
        for question in questions:
            totals[question.category] = totals.get(question.category, 0) + 1
            if question.id in choices:
                answered[question.category] = answered.get(question.category, 0) + 1
        return [
            {
                "key": key,
                "label": CATEGORY_BY_KEY.get(key).label if key in CATEGORY_BY_KEY else key,
                "total": total,
                "answered": answered.get(key, 0),
            }
            for key, total in totals.items()
        ]

    async def progress(self, user_id: uuid.UUID) -> dict:
        """How far the person has come, and how far each section of the catalogue has come.

        Two reads, and they are the two the catalogue route already pays: the active questions as
        ``(id, section)`` rows and the person's own answers as ``(question, option)`` pairs. Two
        ``COUNT``s cost the same and could not name a section, so a screen asking «what is still
        empty here» had to fetch the whole questionnaire to answer it.
        """
        questions = await self.repo.list_active_question_axes()
        choices = await self.repo.list_answer_choices(user_id)
        total = len(questions)
        answered = len(choices)
        percent = int(round((answered / total) * 100)) if total else 0
        return {
            "answered": answered,
            "total": total,
            "percent": min(100, percent),
            "remaining": max(0, total - answered),
            "completed": total > 0 and answered >= total,
            "categories": self.category_summary(questions, choices),
        }

    async def save_answers(self, user_id: uuid.UUID, answers: list[dict]) -> dict:
        if not answers:
            raise ValidationError("No answers provided.")
        # The whole batch is checked against one read of the catalog, and nothing is written
        # until every answer in it is known to be valid — a body naming one impossible option
        # leaves the stored answers exactly as they were.
        questions = await self.repo.get_active_questions(
            {item["question_id"] for item in answers}
        )
        # The catalogue is checked before the batch it belongs to is written, so an answer to a
        # drifted question cannot reach `test_answers` at all.
        self._require_declared_axes(questions)
        catalog = {q.id: {option.id for option in q.options} for q in questions}
        rows: dict[int, int] = {}
        for item in answers:
            options = catalog.get(item["question_id"])
            if options is None:
                raise NotFoundError(f"Question {item['question_id']} not found.")
            if item["option_id"] not in options:
                raise ValidationError(
                    f"Option {item['option_id']} does not belong to question {item['question_id']}."
                )
            rows[item["question_id"]] = item["option_id"]
        await self.repo.upsert_answers(user_id, list(rows.items()))
        await self.session.commit()
        # Recompute the compatibility profile whenever answers change.
        await self.recompute_profile(user_id)
        return await self.progress(user_id)

    async def build_vector(self, user_id: uuid.UUID) -> tuple[dict, dict]:
        """Build (trait_vector, category_scores) from stored answers.

        trait_vector: {category: {trait: mean(option values)}}
        category_scores: {category: mean(trait values)} in 0..1
        """
        answers = await self.repo.list_answers(user_id)
        buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for ans in answers:
            q = ans.question
            if q is None:
                continue
            opt = ans.option
            value = float(opt.value) if opt is not None else 0.0
            buckets[q.category][q.trait].append(max(0.0, min(1.0, value)))

        vector: dict[str, dict[str, float]] = {}
        category_scores: dict[str, float] = {}
        for category, traits in buckets.items():
            trait_means: dict[str, float] = {}
            for trait, values in traits.items():
                trait_means[trait] = sum(values) / len(values) if values else 0.0
            vector[category] = trait_means
            if trait_means:
                category_scores[category] = sum(trait_means.values()) / len(trait_means)
        return vector, category_scores

    async def recompute_profile(self, user_id: uuid.UUID) -> tuple[dict, dict]:
        """Rewrite the derived rows from the stored answers, and hand back what was built.

        The vector and the category scores are read out of the answers here, so a caller that
        wants them for its response takes them from this return instead of reading the same
        answers, questions and options a second time.
        """
        vector, category_scores = await self.build_vector(user_id)
        await self.repo.upsert_compatibility_profile(user_id, vector, ENGINE_VERSION)
        await self.repo.replace_results(user_id, category_scores)
        await self.session.commit()
        # Every queued card was ranked against the vector that just changed. The seen rows
        # stay — what was shown was shown — but the order of what has not been is rebuilt.
        await DiscoveryRepository(self.session).deck_invalidate(user_id)
        # The same goes for the pairs that were handed a page of activities scored against
        # the old answers: their next visit recomputes it instead of rereading it.
        await ActivityRepository(self.session).invalidate_for_user(user_id)
        # And for the percent sitting on the match row, which the match list shows as if it
        # were current. The answers behind it just changed, so it is rewritten from them.
        await CompatibilityService(self.session).refresh_pair_scores(user_id)
        # This is a write and the request session commits nothing on its own; without this
        # line the deck is left holding the ranking the viewer just replaced.
        await self.session.commit()
        return vector, category_scores

    async def complete(self, user_id: uuid.UUID) -> dict:
        progress = await self.progress(user_id)
        if not progress["completed"]:
            raise ValidationError(
                f"Test is not finished yet ({progress['answered']}/{progress['total']})."
            )
        vector, category_scores = await self.recompute_profile(user_id)
        tracker.track(Event.TEST_COMPLETED, str(user_id), categories=len(category_scores))
        return {
            "categories": category_scores,
            "vector": vector,
            "engine_version": ENGINE_VERSION,
        }

    @staticmethod
    def _require_declared_axes(questions: list) -> None:
        """Refuse a batch that answers a question naming an axis the taxonomy does not declare.

        The vector is keyed by the question row's own `category` and `trait`, while the engine reads
        it back through `TRAIT_CATEGORIES_BY_KEY`, so a pair that agrees today is an invariant
        nothing except this method states. Measured on the live stand before this stage, with one
        `test_questions` row inserted at `category='leisure', trait='gaming_taste'`: the batch of 22
        answers returned 200, the name was stored in `compatibility_profiles.vector`, the pair's
        percent moved 92 -> 91 because `_trait_similarity` counts every key of the intersection,
        `_trait_label` handed back the raw slug, and the match screen's line came out as
        "Разное отношение: gaming_taste — gaming_taste vs gaming_taste". A declared axis differs by
        a Russian word on the same screen.

        Rows are sorted by id so a batch answering two drifted questions refuses with the same name
        every time, and the unknown category is refused too: it folds into the vector the same way
        and the engine simply never reads it back, which is the other half of the same silence.
        """
        for q in sorted(questions, key=lambda row: row.id):
            category = TRAIT_CATEGORIES_BY_KEY.get(q.category)
            if category is None:
                raise ValidationError(
                    f"Question {q.id} names category '{q.category}', which the trait taxonomy "
                    "does not declare."
                )
            declared = {trait.key for trait in category.traits}
            if q.trait not in declared:
                raise ValidationError(
                    f"Question {q.id} names trait '{q.trait}', which category '{q.category}' "
                    f"does not declare; its axes are {', '.join(sorted(declared))}."
                )
