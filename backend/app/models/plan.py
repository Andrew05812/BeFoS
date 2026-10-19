from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin

# The states a pair's plan moves through. Named here rather than in an `enum` column because the
# sibling status columns in this schema (`reports.status`, `discovery_queue.status`) are strings with
# a CHECK, and a plan's status is read by the same kind of query — a bucket filter, not a join.
STATUS_PROPOSED = "proposed"
STATUS_ACCEPTED = "accepted"
STATUS_PLANNED = "planned"
STATUS_RESCHEDULED = "rescheduled"
STATUS_COMPLETED = "completed"
STATUS_DECLINED = "declined"
STATUS_CANCELLED = "cancelled"
PLAN_STATUSES = (
    STATUS_PROPOSED,
    STATUS_ACCEPTED,
    STATUS_PLANNED,
    STATUS_RESCHEDULED,
    STATUS_COMPLETED,
    STATUS_DECLINED,
    STATUS_CANCELLED,
)

# What one person says about the idea. `pending` is the state of a half that has not answered yet,
# and it is a state rather than an absent row: the pair's plan is about two named people, so both of
# them are asked, and "has not answered" is what the card has to say about one of them.
DECISION_PENDING = "pending"
DECISION_JOINED = "joined"
DECISION_DECLINED = "declined"
PLAN_DECISIONS = (DECISION_PENDING, DECISION_JOINED, DECISION_DECLINED)


class SharedPlan(TimestampMixin, Base):
    """The one thing a pair arranges: an idea, the two of them, and what they decided about it.

    Until now the pair's plan had no name of its own. It was the composite `(match_id, activity_id)`
    read out of two `activity_preferences` rows, and the conversation kept its own copy of the
    outcome as journal lines — so a screen that wanted "our plans" had no row to point at, a
    reschedule had nothing to hold the new hour, and completion had nowhere to be recorded at all.
    This row is that name: every subsystem that speaks of a plan now speaks of one id.

    The hour it carries is a projection, not a second negotiator. `starts_at` holds the instant the
    pair stands on — the one their two rows agree on — and `pending_hour` holds the single instant one
    of them has named and the other has not confirmed. `app.services.plan_time.agreed_instant` remains
    the only rule that decides whether an instant is agreed, and `PlanService.sync_pair` re-reads the
    rows on every read of the pair, so the plan cannot drift ahead of them.

    `was_planned` is the one fact the rows cannot say: whether this pair ever stood on an hour.
    Without it "the hour is up for a move" and "an hour is being offered for the first time" are the
    same state to the card, and the first of them is the one a person needs to be warned about.
    `pending_hour` and `pending_by` are the second, and they are the same pair of questions: the rows
    of a pair whose standing evening has just been moved hold two different instants, which is exactly
    what a pair talking past each other holds too, and no reading of the rows tells the two apart. So
    the verb that moves an hour writes the question it is asking onto the plan, and the projection keeps
    that record only while the row of the person who asked it still names that instant — see
    `PlanService._ask_of` and `PlanService._record_ask`. A pair that has never settled on an hour still
    gets its question out of the rows alone.

    `note` and `place` belong to the plan rather than to the activity because they are what the two
    of them add to it, and both stay NULL until somebody says them: an idea from the catalogue has
    no address, and inventing one would put a place in a pair's plan that no conversation named.
    """

    __tablename__ = "shared_plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(
        # uq_shared_plan_pair_activity already covers match_id as its leading column.
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    activity_id: Mapped[int] = mapped_column(
        # CASCADE, the way `recommendations` and `activity_preferences` treat the catalogue: a card
        # leaving it takes the pair's *plan* with it, because a plan is that card arranged. The
        # conversation keeps its own line — `messages.plan_activity_id` is SET NULL — so what the
        # pair was said is not rewritten by what the catalogue did afterwards.
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # The idea's own name at the moment the pair took it up. Held here rather than always joined out
    # of the catalogue because the list of plans reads across every pair the viewer is in: the join
    # would be paid per card, and a rename is a thing the pair's plan should not silently acquire.
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    place: Mapped[str | None] = mapped_column(String(200), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pending_hour: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Who is being asked about the pending hour. NULL with a pending hour set means both of them
    # named the same instant without either confirming the other's — a pair that is one tap from an
    # agreement and has not reached it, which is not the same thing as one of them asking.
    pending_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default=STATUS_PROPOSED, server_default=STATUS_PROPOSED, nullable=False
    )
    was_planned: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    # Terminal, plan-owned state: nothing in the preference rows says "we called it off", so this is
    # the column the record of that lands in. Either half may set it and the same half takes the plan
    # back, which is why the actor is named alongside the instant. Whether the meeting happened is
    # not here: it is `attended_at` on each member's row, because it is one answer per person.
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )

    members: Mapped[list["SharedPlanMember"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # The composite the plan replaces as the identity of a pair's arrangement: one row per pair
        # per idea. This is what keeps a re-opened idea from becoming a second copy of a plan the
        # pair already has.
        UniqueConstraint("match_id", "activity_id", name="uq_shared_plan_pair_activity"),
        CheckConstraint(
            "status in ('proposed', 'accepted', 'planned', 'rescheduled', 'completed', "
            "'declined', 'cancelled')",
            name="ck_shared_plan_status",
        ),
        # The bucket read: the plans of one pair by state, and the list of every plan of one viewer
        # ordered by what is coming up.
        Index("ix_shared_plan_match_status", "match_id", "status"),
        Index("ix_shared_plan_start", "status", "starts_at"),
    )


class SharedPlanMember(TimestampMixin, Base):
    """One half of the pair's own answer about one plan.

    Two rows per plan, both written when the plan is born, because the questions this table answers
    are asked about a person who has not answered yet: «ждёт подтверждения» is a state of the pair
    and has to name which half is being asked.

    `decision` mirrors what the preference rows already record — proposed, or pushed away, or
    neither — and is kept here so the pair's plan can be read without reading the whole card page.
    `personal_note` is the one thing that is not shared: a person's own remark about a meeting they
    agreed to. It is read back only to its author (see `PlanService.detail`), which is what makes
    storing it safe rather than a leak into the other half's screen.
    """

    __tablename__ = "shared_plan_members"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        # uq_shared_plan_member already covers plan_id as its leading column.
        ForeignKey("shared_plans.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(
        String(16), default=DECISION_PENDING, server_default=DECISION_PENDING, nullable=False
    )
    # This half's own word that the meeting happened. The plan reaches `completed` only when both
    # rows carry it, because a meeting one of them was at and the other knows nothing about is not a
    # meeting the pair had — and nothing here sets it on the hour passing, so the clock cannot put a
    # met-in-person claim into the pair's journal.
    attended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    personal_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped["SharedPlan"] = relationship(back_populates="members")

    __table_args__ = (
        UniqueConstraint("plan_id", "user_id", name="uq_shared_plan_member"),
        CheckConstraint(
            "decision in ('pending', 'joined', 'declined')", name="ck_shared_plan_member_decision"
        ),
    )
