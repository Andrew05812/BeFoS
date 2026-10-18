from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models import Report, ReportReview, ReportStatus
from app.models.base import age_years, utc_today
from app.repositories.moderation_repo import ModerationRepository

ALL_STATUSES = frozenset(status.value for status in ReportStatus)
TERMINAL_STATUSES = frozenset({ReportStatus.RESOLVED.value, ReportStatus.DISMISSED.value})

# Which status a complaint may be moved to from the one it holds, and nothing else says so. The
# two closed states are dead ends on purpose: `resolved` and `dismissed` are what a moderator told
# the queue, and a route that reopened them would quietly rewrite a decision the history already
# records. A wrong dismissal is answered by the next complaint about the same person, which arrives
# as its own row and is decided fresh, rather than by a second verdict on the first one.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    ReportStatus.OPEN.value: frozenset(
        {
            ReportStatus.REVIEWED.value,
            ReportStatus.RESOLVED.value,
            ReportStatus.DISMISSED.value,
        }
    ),
    ReportStatus.REVIEWED.value: frozenset(
        {ReportStatus.RESOLVED.value, ReportStatus.DISMISSED.value}
    ),
    ReportStatus.RESOLVED.value: frozenset(),
    ReportStatus.DISMISSED.value: frozenset(),
}

# How far one page of the queue may reach. The route bounds it again, and a caller who asks for
# more than this is told 422 rather than quietly served fewer rows than they asked for.
MAX_PAGE = 100
MAX_COMMENT = 1000


class ModerationService:
    """Reading the complaint queue and closing a complaint, for the one role that may do either.

    The service never learns who may call it: every entry point sits behind `get_moderator`
    (`app/auth/deps.py:56`), which reads the flag off the account row per request. What this class
    does hold is the lifecycle — the transition table above, the comment a closing needs, and the
    rule that the hand which writes a status is the account the route authenticated, never a number
    somebody typed into a body.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.reports = ModerationRepository(session)

    async def list_reports(
        self, *, status: str | None, after_id: uuid.UUID | None, limit: int
    ) -> dict:
        """One page of the queue, oldest first, optionally narrowed to one status."""
        if status is not None and status not in ALL_STATUSES:
            raise ValidationError(f"Invalid report status. Allowed: {sorted(ALL_STATUSES)}.")
        after: tuple | None = None
        if after_id is not None:
            anchor = await self.reports.get_report(after_id)
            # A cursor whose row is gone is not a page boundary but a lie about one, so it is
            # refused by name instead of answered with the queue from the beginning — which would
            # hand the caller the oldest complaints twice and never what it was asking for.
            if anchor is None:
                raise NotFoundError("Report cursor not found.")
            after = (anchor.created_at, anchor.id)
        rows = await self.reports.page(status=status, after=after, limit=limit + 1)
        has_more = len(rows) > limit
        rows = rows[:limit]
        return {
            "reports": await self._cards(rows),
            "next_cursor": str(rows[-1].id) if has_more and rows else None,
            "has_more": has_more,
        }

    async def detail(self, report_id: uuid.UUID) -> dict:
        report = await self.reports.get_report(report_id)
        if report is None:
            raise NotFoundError("Report not found.")
        card = (await self._cards([report]))[0]
        history = await self.reviews_of(report_id)
        return {
            **card,
            "updated_at": report.updated_at,
            "reviews": history,
            # The same table `review` checks the asked-for status against, read out loud so the
            # caller can draw the choices that still exist. A closed complaint answers with an empty
            # list rather than with the statuses it once moved through.
            "allowed_next_statuses": sorted(ALLOWED_TRANSITIONS[report.status]),
        }

    async def reviews_of(self, report_id: uuid.UUID) -> list[dict]:
        """How this complaint got to where it is, in the order it was moved."""
        rows = await self.reports.reviews_of(report_id)
        names = await self.reports.names_of({row.moderator_id for row in rows})
        return [self._review_dto(row, names.get(row.moderator_id)) for row in rows]

    async def review(
        self,
        moderator_id: uuid.UUID,
        report_id: uuid.UUID,
        to_status: str,
        comment: str | None,
    ) -> dict:
        """Move one complaint to one status and write the history row that says it happened.

        The complaint is read `FOR UPDATE`, so a second moderator answering the same row waits and
        then reads the status the first one left — which turns a double tap by two people into one
        decision and one refusal rather than two history rows that contradict each other. The
        status and its history row are written in the same transaction and committed once: a run
        that fails before the commit has changed nothing at all, which is the only way this route
        knows how to keep the promise that no status moved without a row saying who moved it.
        """
        to_status = (to_status or "").strip().lower()
        if to_status not in ALL_STATUSES:
            raise ValidationError(f"Invalid report status. Allowed: {sorted(ALL_STATUSES)}.")
        report = await self.reports.get_report(report_id, for_update=True)
        if report is None:
            raise NotFoundError("Report not found.")
        if report.reported_id == moderator_id:
            # The role says who may decide, not whom they may decide about. Without this the
            # moderation surface is a way for a moderator to close a complaint about themselves
            # from the inside, and no other account would ever see it happen.
            raise ForbiddenError("A moderator cannot decide a complaint about their own account.")
        current = report.status
        if to_status == current:
            raise ConflictError("This complaint already carries that status.")
        if to_status not in ALLOWED_TRANSITIONS[current]:
            raise ValidationError(f"A complaint cannot move from {current} to {to_status}.")
        note = (comment or "").strip() or None
        if to_status in TERMINAL_STATUSES and note is None:
            raise ValidationError(
                "A complaint that is being closed needs a comment saying why."
            )
        if note is not None and len(note) > MAX_COMMENT:
            raise ValidationError(f"That comment is longer than {MAX_COMMENT} characters.")

        await self.reports.add_review(report.id, moderator_id, current, to_status, note)
        report.status = to_status
        await self.session.commit()
        return {
            "id": str(report.id),
            "status": report.status,
            "updated_at": report.updated_at,
        }

    def _review_dto(self, row: ReportReview, moderator_name: str | None) -> dict:
        return {
            "id": str(row.id),
            "moderator_id": str(row.moderator_id),
            "moderator_name": moderator_name,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "comment": row.comment,
            "decided_at": row.created_at,
        }

    async def _cards(self, rows: list[Report]) -> list[dict]:
        ids = {row.reporter_id for row in rows} | {row.reported_id for row in rows}
        accounts = await self.reports.accounts_for(ids)
        today = utc_today()
        cards: list[dict] = []
        for row in rows:
            accused = accounts.get(row.reported_id)
            witness = accounts.get(row.reporter_id)
            cards.append(
                {
                    "id": str(row.id),
                    "reason": row.reason,
                    "details": row.details,
                    "status": row.status,
                    "created_at": row.created_at,
                    "reported": {
                        "user_id": str(row.reported_id),
                        "name": accused.name if accused else None,
                        # An erased account still carries a birth date — the one the erasure
                        # writes — and an age read off it would be a number nobody ever was.
                        "age": None
                        if accused is None or accused.is_deleted
                        else age_years(accused.birth_date, today),
                        "city": accused.city if accused else None,
                        "is_deleted": bool(accused.is_deleted) if accused else True,
                        "is_hidden": bool(accused.is_hidden) if accused else True,
                        "is_moderator": bool(accused.is_moderator) if accused else False,
                    },
                    "reporter": {
                        "user_id": str(row.reporter_id),
                        "name": witness.name if witness else None,
                    },
                }
            )
        return cards
