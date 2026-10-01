from __future__ import annotations

"""Trait taxonomy for the BeFoS Compatibility Engine.

The engine works on a normalised trait vector per user::

    { category: { trait: value_in_0_1 } }

Trait-based categories (values, personality, communication, lifestyle, leisure)
are compared by trait similarity. Two categories are computed from structured
profile data instead of the vector:

* ``interests`` - overlap of the users' interest sets.
* ``goals``     - compatibility of declared dating goals.

Every trait has a human-readable label used when generating explanations, and a
``polarity`` describing whether similarity (``"similar"``) is what matters. All
BeFoS traits currently reward similarity, which keeps the model transparent and
explainable.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Trait:
    key: str
    label: str
    low_label: str
    high_label: str
    polarity: str = "similar"


@dataclass(frozen=True)
class CategoryTraits:
    key: str
    label: str
    traits: tuple[Trait, ...] = field(default_factory=tuple)


VALUES = CategoryTraits(
    key="values",
    label="Ценности",
    traits=(
        Trait("family", "Семья", "карьера важнее семьи", "семья в приоритете"),
        Trait("career", "Карьера", "работа без фанатизма", "амбиции и карьера"),
        Trait("growth", "Развитие", "стабильность", "постоянное саморазвитие"),
        Trait("stability", "Стабильность", "спонтанность", "стабильность и план"),
        Trait("adventure", "Приключения", "домашний уют", "жажда приключений"),
    ),
)

PERSONALITY = CategoryTraits(
    key="personality",
    label="Личность",
    traits=(
        Trait("extraversion", "Общительность", "интроверт", "экстраверт"),
        Trait("openness", "Открытость новому", "консерватизм", "открытость опыту"),
        Trait("planning", "Планирование", "спонтанность", "всё по плану"),
        Trait("optimism", "Оптимизм", "реализм", "оптимизм"),
    ),
)

COMMUNICATION = CategoryTraits(
    key="communication",
    label="Общение",
    traits=(
        Trait("directness", "Прямолинейность", "намёки", "прямо и открыто"),
        Trait("frequency", "Частота общения", "редко на связи", "постоянно на связи"),
        Trait("conflict_style", "Стиль в конфликтах", "избегание", "обсуждение сразу"),
    ),
)

LIFESTYLE = CategoryTraits(
    key="lifestyle",
    label="Образ жизни",
    traits=(
        Trait("activity_level", "Активность", "спокойный ритм", "высокая активность"),
        Trait("sleep_schedule", "Режим дня", "жаворонок", "сова"),
        Trait("health_focus", "Здоровье", "без особого режима", "ЗОЖ и режим"),
        Trait("social_frequency", "Выход в свет", "домосед", "часто в компаниях"),
    ),
)

LEISURE = CategoryTraits(
    key="leisure",
    label="Досуг",
    traits=(
        Trait("outdoor", "Активный отдых", "дома", "на природе/активно"),
        Trait("creative", "Творчество", "практичность", "творчество и искусство"),
        Trait("intellectual", "Интеллектуальный досуг", "развлечение", "книги/лекции/наука"),
        Trait("social_leisure", "Социальный досуг", "один/вдвоём", "в больших компаниях"),
        Trait("relaxation", "Спокойный отдых", "движение", "спокойствие и релакс"),
    ),
)

# Categories that are computed from structured data rather than the trait vector.
INTERESTS = CategoryTraits(key="interests", label="Интересы")
GOALS = CategoryTraits(key="goals", label="Цели знакомства")

TRAIT_CATEGORIES: tuple[CategoryTraits, ...] = (VALUES, PERSONALITY, COMMUNICATION, LIFESTYLE, LEISURE)
ALL_CATEGORIES: tuple[CategoryTraits, ...] = (
    VALUES,
    PERSONALITY,
    INTERESTS,
    COMMUNICATION,
    LIFESTYLE,
    LEISURE,
    GOALS,
)

CATEGORY_BY_KEY: dict[str, CategoryTraits] = {c.key: c for c in ALL_CATEGORIES}
TRAIT_CATEGORIES_BY_KEY: dict[str, CategoryTraits] = {c.key: c for c in TRAIT_CATEGORIES}

# Dating-goal compatibility matrix. Values in 0..1. Symmetric.
# Same goals score 1.0; complementary goals score partial; conflicting score low.
_GOAL_COMPAT: dict[str, dict[str, float]] = {
    "marriage": {"marriage": 1.0, "relationship": 0.85, "friendship": 0.45, "casual": 0.15, "networking": 0.25},
    "relationship": {"relationship": 1.0, "marriage": 0.85, "friendship": 0.55, "casual": 0.3, "networking": 0.3},
    "friendship": {"friendship": 1.0, "networking": 0.6, "relationship": 0.55, "marriage": 0.45, "casual": 0.4},
    "casual": {"casual": 1.0, "friendship": 0.4, "networking": 0.35, "relationship": 0.3, "marriage": 0.15},
    "networking": {"networking": 1.0, "friendship": 0.6, "casual": 0.35, "relationship": 0.3, "marriage": 0.25},
}


def goal_compatibility(goal_a: str, goal_b: str) -> float:
    """Return 0..1 compatibility between two dating goals (deterministic)."""
    table = _GOAL_COMPAT.get(goal_a)
    if not table:
        return 0.0
    return table.get(goal_b, 0.0)
