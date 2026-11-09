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


class ChallengePurpose(StrEnum):
    """What a one-time code is proof of. The value sits in the redemption predicate, not only in a label.

    A code minted for one purpose must not be redeemable as another, and the cheapest way to make
    that true is to carry the purpose in the same ``WHERE`` clause that decides whether the code is
    alive at all. Adding a purpose later is a new value here and no migration.
    """

    PASSWORD_RESET = "password_reset"
    # The other claim a mailbox can make, and a different one: a reset code says «this person may set
    # the word», a confirmation code says «this address belongs to this account». Sharing one purpose
    # would let a recovery code, asked for to get back in, silently mark an address the account never
    # proved — so the two live apart in the one column the redemption predicate reads.
    EMAIL_CONFIRMATION = "email_confirmation"


class CompatibilityCategory(StrEnum):
    VALUES = "values"
    PERSONALITY = "personality"
    INTERESTS = "interests"
    COMMUNICATION = "communication"
    LIFESTYLE = "lifestyle"
    LEISURE = "leisure"
    GOALS = "goals"
