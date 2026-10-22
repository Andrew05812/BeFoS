"""The account's own rows, gathered into one document the owner can hand over (stage 121).

`delete_account` is the most final thing this product does: it anonymises the profile, deletes the
photographs and the files behind them, drops the questionnaire answers, the scored profile, the
activity preferences and the deck, purges the social graph and revokes every session
(`backend/app/services/safety_service.py:155-212`). The door that hands a person their own rows back
before that tap stood nowhere in the route table, so the choice the settings screen offers —
«Аккаунт удалится сразу. Восстановить его не получится» — was a choice between staying and losing,
with no third option of leaving with what one wrote.

Three rules hold this service together.

**Nothing is re-derived.** Every section is either a row read straight out of the table that owns it
or the answer of the service that already answers it on screen — `MatchesService.list_matches`,
`SafetyService.list_blocked`, `AuthService.own_sessions`, `PlanService.list_for_viewer` and
`TestService.stored_profile`. A file that recomputed a percent, an age or a status would be a second
story about the same person, and the two would drift the first time one of them was fixed. Where the
door prints a rendering, the file carries the stored number and says so in its format name: the
percent the results screen shows is `round(score * 100)` of the float in `test_results`, and a
document meant to outlive the app should outlive its rounding too.

**Nothing secret travels.** No password hash, no token material of any kind, no moderator's identity
or comment on a complaint. The pair's conversation is in it because both halves wrote it and either
can read it on screen; the other half's private remark on a plan (`my_note` of the detail read) is
not, because that field belongs to one person and the reader is not that person.

**Nothing is written.** This is a read, and it reads through plain statements rather than through
`ChatService.history`, which marks the backlog read on the way out — pulling one's own file in the
background must not quietly empty the partner's unread badge. The ceiling is a property of this
document (`ROWS_PER_SECTION`); a section that hits it is named in `limits.truncated`, and `counts`
keeps answering with the rows that stand, so a cut never looks like a complete list.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models import (
    PHOTO_DISPLAY_ORDER,
    CompatibilityProfile,
    DiscoveryQueue,
    Like,
    Match,
    Message,
    Pass,
    Photo,
    Report,
    ReportReview,
    TestAnswer,
    User,
)
from app.models.base import utcnow
from app.repositories.user_repo import UserRepository
from app.services.auth_service import AuthService
from app.services.matches_service import MatchesService
from app.services.plan_service import PlanService
from app.services.safety_service import SafetyService
from app.services.test_service import TestService

# How the person reads the document: which app wrote it, and in what shape its numbers arrived.
EXPORT_FORMAT = "befos.account-export/1"

# Rows a single section carries. A file is written once and may be forwarded, so an unbounded read is
# not a safer one — it is only a less predictable one.
ROWS_PER_SECTION = 500


class ExportService:
    """Gathers one account's own rows into one JSON-ready document."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.profiles = UserRepository(session)
        self.matches = MatchesService(session)
        self.safety = SafetyService(session)
        self.auth = AuthService(session)
        self.plans = PlanService(session)
        self.tests = TestService(session)
        # Names of the sections this document had to cut, and the rows that actually stand behind
        # them. Both live per document: a service instance answers one request, and a ceiling named
        # on one account has no business being remembered for the next.
        self.truncated: list[str] = []
        self.true_counts: dict[str, int] = {}

    async def build(self, user: User, current_session_id: uuid.UUID | None) -> dict[str, Any]:
        """The whole document of one account, in the order a person recognises their own life.

        `current_session_id` is passed to the sessions section unchanged: which row this very token
        stands on is a fact about the request rather than about the account, and a file that loses it
        cannot tell the reader which device they are holding.
        """
        profile = await self.profiles.get_profile(user.id)
        pairs = await self.matches.list_matches(user.id)
        questionnaire = await self._questionnaire(user.id)
        taps = await self._taps(user.id)

        document: dict[str, Any] = {
            "format": EXPORT_FORMAT,
            "generated_at": utcnow(),
            "account": self._account(user),
            "profile": self._profile(profile),
            "photos": await self._photos(user.id),
            "questionnaire": questionnaire,
            "taps": taps,
            "deck": await self._deck(user.id),
            "pairs": pairs,
            "chats": await self._chats(user.id, pairs),
            "plans": await self._plans(user.id),
            "blocks": await self._blocks(user.id),
            "complaints": await self._complaints(user.id),
            "sessions": await self._sessions(user, current_session_id),
        }
        document["counts"] = self._counts(document)
        document["limits"] = {
            "rows_per_section": ROWS_PER_SECTION,
            "truncated": sorted(set(self.truncated)),
        }
        return document

    # ---------- the sections, in the order the app already shows them ----------

    @staticmethod
    def _account(user: User) -> dict[str, Any]:
        return {
            "user_id": str(user.id),
            "email": user.email,
            "is_active": user.is_active,
            "is_moderator": bool(user.is_moderator),
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    @staticmethod
    def _profile(profile) -> dict[str, Any] | None:
        """The questionnaire row as the profile door answers it, plus the date it was born with.

        `age` is the door's derived number and `birth_date` is the stored one. Both are here because
        a file read in five years cannot be expected to recompute an age with whatever calendar the
        server holds then — the date is the row, the age is today's opinion about it.
        """
        if profile is None:
            return None
        return {
            "name": profile.name,
            "birth_date": profile.birth_date,
            "age": profile.age,
            "gender": profile.gender,
            "city": profile.city,
            "about": profile.about,
            "dating_goal": profile.dating_goal,
            "age_min": profile.age_min,
            "age_max": profile.age_max,
            "gender_preference": list(profile.gender_preference or []),
            "city_preference": profile.city_preference,
            "lifestyle": dict(profile.lifestyle or {}),
            "is_hidden": profile.is_hidden,
            "onboarding_completed_at": profile.onboarding_completed_at,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
            "interests": [
                {"slug": i.slug, "name": i.name, "category": i.category}
                for i in profile.interests
            ],
        }

    async def _photos(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        return await self._section(
            "photos",
            select(Photo).where(Photo.user_id == user_id).order_by(*PHOTO_DISPLAY_ORDER),
            lambda p: {
                "id": str(p.id),
                "url": p.url,
                "is_primary": p.is_primary,
                "position": p.position,
                "created_at": p.created_at,
            },
        )

    async def _questionnaire(self, user_id: uuid.UUID) -> dict[str, Any]:
        """The answers as they were stored, and the profile the engine built out of them."""
        answers = await self._section(
            "questionnaire_answers",
            (
                select(TestAnswer)
                .where(TestAnswer.user_id == user_id)
                .order_by(TestAnswer.created_at, TestAnswer.id)
            ),
            lambda a: {
                "question_id": a.question_id,
                "category": a.question.category,
                "trait": a.question.trait,
                "question": a.question.text,
                "option_id": a.option_id,
                "option": a.option.text,
                "value": a.option.value,
                "answered_at": a.created_at,
            },
        )
        stored = await self.tests.stored_profile(user_id)
        categories: list[dict[str, Any]] = []
        compatibility: dict[str, Any] | None = None
        if stored is not None:
            categories = [
                {"category": key, "score": value} for key, value in sorted(stored["scores"].items())
            ]
            compatibility = {
                "vector": stored["vector"],
                "updated_at": stored["updated_at"],
                "version": await self._profile_version(user_id),
            }
        return {"answers": answers, "categories": categories, "compatibility": compatibility}

    async def _profile_version(self, user_id: uuid.UUID) -> int | None:
        """Which run of the engine the stored vector came from.

        `stored_profile` quotes the numbers it was built to show and leaves the version out, and a
        file is exactly where a version earns its keep: it says which model scored the axes of this
        document, and that model changes (stages 82 and 88 moved one each).
        """
        return await self.session.scalar(
            select(CompatibilityProfile.version).where(CompatibilityProfile.user_id == user_id)
        )

    async def _taps(self, user_id: uuid.UUID) -> dict[str, Any]:
        given = await self._section(
            "taps_given",
            select(Like).where(Like.from_user_id == user_id).order_by(Like.created_at, Like.id),
            lambda r: {
                "user_id": str(r.to_user_id),
                "compatibility": r.compatibility_score,
                "tapped_at": r.created_at,
            },
        )
        received = await self._section(
            "taps_received",
            select(Like).where(Like.to_user_id == user_id).order_by(Like.created_at, Like.id),
            lambda r: {
                "user_id": str(r.from_user_id),
                "compatibility": r.compatibility_score,
                "tapped_at": r.created_at,
            },
        )
        passed = await self._section(
            "taps_passed",
            select(Pass).where(Pass.from_user_id == user_id).order_by(Pass.created_at, Pass.id),
            lambda r: {"user_id": str(r.to_user_id), "passed_at": r.created_at},
        )
        return {"given": given, "received": received, "passed": passed}

    async def _deck(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        return await self._section(
            "deck",
            (
                select(DiscoveryQueue)
                .where(DiscoveryQueue.viewer_id == user_id)
                .order_by(DiscoveryQueue.rank, DiscoveryQueue.candidate_id)
            ),
            lambda r: {
                "candidate_id": str(r.candidate_id),
                "rank": r.rank,
                "score": r.score,
                "status": r.status,
                "queued_at": r.queued_at,
                "seen_at": r.seen_at,
            },
        )

    async def _chats(self, user_id: uuid.UUID, pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """One entry per pair, oldest line first — the order a transcript is read in.

        Both halves' lines are here: a conversation belongs to the two who wrote it, and every line
        of it stands on this person's screen already. `is_own` says who wrote it, so nobody has to
        match the file against a pair list to find that out.

        The ceiling belongs to a pair rather than to the whole section, which is the difference
        between a file and a page: a person with one long conversation must not lose it because ten
        short ones filled the count.
        """
        if not pairs:
            return []
        ids = [uuid.UUID(pair["match_id"]) for pair in pairs]
        held = await self.session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.match_id.in_(ids))
        )
        sections: list[dict[str, Any]] = []
        for pair in pairs:
            match_id = uuid.UUID(pair["match_id"])
            rows = await self._section(
                "chats",
                (
                    select(Message)
                    .where(Message.match_id == match_id)
                    .order_by(Message.created_at, Message.id)
                ),
                lambda m: {
                    "id": str(m.id),
                    "sender_id": str(m.sender_id),
                    "is_own": m.sender_id == user_id,
                    "kind": m.kind,
                    "body": m.body,
                    "plan_id": str(m.plan_id) if m.plan_id else None,
                    "created_at": m.created_at,
                    "recalled": m.is_deleted,
                },
            )
            sections.append(
                {
                    "match_id": pair["match_id"],
                    "partner": {"user_id": pair["user_id"], "name": pair["name"]},
                    "lines": rows,
                }
            )
        # The count of a capped section is the number of lines that stand, not the number the file
        # was allowed to carry — otherwise `counts` would agree with the cut and disagree with the
        # database. One count for all the pairs, asked once, replaces the per-pair sums that
        # truncation would otherwise hide.
        if "chats" in self.truncated and held is not None:
            self.true_counts["chats"] = int(held)
        return sections

    async def _plans(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """Every arrangement this person is in, with the words the pair wrote about it.

        The list door owns the shared fields; the detail door owns this person's own remark and the
        lines the chat holds about the plan. Both are asked here rather than reconstructed, so the
        file and the screen of «Наши планы» cannot tell two stories about one agreement — and
        `my_note` of the detail arrives as the reader's own, which is the only private remark in the
        document.
        """
        rows = await self.plans.list_for_viewer(user_id)
        if len(rows) > ROWS_PER_SECTION:
            self.truncated.append("plans")
        out: list[dict[str, Any]] = []
        for row in rows[:ROWS_PER_SECTION]:
            detail = await self.plans.detail(uuid.UUID(row["id"]), user_id)
            out.append(
                {
                    **row,
                    "my_note": detail["my_note"],
                    "journal": [
                        {
                            "id": str(event["id"]),
                            "sender_id": str(event["sender_id"]),
                            "kind": event["kind"],
                            "body": event["body"],
                            "created_at": event["created_at"],
                        }
                        for event in detail["events"]
                    ],
                }
            )
        return out

    async def _blocks(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """The blocked list as its own screen answers it, capped and named like the rest.

        The rows come from the service rather than from `blocks`, because the door decides which
        people are still showable — a file that listed a person the screen hides would be a second
        answer about the same row.
        """
        rows = await self.safety.list_blocked(user_id)
        if len(rows) > ROWS_PER_SECTION:
            self.truncated.append("blocks")
            self.true_counts["blocks"] = len(rows)
        return [dict(row) for row in rows[:ROWS_PER_SECTION]]

    async def _complaints(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """What this account filed, and how far the queue got with it.

        The status arrives because the reporter is owed to know whether anything happened; the
        moderator's identity and their comment do not, because that text was written for the queue
        and about a third person.
        """
        rows = await self._section(
            "complaints",
            (
                select(Report)
                .where(Report.reporter_id == user_id)
                .order_by(Report.created_at, Report.id)
            ),
            lambda r: {
                "id": str(r.id),
                "reported_user_id": str(r.reported_id),
                "reason": r.reason,
                "details": r.details,
                "status": r.status,
                "filed_at": r.created_at,
            },
        )
        # One review per legal move of a complaint, and a complaint takes at most a handful of moves,
        # so the join over the owner's own complaints is bounded by the ceiling above rather than by
        # a second one of its own.
        decided = list(
            (
                await self.session.execute(
                    select(ReportReview)
                    .join(Report, Report.id == ReportReview.report_id)
                    .where(Report.reporter_id == user_id)
                    .order_by(ReportReview.created_at, ReportReview.id)
                )
            )
            .scalars()
            .all()
        )
        history: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for review in decided:
            history.setdefault(review.report_id, []).append(
                {
                    "from_status": review.from_status,
                    "to_status": review.to_status,
                    "moved_at": review.created_at,
                }
            )
        for row in rows:
            row["history"] = history.get(uuid.UUID(row["id"]), [])
        return rows

    async def _sessions(
        self, user: User, current_session_id: uuid.UUID | None
    ) -> list[dict[str, Any]]:
        owned = await self.auth.own_sessions(user, current_session_id)
        if owned["has_more"]:
            self.truncated.append("sessions")
        return owned["sessions"]

    # ---------- the plumbing that keeps the promises above ----------

    async def _section(self, name: str, statement: Select, shape: Callable[[Any], dict]) -> list[dict]:
        """Read one collection, carry at most the ceiling of it, and name a cut when there was one.

        The window is one row wider than the ceiling: that row is what tells a cut apart from a
        complete list without a second query on the path that does not need one.
        """
        rows = list(
            (
                await self.session.execute(statement.limit(ROWS_PER_SECTION + 1))
            )
            .scalars()
            .all()
        )
        if len(rows) > ROWS_PER_SECTION:
            self.truncated.append(name)
            total = await self.session.scalar(
                select(func.count()).select_from(statement.order_by(None).limit(None).subquery())
            )
            if total is not None:
                self.true_counts[name] = int(total)
            return [shape(row) for row in rows[:ROWS_PER_SECTION]]
        return [shape(row) for row in rows]

    def _counts(self, document: dict[str, Any]) -> dict[str, int]:
        """How many rows stand behind each section — not how many the ceiling let through.

        A file whose own summary agreed with its cut would be the one kind of lie a document can
        tell about itself.
        """
        taps = document["taps"]
        questionnaire = document["questionnaire"]
        counts = {
            "photos": len(document["photos"]),
            "questionnaire_answers": len(questionnaire["answers"]),
            "questionnaire_categories": len(questionnaire["categories"]),
            "taps_given": len(taps["given"]),
            "taps_received": len(taps["received"]),
            "taps_passed": len(taps["passed"]),
            "deck": len(document["deck"]),
            "pairs": len(document["pairs"]),
            "chats": sum(len(entry["lines"]) for entry in document["chats"]),
            "plans": len(document["plans"]),
            "blocks": len(document["blocks"]),
            "complaints": len(document["complaints"]),
            "sessions": len(document["sessions"]),
        }
        counts.update(self.true_counts)
        return counts
