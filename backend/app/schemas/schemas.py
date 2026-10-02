from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Paginated(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
    has_more: bool


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ---------- Auth ----------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthResponse(BaseModel):
    user: "UserBrief"
    tokens: TokenPair


class UserBrief(ORMModel):
    id: str
    email: EmailStr
    is_active: bool
    created_at: datetime


# ---------- Profile ----------
class InterestOut(ORMModel):
    slug: str
    name: str
    category: str


class PhotoOut(ORMModel):
    id: str
    url: str
    is_primary: bool
    position: int


class ProfileOut(BaseModel):
    user_id: str
    name: str
    age: int
    city: str
    gender: str
    about: str | None
    dating_goal: str
    photos: list[PhotoOut] = []
    interests: list[InterestOut] = []
    lifestyle: dict[str, Any] = {}
    age_min: int
    age_max: int
    gender_preference: list[str] = []


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    city: str | None = Field(default=None, min_length=1, max_length=120)
    about: str | None = Field(default=None, max_length=2000)
    dating_goal: str | None = None
    gender: str | None = None
    birth_date: str | None = None
    interests: list[str] | None = None
    lifestyle: dict[str, Any] | None = None
    age_min: int | None = Field(default=None, ge=18, le=99)
    age_max: int | None = Field(default=None, ge=18, le=99)
    gender_preference: list[str] | None = None
    is_hidden: bool | None = None


class OnboardingProfile(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    birth_date: str
    city: str = Field(min_length=1, max_length=120)
    gender: str
    about: str | None = Field(default=None, max_length=2000)
    dating_goal: str
    interests: list[str] = []
    lifestyle: dict[str, Any] = {}
    age_min: int = Field(default=18, ge=18, le=99)
    age_max: int = Field(default=60, ge=18, le=99)
    gender_preference: list[str] = []


# ---------- Tests ----------
class OptionOut(ORMModel):
    id: int
    text: str
    position: int


class QuestionOut(ORMModel):
    id: int
    category: str
    trait: str
    text: str
    position: int
    options: list[OptionOut] = []


class TestListResponse(BaseModel):
    questions: list[QuestionOut]
    total: int
    answered: int


class AnswerIn(BaseModel):
    question_id: int
    option_id: int


class AnswersIn(BaseModel):
    answers: list[AnswerIn]


class ProgressOut(BaseModel):
    answered: int
    total: int
    percent: int
    remaining: int
    completed: bool


class CategoryScoreOut(BaseModel):
    category: str
    label: str
    score: int  # 0..100
    weight: float


class TestResultOut(BaseModel):
    categories: list[CategoryScoreOut]
    completed_at: datetime | None = None


# ---------- Compatibility ----------
class ExplanationItemOut(BaseModel):
    category: str
    label: str
    text: str
    score: float


class CompatibilityOut(BaseModel):
    overall: int
    engine_version: int
    categories: list[CategoryScoreOut]
    strengths: list[ExplanationItemOut] = []
    differences: list[ExplanationItemOut] = []
    shared_interests: list[str] = []


# ---------- Discovery ----------
class DiscoveryCard(BaseModel):
    user_id: str
    name: str
    age: int
    city: str
    about: str | None
    dating_goal: str
    photo_url: str | None
    interests: list[str] = []
    compatibility: int
    shared_interests_count: int
    highlight: str | None = None


class DiscoveryResponse(Paginated[DiscoveryCard]):
    pass


class LikeResponse(BaseModel):
    liked: bool
    match: bool
    match_id: str | None = None
    compatibility: int | None = None


class PassResponse(BaseModel):
    passed: bool


# ---------- Matches ----------
class MatchSummary(BaseModel):
    match_id: str
    user_id: str
    name: str
    age: int
    city: str
    photo_url: str | None
    compatibility: int
    last_message: str | None
    last_message_at: datetime | None
    unread: int
    created_at: datetime


class MatchListResponse(BaseModel):
    matches: list[MatchSummary]


# ---------- Chat ----------
class MessageOut(BaseModel):
    id: str
    match_id: str
    sender_id: str
    body: str
    created_at: datetime
    is_read: bool
    is_own: bool


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class MessagePage(BaseModel):
    messages: list[MessageOut]
    has_more: bool


# ---------- Activities / Recommendations ----------
class ActivityOut(ORMModel):
    id: int
    slug: str
    title: str
    description: str | None
    category: str
    energy: float
    social: float
    cost: float


class RecommendationOut(BaseModel):
    activity: ActivityOut
    score: int
    position: int
    reasons: list[str]


class RecommendationListResponse(BaseModel):
    match_id: str
    recommendations: list[RecommendationOut]


AuthResponse.model_rebuild()
