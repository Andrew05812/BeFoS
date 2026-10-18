from __future__ import annotations

"""The rules a pair's hour is judged by, kept where both doors that arrange it can read them.

Two screens put an hour in front of a pair — the card page of the recommendations and the plan
itself — and the moment is one fact about the pair, so the rule that decides whether an instant the
two of them hold is an agreement has to have one home. It used to sit inside `RecommendationService`
while only that one door existed; a second door reading a service's private helper would either copy
the rule or couple the two screens to each other's internals.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.core.exceptions import ValidationError
from app.models.base import utcnow
from app.models.chat import (
    KIND_PLAN_ACCEPTED,
    KIND_PLAN_AGREED,
    KIND_PLAN_CANCELLED,
    KIND_PLAN_CHANGED,
    KIND_PLAN_COMPLETED,
    KIND_PLAN_DECLINED,
    KIND_PLAN_PROPOSED,
    KIND_PLAN_RESCHEDULED,
    KIND_PLAN_VOIDED,
)

# A meeting is arranged for a moment that has not passed and is not a rumor about next year. The
# tolerance is a clock allowance, not a policy: a phone whose clock runs a minute behind should be
# able to say «сейчас», and a card forty years ahead would render as a plan nobody made.
MIN_LEAD = timedelta(minutes=15)
MAX_LEAD = timedelta(days=400)


def _moment_text(when: datetime) -> str:
    """The instant as the journal says it: named in UTC and said so.

    The pair is often in two cities, and a card that printed the moment on the server's own clock
    would hand the wrong hour to whoever reads it. Everything a card can draw from fields is in the
    fields; this is the fallback sentence that has to be true on its own.
    """
    return when.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


def plan_sentence(kind: str, title: str, when: datetime | None = None) -> str:
    """The sentence a plan line is born with, for a client that draws only text."""
    if when is None:
        return {
            KIND_PLAN_PROPOSED: f"Идея для встречи: {title}",
            KIND_PLAN_ACCEPTED: f"Оба за: {title}",
            KIND_PLAN_DECLINED: f"Идея отклонена: {title}",
            KIND_PLAN_CANCELLED: f"План отменён: {title}",
            KIND_PLAN_COMPLETED: f"Встреча завершена: {title}",
            # A plan with no hour still has a place and a note, so a change of those is sayable
            # without a moment; the card draws what changed from the plan's own fields.
            KIND_PLAN_CHANGED: f"План изменён: {title}",
        }[kind]
    moment = _moment_text(when)
    return {
        KIND_PLAN_AGREED: f"Вы договорились встретиться: {title} — {moment}",
        KIND_PLAN_VOIDED: f"Договорённость отменена: {title} — {moment}",
        KIND_PLAN_RESCHEDULED: f"Перенос встречи: {title} — {moment}. Ждём подтверждения.",
        KIND_PLAN_CANCELLED: f"План отменён: {title} — {moment}",
        KIND_PLAN_COMPLETED: f"Встреча завершена: {title} — {moment}",
        # A change of place or note does not move the hour, so the moment it carries is the one the
        # pair still stands on: the line says the arrangement changed, and the card draws what it is
        # now from the plan's own fields.
        KIND_PLAN_CHANGED: f"План изменён: {title} — {moment}",
    }[kind]


# What the two fields a person may rewrite on the pair's plan are called in the sentence that says
# one of them moved, and what each edge of the move is called when it holds no text.
FIELD_WORDS = {"place": "место", "note": "заметка"}
_FIELD_NOTHING = "не было"
_FIELD_REMOVED = "снято"


def _edge_text(value: str | None, *, empty_word: str) -> str:
    return empty_word if value is None else f"«{value}»"


def plan_change_sentence(
    title: str,
    when: datetime | None,
    changes: list[tuple[str, str | None, str | None]],
) -> str:
    """The sentence a plan-change line carries when what moved is the pair's own words.

    `plan_sentence` says *that* the plan changed, which is enough for the chat card the pair already
    has: that card draws the arrangement from the plan's own fields, and a body repeating them would
    be a second copy of a fact with two readings. The plan's history is the other reader, and there
    the fields being asked about are the values as they *were* — a screen that prints only the place
    the plan holds now says nothing to a pair looking for the evening it moved. So this line names
    both edges of every field that moved, in the words the pair wrote.

    `changes` holds `(field, previous, current)` for the fields that actually moved; the caller diffs
    before writing, so a field left as it was is not in the list. This is also why the two edges can
    share one convention: an erased field is named by `empty_word` on the side it left, and a field
    written for the first time on the side it came from.

    `my_note` never appears here. A person's own remark about their own plan is read by its author and
    by nobody else, and the journal this line belongs to is read by both halves of the pair — see
    `docs/DATABASE.md` on `shared_plan_members.personal_note`.
    """
    base = plan_sentence(KIND_PLAN_CHANGED, title, when)
    moves = ", ".join(
        "{}: {} → {}".format(
            FIELD_WORDS[field],
            _edge_text(before, empty_word=_FIELD_NOTHING),
            _edge_text(after, empty_word=_FIELD_REMOVED),
        )
        for field, before, after in changes
    )
    return f"{base}; {moves}"


def agreed_instant(
    mine: tuple[datetime | None, datetime | None],
    theirs: tuple[datetime | None, datetime | None],
) -> datetime | None:
    """The moment both halves of the pair have landed on, or nothing when they have not.

    A plan is one instant named by one of them and agreed to by the other. Two different instants
    each satisfying that rule is a trade — one named 19:00 and the other agreed, the second named
    20:00 and the first agreed — and a pair that traded has not agreed on a moment, it has talked
    past one. The card then shows both proposals and no plan line, which is what the two rows
    actually say; folding the trade into the earlier of the two would print a promise nobody holds.

    The reading depends on the rows holding what a person currently means rather than everything they
    ever said, and that is the half of the contract `set_meeting_time` keeps: a person who names a
    *different* moment has withdrawn the acceptance they were standing on. Without that withdrawal the
    trade above is not two pairs of answers but three — the earlier promise still counted beside the
    two offers — and the same rule that refuses to pick between the two offers then refuses to see the
    agreement a pair reaches when the second half accepts the moved hour. It also silently swallows the
    move of whoever had only accepted: their own stale acceptance keeps the old instant agreed, so the
    tap changes nothing anywhere and no line is written. Both of those are readings of the same two
    rows, and the rows are what had to become honest.
    """
    my_time, my_accept = mine
    their_time, their_accept = theirs
    candidates: set[datetime] = set()
    if my_time is not None and my_time == their_accept:
        candidates.add(my_time)
    if their_time is not None and their_time == my_accept:
        candidates.add(their_time)
    if len(candidates) != 1:
        return None
    return candidates.pop()


def unmatched_offer(
    lines: dict[uuid.UUID, tuple[datetime | None, datetime | None]]
) -> tuple[datetime | None, uuid.UUID | None]:
    """The single hour one half has named and the other has not confirmed, and who named it.

    Read out of the pair's own rows rather than stored beside them, so the plan cannot claim a
    question the card is not asking. A pair that named two different hours answers with nothing: the
    card shows both offers, and a plan that picked one of them would be an answer nobody gave. Both
    halves naming the *same* instant is a pair one tap from an agreement, and the hour comes back
    with no actor to confirm it — either of them is being asked.

    Nothing is the honest answer for one case this read cannot see, and that case is a moved evening:
    a pair that stood on 19:00 and has just been moved to 20:00 by the half who only ever agreed also
    has two rows naming two different instants. `PlanService._ask_of` asks this only when the plan's
    own record of the question has gone stale, so a reschedule is answered by the plan and this by the
    rows.
    """
    named = {
        user_id: line[0]
        for user_id, line in lines.items()
        if line[0] is not None and line[1] != line[0]
    }
    if not named:
        return None, None
    instants = set(named.values())
    if len(instants) > 1:
        return None, None
    return instants.pop(), None if len(named) > 1 else next(iter(named))


def validate_meeting_time(when: datetime) -> None:
    """Reject an instant the pair cannot meet at, before it becomes a card both halves read."""
    if when.tzinfo is None:
        raise ValidationError(
            "Meeting time must carry a UTC offset: the pair is often in two cities, and a "
            "wall clock with no zone names a moment in one of them at random."
        )
    lead = when.astimezone(timezone.utc) - utcnow()
    if lead < -MIN_LEAD:
        raise ValidationError("This moment has already passed.")
    if lead > MAX_LEAD:
        raise ValidationError("A meeting is arranged within the next year, not beyond it.")
