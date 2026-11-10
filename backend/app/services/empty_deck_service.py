"""Why the deck is empty, said in aggregates the reader is allowed to see.

«Анкеты закончились» was one sentence for seven different worlds. A person who has answered every
card, a person whose filters exclude a city that is right there, a person who arrived before a
single other profile was confirmed and a person whose request failed all read the same thing and
were offered the same dead end.

The server is the only place that can tell them apart, and this service is the shape of that
answer under a rule: *the explanation must never be usable to enumerate other accounts*. So it
returns a reason and coarse buckets, never rows, never ids, never exact counts of the showable
population, and never anything owned by another person. The buckets are the one number the empty
screen may say aloud — «рядом пока никого» / «рядом уже есть люди» — and the threshold is chosen so
that a bucket cannot become a name:

* `none`  — 0;
* `few`   — 1…9;
* `some`  — 10…49;
* `many`  — 50+.

The reasons, in the order they win:

* `email_unconfirmed` / `onboarding_incomplete` — the reader's own row, the two gates that decide
  whether *they* may be shown. Not a fact about anybody else. The client's start screen normally
  stops these before the deck, and the API still answers them because a direct caller deserves
  the same sentence as the screen;
* `exhausted` — somebody matched the reader's filters and the reader has already decided about
  them (a tap, a pass, a pair). «You have seen everyone» is not «there is nobody»;
* `city_filter_empty` — the gender and age are affordable somewhere, but the chosen search city
  removes every one of them. The one filter to loosen is named;
* `filters_too_narrow` — showable people exist, none matches the current gender/age band;
* `audience_preparing` — nobody is showable yet, but accounts do exist behind the two onboarding
  gates (address not confirmed / questionnaire not finished). This is a bucketed boolean for the
  same city, never a count and never a person: a count in a small city plus a name from the street
  is how a «zero» becomes a directory;
* `no_one_yet` — no other account the reader may be shown: no showable profile, and nobody behind
  the two onboarding gates either. The count deliberately does not include accounts the reader
  blocked, profiles their owners hid, or people outside the block pair — «nobody here» is a fact
  about the reader's deck, not a directory of the product. The honest sentence is «пока здесь
  никого», and the only action that changes it is an invitation.

Every reason has one answer the client can act on: invite (`referral`), widen the filters, finish
the account, wait (waitlist), or retry (a transient failure never becomes a reason here — the deck
route answers 5xx and the screen owns its retry). The diagnosis reads only counts, so it cannot
leak a profile; it is written as one statement, so an empty page pays one round trip for being
explained.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.tracker import Event, tracker
from app.models import Profile, User
from app.repositories.social_repo import DiscoveryRepository
from app.services.waitlist_service import WaitlistService

EMAIL_UNCONFIRMED = "email_unconfirmed"
ONBOARDING_INCOMPLETE = "onboarding_incomplete"
EXHAUSTED = "exhausted"
CITY_FILTER_EMPTY = "city_filter_empty"
FILTERS_TOO_NARROW = "filters_too_narrow"
AUDIENCE_PREPARING = "audience_preparing"
NO_ONE_YET = "no_one_yet"

# The client renders these, but they are part of the contract a second client would need: a bucket
# is a promise that the server will not hand out a number sharp enough to point at a person.
NONE = "none"
FEW = "few"
SOME = "some"
MANY = "many"


def bucket(count: int) -> str:
    if count <= 0:
        return NONE
    if count < 10:
        return FEW
    if count < 50:
        return SOME
    return MANY


class EmptyDeckService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.discovery = DiscoveryRepository(session)
        self.waitlist = WaitlistService(session)

    async def explain(
        self,
        viewer_id: uuid.UUID,
        profile: Profile,
        *,
        gender_pref: list[str],
        age_min: int,
        age_max: int,
        city_pref: str | None,
        track: bool,
        viewer_is_verified: bool | None = None,
    ) -> dict:
        """The reason, the buckets and the reader's own waiting mark for an empty page.

        `viewer_is_verified` is the flag the authenticated route already holds; passing it keeps
        the diagnosis from reading the account row a second time. It is optional only so a
        caller that reaches this service without a session still gets the same sentence, and that
        path is the one place a profile read is paid for the answer.
        """
        if viewer_is_verified is None:
            viewer = await self.session.get(User, viewer_id)
            assert viewer is not None, "a deck is read by an account that exists"
            viewer_is_verified = viewer.is_verified

        if not viewer_is_verified or profile.onboarding_completed_at is None:
            waiting = await self.waitlist.status_for(viewer_id)
            if not viewer_is_verified:
                answer = self._answer(EMAIL_UNCONFIRMED, waiting)
            else:
                answer = self._answer(ONBOARDING_INCOMPLETE, waiting)
        else:
            snapshot = await self.discovery.audience_snapshot(
                viewer_id=viewer_id,
                gender_pref=gender_pref,
                age_min=age_min,
                age_max=age_max,
                city_pref=city_pref,
                city=(profile.city or "").strip() or None,
            )
            reason = self._reason(snapshot, city_pref=city_pref)
            answer = {
                "reason": reason,
                "audience": bucket(snapshot["showable_any"]),
                "nearby": bucket(snapshot["same_city_any"]),
                "someone_preparing_here": snapshot["preparing_nearby"] > 0,
                "can_widen_filters": self._can_widen(reason, snapshot, city_pref=city_pref),
                "waitlist_joined": snapshot["waitlist_joined"],
                "waitlist_city": snapshot["waitlist_city"],
            }

        if track:
            tracker.track(
                Event.DISCOVERY_EMPTY,
                str(viewer_id),
                reason=answer["reason"],
                audience=answer.get("audience", NONE),
                nearby=answer.get("nearby", NONE),
                preparing=bool(answer.get("someone_preparing_here", False)),
                can_widen=bool(answer.get("can_widen_filters", False)),
            )
        return answer

    @staticmethod
    def _answer(reason: str, waiting: dict) -> dict:
        return {
            "reason": reason,
            "audience": NONE,
            "nearby": NONE,
            "someone_preparing_here": False,
            "can_widen_filters": False,
            "waitlist_joined": waiting["joined"],
            "waitlist_city": waiting["city"],
        }

    @staticmethod
    def _reason(snapshot: dict[str, int], *, city_pref: str | None) -> str:
        if snapshot["remaining"] > 0:
            # The page ended at a cursor, not at the world; a fresh load is the next step.
            return EXHAUSTED
        if snapshot["ever"] > 0:
            return EXHAUSTED
        if snapshot["showable_any"] > 0:
            if city_pref and snapshot["gender_age_any"] > 0:
                return CITY_FILTER_EMPTY
            return FILTERS_TOO_NARROW
        if snapshot["preparing_any"] > 0:
            return AUDIENCE_PREPARING
        return NO_ONE_YET

    @staticmethod
    def _can_widen(reason: str, snapshot: dict[str, int], *, city_pref: str | None) -> bool:
        if reason == EXHAUSTED:
            # Only city is worth loosening after the deck is spent: gender and age already
            # admitted somebody, so widening them would change the person, not the supply.
            return bool(city_pref) and snapshot["open_gender_age"] > 0
        if reason == CITY_FILTER_EMPTY:
            return snapshot["open_gender_age"] > 0
        if reason == FILTERS_TOO_NARROW:
            return snapshot["open_any"] > 0
        return False
