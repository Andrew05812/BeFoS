"""ORM models package.

Importing every model module here ensures all mappers are registered on the
shared ``Base.metadata`` so Alembic autogenerate and relationship resolution
work correctly.
"""

from app.core.database import Base
from app.models.base import TimestampMixin, utcnow
from app.models.enums import (
    CompatibilityCategory,
    DatingGoal,
    Gender,
    InterestCategory,
    ReportStatus,
)
from app.models.user import Interest, Photo, Profile, User, UserInterest
from app.models.test import (
    CompatibilityProfile,
    TestAnswer,
    TestOption,
    TestQuestion,
    TestResult,
)
from app.models.social import Block, Like, Match, Pass, Report
from app.models.chat import Message, MessageRead
from app.models.discovery import DiscoveryQueue
from app.models.activity import Activity, ActivityPreference, Recommendation
from app.models.token import RefreshToken

__all__ = [
    "Base",
    "TimestampMixin",
    "utcnow",
    "Gender",
    "DatingGoal",
    "InterestCategory",
    "ReportStatus",
    "CompatibilityCategory",
    "User",
    "Profile",
    "Photo",
    "Interest",
    "UserInterest",
    "TestQuestion",
    "TestOption",
    "TestAnswer",
    "TestResult",
    "CompatibilityProfile",
    "Like",
    "Pass",
    "Match",
    "Block",
    "Report",
    "Message",
    "MessageRead",
    "DiscoveryQueue",
    "Activity",
    "ActivityPreference",
    "Recommendation",
    "RefreshToken",
]
