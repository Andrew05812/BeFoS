from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Paged(BaseModel, Generic[T]):
    """A page you can ask the next page of.

    A cursor, not an offset: the offset of the next card changes the moment the viewer
    likes anything, and a feed that pages by position quietly skips candidates.
    """

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


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


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    password_confirm: str = Field(min_length=8, max_length=128)


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


class SessionCard(BaseModel):
    """One live session of the account reading it.

    `device` is the `User-Agent` string the session arrived with, stored and returned as it came: the
    server does not translate a phone's model or a browser's build into words it found neither. It is
    None for a session that arrived with no header at all, which is a fact worth showing rather than
    a blank to explain. `current` is the row this very access token opened, so a list of devices can
    say which one the reader must not cut off.
    """

    id: str
    device: str | None
    signed_in_at: datetime
    expires_at: datetime
    current: bool


class SessionsPage(BaseModel):
    sessions: list[SessionCard]
    has_more: bool


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
    # The city the deck is filtered by (`discovery_service` hands it to
    # `social_repo._preference_conditions`); None means the person never named one and the deck
    # stays city-unbounded. Only the owner's routes answer it — a public reader has no business
    # learning where somebody searches.
    city_preference: str | None = None
    is_hidden: bool = False
    # Every route answering with this schema is a `/users/me*` route, so the role a reader sees here
    # is the reader's own. It tells the client where to put a door, and opens nothing: the
    # moderation routes read the flag off the account row per request (`app/auth/deps.py:56`).
    is_moderator: bool = False


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
    # No min_length on purpose: the empty string is the answer «снимите фильтр», and a schema
    # that refused it would leave the only way to widen the deck be a field the client cannot
    # send back. Absent means untouched, the same split `about` already lives by.
    city_preference: str | None = Field(default=None, max_length=120)
    is_hidden: bool | None = None


class PhotoOrderUpdate(BaseModel):
    """The whole row of photographs, in the order the owner wants readers to see it.

    A full order rather than a move: `position` and `is_primary` are written from one list, so a
    request naming only the pair being swapped would still have to say where the rest of the row
    stands — and a client that guessed wrong would move a photograph into an order nobody chose.
    """

    photo_ids: list[uuid.UUID] = Field(min_length=1)


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
    # How this question is put to the person: `choice` is the stack of cards below, `scale` says
    # the same ordered options are better set with a thumb. A client that does not know the field
    # keeps working — it renders the cards it has always rendered, and the answer it posts is the
    # same option row either way.
    kind: str = "choice"
    position: int
    options: list[OptionOut] = []
    # The option this person's stored answer stands on, or null where the server holds none.
    # Without it a test left halfway reopens as question one with every card unmarked: the
    # person cannot see what they answered, cannot change one answer, and has to re-tap the
    # questions they already passed to reach the one they had not.
    selected_option_id: int | None = None


class CategoryProgressOut(BaseModel):
    # One category of the catalogue with its Russian label and how much of it the person
    # answered. The screen needs both halves: the label to name the section, and the pair of
    # numbers to say what is still missing — a category nobody answered has to stay in this
    # list with ``answered=0``, because hiding it is how an empty band becomes invisible.
    key: str
    label: str
    total: int
    answered: int


class TestListResponse(BaseModel):
    questions: list[QuestionOut]
    total: int
    answered: int
    categories: list[CategoryProgressOut]


class AnswerIn(BaseModel):
    # Both fields name a PostgreSQL `integer` column. A larger number cannot be a row and
    # cannot be looked up: bound into `WHERE id = $1::INTEGER` the driver refuses it, so a
    # payload naming an impossible id answered with a 500 rather than about itself.
    question_id: int = Field(le=2**31 - 1)
    option_id: int = Field(le=2**31 - 1)


class AnswersIn(BaseModel):
    # A batch is one entry per question: the client posts the whole map when the last question
    # is tapped. The server validates it against the catalog in one read and writes it in one
    # statement, so a body longer than any test can be is refused here instead of reaching the
    # driver as a parameter list it will not hold.
    answers: list[AnswerIn] = Field(max_length=500)


class ProgressOut(BaseModel):
    answered: int
    total: int
    percent: int
    remaining: int
    completed: bool
    # The same sections `GET /api/v1/tests` prints, with the same counts. A screen that has to say
    # which part of the questionnaire is still empty asks this route, not the catalogue one, and it
    # gets the answer without carrying twenty-one question texts and their options over the wire.
    categories: list[CategoryProgressOut] = []


class CategoryScoreOut(BaseModel):
    category: str
    label: str
    # A percent, and the contract the screens are written against: the engine clamps every
    # category into 0..1 and rounds, so anything outside this range is a bug rather than a
    # low score. Declaring it here means the bug fails on the way out instead of showing
    # a user "-3%".
    score: int = Field(ge=0, le=100)
    weight: float
    # Whether anything produced that percent. The engine keeps this flag for its own explanation
    # and a band with nothing to compare on still carries its neutral 50, so a screen handed only
    # the number draws an absent answer exactly like a middling one. Required, with no default: a
    # route that forgets it fails here instead of silently promising "measured".
    has_data: bool


class TraitAxisOut(BaseModel):
    """One axis of the questionnaire, measured from the person's own answers.

    The band percent above it is the average of these, so a screen that shows only the band claims
    «the calculation is transparent» while hiding the twenty-one positions that produced it — and
    until now the only place a person could read their own position on an axis was the compatibility
    map of a pair they might not have yet.
    """

    category: str
    trait: str
    label: str
    # The same 0..1 the engine stores. Bounded like every other number on the wire: an axis outside
    # this range is a bug in the build, not an extreme answer.
    value: float = Field(ge=0, le=1)
    # Which end of the axis that value reads as, in the taxonomy's own words — the same
    # `describe_side` the compatibility explanation and the universe map quote, so a person who
    # finishes the questionnaire and later opens a pair map reads one wording for one answer.
    side: str


class TestResultOut(BaseModel):
    categories: list[CategoryScoreOut]
    axes: list[TraitAxisOut] = []
    completed_at: datetime | None = None


class TestProfileOut(BaseModel):
    """The person's own profile, read back long after the evening it was scored.

    The bands and axes are the same two lists ``POST /tests/complete`` answers with, built by the
    same code, so the screen that opens weeks later cannot show a percent the results screen did.
    What this one adds is ``updated_at`` — the moment the engine last rebuilt the profile from this
    person's answers — because a profile read months later has to say when it spoke from.
    """

    categories: list[CategoryScoreOut]
    axes: list[TraitAxisOut] = []
    updated_at: datetime | None = None


# ---------- Compatibility ----------
class ExplanationItemOut(BaseModel):
    category: str
    label: str
    text: str
    score: float


class CompatibilityOut(BaseModel):
    overall: int = Field(ge=0, le=100)
    engine_version: int
    categories: list[CategoryScoreOut]
    strengths: list[ExplanationItemOut] = []
    differences: list[ExplanationItemOut] = []
    shared_interests: list[str] = []


class UniverseNodeOut(BaseModel):
    key: str
    label: str
    a_value: float | None = Field(default=None, ge=0, le=1)
    b_value: float | None = Field(default=None, ge=0, le=1)
    has_data: bool
    connection: str = Field(pattern=r"^(harmony|complementarity|discussion|unknown)$")
    evidence: str
    # How far this node's similarity sits from the band boundary that decided `connection`. Bounded
    # like every other number on the wire: a node that reported 140 % assurance would be a bug, not
    # a confident answer.
    confidence: int = Field(ge=0, le=100)
    suggestion: str
    # The questionnaire items that measure this axis. Empty for an interest or a goal, which the
    # test does not score — a node with an invented question would claim a basis it does not have.
    questions: list[str] = []


class UniverseLayerOut(BaseModel):
    category: str
    label: str
    score: int = Field(ge=0, le=100)
    weight: float
    has_data: bool
    coverage: float = Field(ge=0, le=1)
    # Mean assurance over the nodes that were actually compared, so a band cannot be confident
    # about answers nobody gave.
    confidence: int = Field(ge=0, le=100)
    nodes: list[UniverseNodeOut] = []


class UniverseOut(BaseModel):
    overall: int = Field(ge=0, le=100)
    engine_version: int
    a_user_id: str
    b_user_id: str
    layers: list[UniverseLayerOut]
    # The same map retold in aggregate-only sentences, so "Our Story" and the share sheet send the
    # pair's shape rather than either person's answers. Built by the engine, never by the client.
    story: list[str] = []


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
    compatibility: int = Field(ge=0, le=100)
    shared_interests_count: int
    highlight: str | None = None


class DiscoveryResponse(Paged[DiscoveryCard]):
    pass


class LikeResponse(BaseModel):
    liked: bool
    match: bool
    match_id: str | None = None
    compatibility: int | None = Field(default=None, ge=0, le=100)


class PassResponse(BaseModel):
    passed: bool


class IncomingLikeCard(BaseModel):
    """One tap, described by the person it points at rather than by the one who made it.

    The percent is the number the tapper's own card carried when they tapped, read out of the like
    row — not a fresh calculation about whether the two still fit. It can be null, and null is not
    zero: a score nobody measured has no business arriving as the bottom of a scale (defect 72-1).

    The same row shape answers both directions of the gesture: ``/discover/liked-me`` lists it for
    the account a tap pointed at, ``/discover/liked`` lists it for the account that made the tap.
    Which of the two a reader holds is named by the envelope, not by a field — the server would have
    to invent an answer to say "incoming" here — so the class keeps its original name and this note
    says what it covers.
    """

    user_id: str
    name: str
    age: int
    city: str
    photo_url: str | None
    compatibility: int | None = Field(default=None, ge=0, le=100)
    liked_at: datetime


class LikedMeResponse(BaseModel):
    """The newest ``LIKED_ME_SHOWN`` taps, and whether the account holds more than those."""

    likes: list[IncomingLikeCard]
    has_more: bool


class LikedUsersResponse(BaseModel):
    """The newest ``LIKED_SHOWN`` taps the account made, and whether more stand behind them.

    The card shape is the inbox's, and so is its honesty: the percent is the number the reader was
    shown when they tapped, read off the like row, and null stays null. The undo route answers with
    this same shape, so the screen that withdrew a tap paints the list the server actually holds.
    """

    likes: list[IncomingLikeCard]
    has_more: bool


class PassedUserSummary(BaseModel):
    """One person this account dismissed, and the moment the card was swiped past.

    The same projection the blocked list and the inbox are built from — a name, an age, a city, the
    leading photograph — and no compatibility number. A pass carries no score, and inventing one for
    a gesture that refused the person would be a number about nothing.
    """

    user_id: str
    name: str
    age: int
    city: str
    photo_url: str | None
    passed_at: datetime


class PassedUsersResponse(BaseModel):
    """The newest ``PASSED_SHOWN`` answers of the account's own, and whether more stand behind them.

    The undo route answers with this same shape: the screen that asked has to paint the list the
    server actually holds after the row went, the way unblocking paints the blocked list.
    """

    passed: list[PassedUserSummary]
    has_more: bool


# ---------- Matches ----------
class MatchSummary(BaseModel):
    match_id: str
    user_id: str
    name: str
    age: int
    city: str
    photo_url: str | None
    compatibility: int = Field(ge=0, le=100)
    last_message: str | None
    last_message_at: datetime | None
    unread: int
    created_at: datetime


class MatchListResponse(BaseModel):
    matches: list[MatchSummary]


# ---------- Chat ----------
class MessagePlan(BaseModel):
    """The pair's plan a journal line records, as fields rather than as a sentence.

    `activity_title` comes from the catalogue at read time, so a card that names an idea shows the
    name the idea has now; `body` keeps the sentence the line was born with for a client that draws
    only text. `activity_id` is absent when the card has left the catalogue: the line stays in the
    conversation, its tap target does not. `is_latest` says this is the newest word the pair wrote
    about this idea — an agreement that is not the newest word has been cancelled by a later line,
    possibly one the viewer has not loaded yet.
    """

    activity_id: int | None
    activity_title: str | None
    when: datetime | None
    # The arrangement the line records. A pair can talk the same idea over more than once, and a card
    # that opens the plan's details has to name which one; absent for a line the plan entity never
    # wrote.
    plan_id: str | None
    is_latest: bool


class MessageOut(BaseModel):
    id: str
    match_id: str
    sender_id: str
    body: str
    created_at: datetime
    is_read: bool
    is_own: bool
    client_msg_id: str | None = None
    # `text` for anything a person typed; a plan kind for a line the pair's plan wrote. Sent as
    # text because a client groups bubbles by author, and a plan line has an actor but no author.
    kind: str = "text"
    plan: MessagePlan | None = None


class MessageIn(BaseModel):
    # The envelope a schema violation produces names no field and no limit, which is
    # useless to someone whose message was simply too long, so the length rule lives in
    # ChatService.send with its own message; this bound only stops an absurd payload.
    body: str = Field(min_length=1, max_length=20_000)
    # The client's own name for the send, which lets a retry of a request whose response
    # was lost reuse it instead of writing a second copy. 64 is the column width, so an
    # over-long id is a 422 on input rather than a database error.
    client_msg_id: str | None = Field(default=None, max_length=64)


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
    score: int = Field(ge=0, le=100)
    position: int
    reasons: list[str]
    # Whether the person reading this page already chose this card for this pair. Per viewer:
    # the pair shares one stored page, and a card one half used is not a card the other used.
    selected: bool
    # Whether the other half of the pair chose it. A card can be agreed on twice over or picked
    # by one side only, and the page has to say which — the stored row is not secret, it is the
    # proposal that already went into the pair's chat.
    partner_selected: bool
    # Whether the person reading this page pushed the card away. Per viewer, like `selected`, and
    # deliberately never answered for the other half: a proposal is a message the pair received,
    # a refusal is one person editing their own list.
    declined: bool
    # The last verb of a plan: when. Each half names the moment they would meet, and answers the
    # other half's name — so all four are per viewer, like `selected`, and the same instant read
    # from the other side of the pair swaps `my_…` with `partner_…`. They are instants with an
    # offset, not wall clocks: a pair in Казань and Новосибирск has to meet at one moment, and each
    # of them reads it on their own clock.
    my_meeting_time: str | None = None
    partner_meeting_time: str | None = None
    i_accepted_time: str | None = None
    # Filled only when one instant is one half's name and the other's answer. Two of them, each
    # agreed to by the other side, is a pair that talked past itself, and this stays empty.
    agreed_time: str | None = None


class MeetingTimeIn(BaseModel):
    """The moment a person names for a card, or the one they agree to."""

    when: AwareDatetime


# ---------- Shared plans ----------
class PlanOut(BaseModel):
    """One arrangement of the pair, as both halves of it see it.

    The shared fields are shared: `note` and `place` are what the pair wrote about the arrangement, so
    each of them reads the same words. A person's own remark is not here — it is `my_note` of the
    detail read, because a note about one's own plan is not a fact about the pair. The two `*_decision`
    and `*_attended` pairs are the same kind of answer seen from either side, and the four flags at the
    end are the screen's questions answered once rather than re-derived by each client: which bucket the
    card belongs to, whether it is the viewer who is being asked, and whether the tap they are about to
    make is allowed.
    """

    id: str
    match_id: str
    activity_id: int
    # Absent when the idea has left the catalogue: the plan keeps its own title and its history, and
    # the deep link that needs the slug simply is not offered.
    activity_slug: str | None
    activity_category: str | None
    title: str
    description: str | None
    note: str | None
    place: str | None
    status: str = Field(
        description=(
            "proposed | accepted | planned | rescheduled | completed | declined | cancelled — "
            "read off what the pair has said, never stored ahead of it"
        )
    )
    starts_at: datetime | None
    pending_hour: datetime | None
    pending_by: str | None
    created_by: str
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    my_decision: str = Field(
        description=(
            "pending | joined | declined — this person's own answer, which the partner's tap never "
            "moves and their own tap may always take back while the plan is open"
        )
    )
    i_attended: bool
    partner_id: str | None
    partner_name: str | None
    partner_photo_url: str | None
    partner_decision: str = Field(
        description="the same three words read off the other half's row, or pending while they have said nothing"
    )
    partner_attended: bool
    hour_passed: bool
    needs_my_answer: bool = Field(
        description=(
            "true while this person is the one the plan waits on: their own word is missing, or the "
            "hour being asked about is one the other half named"
        )
    )
    can_cancel: bool


class PlanListResponse(BaseModel):
    plans: list[PlanOut]


class PlanDetailResponse(BaseModel):
    plan: PlanOut
    my_note: str | None
    events: list[MessageOut]


class PlanEditIn(BaseModel):
    """What the pair writes about the arrangement: where, and their own word about it.

    The hour is not among these fields, and that is not an omission: an hour the pair stands on is the
    other half's answer as much as this person's, so it moves through the hour routes and waits for
    that answer again.
    """

    place: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=500)
    my_note: str | None = Field(default=None, max_length=500)
    # A field that is absent says nothing, so it cannot clear what is already written; these two say
    # it on purpose, and a client that wants the place gone has to be able to ask.
    clear_place: bool = False
    clear_note: bool = False


class PlanPersonalNoteIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class RecommendationListResponse(BaseModel):
    match_id: str
    recommendations: list[RecommendationOut]


# ---------- Safety ----------
class BlockedUserSummary(BaseModel):
    """One row of the list the owner built by blocking people: who they blocked, and when.

    The card holds what a person recognises — a name, an age, a city, the leading photograph —
    and the moment the block was placed, because the list is ordered by it. Interests, the
    questionnaire and the lifestyle answers appear nowhere on it and are not read for it.
    """

    user_id: str
    name: str
    age: int
    city: str
    photo_url: str | None
    blocked_at: datetime


class BlockedUsersResponse(BaseModel):
    blocked: list[BlockedUserSummary]


# ---------- Moderation ----------
class ReportedAccountSummary(BaseModel):
    """Whom the complaint names, and only what a decision is made on.

    The questionnaire, the photographs and the email address are absent because the reviewer has no
    use for them at this point: the row they are about to close says who is accused, whether that
    account is still visible to anybody, and whether it already holds the privilege they are about
    to use against it.
    """

    user_id: str
    name: str | None
    age: int | None
    city: str | None
    is_deleted: bool
    is_hidden: bool
    is_moderator: bool


class ReporterSummary(BaseModel):
    user_id: str
    name: str | None


class ReportReviewRow(BaseModel):
    """One move of one complaint, with the hand that moved it and the note it left."""

    id: str
    moderator_id: str
    moderator_name: str | None
    from_status: str
    to_status: str
    comment: str | None
    decided_at: datetime


class ReportCard(BaseModel):
    id: str
    reason: str
    details: str | None
    status: str
    created_at: datetime
    reported: ReportedAccountSummary
    reporter: ReporterSummary


class ReportsPage(BaseModel):
    reports: list[ReportCard]
    next_cursor: str | None
    has_more: bool


class ReportDetail(ReportCard):
    updated_at: datetime
    reviews: list[ReportReviewRow]
    # The statuses this complaint may still be moved to, read off the same table the write route
    # checks it against. A client drawing its own list of buttons would drift from that table the
    # first time a transition is added or closed off, and the drift shows up as a tap that can only
    # ever be refused.
    allowed_next_statuses: list[str] = []


class ReviewIn(BaseModel):
    """The status a complaint is moved to and the comment recorded with it.

    The moderator is not in this body: the row that writes history takes the hand from the session
    that authenticated, so a payload naming somebody else changes nothing about whose name ends up
    on the line.
    """

    status: str = Field(min_length=2, max_length=20)
    comment: str | None = Field(default=None, max_length=1000)


class ReviewResult(BaseModel):
    id: str
    status: str
    updated_at: datetime


AuthResponse.model_rebuild()
