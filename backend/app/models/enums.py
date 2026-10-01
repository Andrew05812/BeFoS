from __future__ import annotations

import enum


class StrEnum(str, enum.Enum):
    """String enum that serialises cleanly in both SQLAlchemy and Pydantic."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    NONBINARY = "nonbinary"
    OTHER = "other"


class DatingGoal(StrEnum):
    RELATIONSHIP = "relationship"
    MARRIAGE = "marriage"
    FRIENDSHIP = "friendship"
    CASUAL = "casual"
    NETWORKING = "networking"


class InterestCategory(StrEnum):
    ART = "art"
    SPORT = "sport"
    MUSIC = "music"
    TRAVEL = "travel"
    FOOD = "food"
    TECH = "tech"
    NATURE = "nature"
    GAMES = "games"
    LEARNING = "learning"
    SOCIAL = "social"


class ReportStatus(StrEnum):
    OPEN = "open"
    REVIEWED = "reviewed"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class CompatibilityCategory(StrEnum):
    VALUES = "values"
    PERSONALITY = "personality"
    INTERESTS = "interests"
    COMMUNICATION = "communication"
    LIFESTYLE = "lifestyle"
    LEISURE = "leisure"
    GOALS = "goals"
