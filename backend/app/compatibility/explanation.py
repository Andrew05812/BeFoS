from __future__ import annotations

from dataclasses import dataclass, field

from app.compatibility.engine import CompatibilityInput, CompatibilityResult
from app.compatibility.traits import CATEGORY_BY_KEY, TRAIT_CATEGORIES_BY_KEY

# Thresholds that decide whether a trait/category counts as a strength,
# a difference, or neither. Tunable, deterministic.
STRENGTH_THRESHOLD = 0.75
DIFFERENCE_THRESHOLD = 0.40


@dataclass(frozen=True)
class ExplanationItem:
    category: str
    label: str
    text: str
    score: float


@dataclass(frozen=True)
class CompatibilityExplanation:
    overall_percent: int
    strengths: list[ExplanationItem] = field(default_factory=list)
    differences: list[ExplanationItem] = field(default_factory=list)
    shared_interests: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "overall_percent": self.overall_percent,
            "strengths": [vars(i) for i in self.strengths],
            "differences": [vars(i) for i in self.differences],
            "shared_interests": self.shared_interests,
        }


def _trait_label(category_key: str, trait_key: str) -> tuple[str, str, str]:
    cat = TRAIT_CATEGORIES_BY_KEY.get(category_key)
    if not cat:
        return (trait_key, trait_key, trait_key)
    trait = next((t for t in cat.traits if t.key == trait_key), None)
    if not trait:
        return (trait_key, trait_key, trait_key)
    return (trait.label, trait.low_label, trait.high_label)


def _describe_side(value: float, low_label: str, high_label: str) -> str:
    if value >= 0.66:
        return high_label
    if value <= 0.33:
        return low_label
    return "умеренно"


def _one_per_category(items: list[ExplanationItem]) -> list[ExplanationItem]:
    """Keep only the strongest item of each category, in the given order.

    A category holds several traits, so the same label could repeat — "Досуг" twice
    in one list reads as a glitch and pushes other categories out of the top six.
    """
    seen: set[str] = set()
    kept: list[ExplanationItem] = []
    for item in items:
        if item.category in seen:
            continue
        seen.add(item.category)
        kept.append(item)
    return kept


def build_explanation(
    a: CompatibilityInput,
    b: CompatibilityInput,
    result: CompatibilityResult,
) -> CompatibilityExplanation:
    """Generate a human-readable, deterministic explanation of a match.

    Strengths and differences are derived from the actual trait vectors and
    interest sets - never random text.
    """
    strengths: list[ExplanationItem] = []
    differences: list[ExplanationItem] = []

    for cat_score in result.categories:
        key = cat_score.key
        label = cat_score.label

        if key in TRAIT_CATEGORIES_BY_KEY:
            a_traits = a.vector.get(key, {})
            b_traits = b.vector.get(key, {})
            for trait_key in sorted(a_traits.keys() & b_traits.keys()):
                va = max(0.0, min(1.0, float(a_traits[trait_key])))
                vb = max(0.0, min(1.0, float(b_traits[trait_key])))
                sim = 1.0 - abs(va - vb)
                t_label, low_label, high_label = _trait_label(key, trait_key)
                if sim >= STRENGTH_THRESHOLD:
                    side = _describe_side((va + vb) / 2, low_label, high_label)
                    strengths.append(
                        ExplanationItem(
                            category=key,
                            label=label,
                            text=f"Похожее отношение: {t_label.lower()} ({side})",
                            score=round(sim, 3),
                        )
                    )
                elif sim <= DIFFERENCE_THRESHOLD:
                    differences.append(
                        ExplanationItem(
                            category=key,
                            label=label,
                            text=f"Разное отношение: {t_label.lower()} — {_describe_side(va, low_label, high_label)} vs {_describe_side(vb, low_label, high_label)}",
                            score=round(sim, 3),
                        )
                    )
        elif key == "interests":
            shared = sorted(a.interests & b.interests)
            if cat_score.score >= STRENGTH_THRESHOLD and shared:
                strengths.append(
                    ExplanationItem(
                        category=key,
                        label=label,
                        text="Много общих интересов",
                        score=round(cat_score.score, 3),
                    )
                )
            elif cat_score.score <= DIFFERENCE_THRESHOLD:
                differences.append(
                    ExplanationItem(
                        category=key,
                        label=label,
                        text="Мало общих интересов",
                        score=round(cat_score.score, 3),
                    )
                )
        elif key == "goals":
            if cat_score.score >= STRENGTH_THRESHOLD and cat_score.has_data:
                strengths.append(
                    ExplanationItem(
                        category=key,
                        label=label,
                        text="Совпадающие цели знакомства",
                        score=round(cat_score.score, 3),
                    )
                )
            elif cat_score.score <= DIFFERENCE_THRESHOLD and cat_score.has_data:
                differences.append(
                    ExplanationItem(
                        category=key,
                        label=label,
                        text="Разные цели знакомства",
                        score=round(cat_score.score, 3),
                    )
                )

    strengths.sort(key=lambda i: (-i.score, i.category))
    differences.sort(key=lambda i: (i.score, i.category))

    return CompatibilityExplanation(
        overall_percent=result.overall_percent,
        strengths=_one_per_category(strengths)[:6],
        differences=_one_per_category(differences)[:4],
        shared_interests=sorted(a.interests & b.interests),
    )


def category_labels() -> dict[str, str]:
    return {key: cat.label for key, cat in CATEGORY_BY_KEY.items()}
