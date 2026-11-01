from __future__ import annotations

from dataclasses import dataclass, field

from app.compatibility.engine import CompatibilityInput, CompatibilityResult
from app.compatibility.traits import (
    CATEGORY_BY_KEY,
    TRAIT_CATEGORIES_BY_KEY,
    connection_for,
    describe_side,
    DIFFERENCE_THRESHOLD,
    STRENGTH_THRESHOLD,
)

__all__ = [
    "CompatibilityExplanation",
    "ExplanationItem",
    "build_explanation",
    "category_labels",
    "DIFFERENCE_THRESHOLD",
    "STRENGTH_THRESHOLD",
]


@dataclass(frozen=True)
class ExplanationItem:
    category: str
    label: str
    text: str
    score: float
    # The kind of gap or match this line is, named by the same rule the pair map uses for its
    # nodes. A line without it left the screen to guess, and the guess differed per surface.
    connection: str = ""


@dataclass(frozen=True)
class CompatibilityExplanation:
    overall_percent: int
    strengths: list[ExplanationItem] = field(default_factory=list)
    differences: list[ExplanationItem] = field(default_factory=list)
    shared_interests: list[str] = field(default_factory=list)
    # The same interests as the person reads them. Carried beside the slugs rather than instead of
    # them: the slug is the stable id a screen keys on, the title is what a sentence may print, and
    # only the service that already loaded the pair's rows knows both.
    shared_interest_titles: list[str] = field(default_factory=list)
    bands_measured: int = 0
    bands_total: int = 0
    measured_weight: float = 0.0
    starter: str = ""

    def to_dict(self) -> dict:
        return {
            "overall_percent": self.overall_percent,
            "strengths": [vars(i) for i in self.strengths],
            "differences": [vars(i) for i in self.differences],
            "shared_interests": self.shared_interests,
            "shared_interest_titles": self.shared_interest_titles,
            "bands_measured": self.bands_measured,
            "bands_total": self.bands_total,
            "measured_weight": self.measured_weight,
            "starter": self.starter,
        }


def _trait_label(category_key: str, trait_key: str) -> tuple[str, str, str]:
    cat = TRAIT_CATEGORIES_BY_KEY.get(category_key)
    if not cat:
        return (trait_key, trait_key, trait_key)
    trait = next((t for t in cat.traits if t.key == trait_key), None)
    if not trait:
        return (trait_key, trait_key, trait_key)
    return (trait.label, trait.low_label, trait.high_label)


def _one_per_category(items: list[ExplanationItem]) -> list[ExplanationItem]:
    """Keep only the strongest item of each category, in the given order.

    A category holds several traits, so the same label could repeat — "Досуг" twice in one list
    reads as a glitch. This is the whole limit: seven bands, at most seven lines. A slice on top
    of it cut the list below the number of bands, and the victim was whichever category's Latin
    key sorted last among equal scores — the pair's screen then refused to explain a band it had
    just printed a percent for.
    """
    seen: set[str] = set()
    kept: list[ExplanationItem] = []
    for item in items:
        if item.category in seen:
            continue
        seen.add(item.category)
        kept.append(item)
    return kept


def _starter(
    shared: list[str],
    strengths: list[ExplanationItem],
    differences: list[ExplanationItem],
    bands_measured: int,
) -> str:
    """The one place the pair can start, named only from what was actually compared.

    Ordered by what the engine really holds: a named common interest first, then a band the two
    answered the same way, then a band where they differ (which is a conversation, not a verdict).
    When nothing was compared the sentence says so — the percent at that point rests on the
    engine's neutral, and calling it a result would be the lie the screen keeps telling.
    """
    if shared:
        return f"Начните с общего интереса: «{shared[0]}»"
    if strengths:
        return f"Начните с того, где вы уже совпадаете: {strengths[0].label.lower()}"
    if differences:
        return f"Начните с разговора про {differences[0].label.lower()}: здесь ответы разошлись"
    if bands_measured == 0:
        return "Пока нет ни одного сравненного ответа, и процент держится на нейтрали — начните с анкеты"
    return "Похожие ответы нашлись, но назвать их нечем — начните с анкеты"


def build_explanation(
    a: CompatibilityInput,
    b: CompatibilityInput,
    result: CompatibilityResult,
    interest_names: dict[str, str] | None = None,
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
                sim = round(1.0 - abs(va - vb), 3)
                t_label, low_label, high_label = _trait_label(key, trait_key)
                if sim >= STRENGTH_THRESHOLD:
                    side = describe_side((va + vb) / 2, low_label, high_label)
                    strengths.append(
                        ExplanationItem(
                            category=key,
                            label=label,
                            text=f"Похожее отношение: {t_label.lower()} ({side})",
                            score=sim,
                            connection=connection_for(sim),
                        )
                    )
                elif sim <= DIFFERENCE_THRESHOLD:
                    differences.append(
                        ExplanationItem(
                            category=key,
                            label=label,
                            text=f"Разное отношение: {t_label.lower()} — {describe_side(va, low_label, high_label)} vs {describe_side(vb, low_label, high_label)}",
                            score=sim,
                            connection=connection_for(sim),
                        )
                    )
        elif key == "interests":
            if cat_score.score >= STRENGTH_THRESHOLD and (a.interests & b.interests):
                strengths.append(
                    ExplanationItem(
                        category=key,
                        label=label,
                        text="Много общих интересов",
                        score=round(cat_score.score, 3),
                        connection=connection_for(round(cat_score.score, 3)),
                    )
                )
            elif cat_score.score <= DIFFERENCE_THRESHOLD:
                differences.append(
                    ExplanationItem(
                        category=key,
                        label=label,
                        text="Мало общих интересов",
                        score=round(cat_score.score, 3),
                        connection=connection_for(round(cat_score.score, 3)),
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
                        connection=connection_for(round(cat_score.score, 3)),
                    )
                )
            elif cat_score.score <= DIFFERENCE_THRESHOLD and cat_score.has_data:
                differences.append(
                    ExplanationItem(
                        category=key,
                        label=label,
                        text="Разные цели знакомства",
                        score=round(cat_score.score, 3),
                        connection=connection_for(round(cat_score.score, 3)),
                    )
                )

    strengths.sort(key=lambda i: (-i.score, i.category))
    differences.sort(key=lambda i: (i.score, i.category))

    shared = sorted(a.interests & b.interests)
    names = interest_names or {}
    shared_titles = [names.get(slug, slug) for slug in shared]
    kept_strengths = _one_per_category(strengths)
    kept_differences = _one_per_category(differences)

    return CompatibilityExplanation(
        overall_percent=result.overall_percent,
        strengths=kept_strengths,
        differences=kept_differences,
        shared_interests=shared,
        shared_interest_titles=shared_titles,
        bands_measured=result.bands_measured,
        bands_total=result.bands_total,
        measured_weight=result.measured_weight,
        starter=_starter(shared_titles, kept_strengths, kept_differences, result.bands_measured),
    )


def category_labels() -> dict[str, str]:
    return {key: cat.label for key, cat in CATEGORY_BY_KEY.items()}
