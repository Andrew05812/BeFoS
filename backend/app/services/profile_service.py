from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compatibility.traits import GOAL_KEYS
from app.core.exceptions import NotFoundError, ValidationError
from app.models import Interest, PHOTO_DISPLAY_ORDER, Photo, Profile
from app.models.base import age_years, utc_today
from app.repositories.activity_repo import ActivityRepository
from app.repositories.social_repo import DiscoveryRepository
from app.repositories.user_repo import UserRepository
from app.services.compatibility_service import CompatibilityService

VALID_GENDERS = {"male", "female", "nonbinary", "other"}
# The set a write is refused against is the table itself, not a list beside it: a goal accepted here
# and missing from `_GOAL_COMPAT` is stored, read back by the route as an answer, and scored 0.0 —
# the engine cannot tell an unscored goal from an opposite one.
VALID_GOALS = GOAL_KEYS

# Refused for a row that is not the caller's, whether it is absent or belongs to somebody else: an
# answer that distinguished the two would confirm a stranger's photograph exists.
_MISSING_PHOTO_MESSAGE = "No photograph with this number is in your profile."


def _rejected_goal(goal: object) -> ValidationError:
    """The refusal on both writes, naming the fault and the goals the app does carry."""
    return ValidationError(
        f"Invalid dating goal {goal!r}. The app scores: {', '.join(sorted(VALID_GOALS))}."
    )


# How many interests one profile carries. The number already decided what got stored; it is now
# the number a request is refused against, so it lives where both readings can reach it.
MAX_INTERESTS = 30

# How many gender preferences one profile can name. Derived rather than written down: a list
# longer than the set the names are checked against cannot be anything but a mistake, and
# refusing it first bounds what the unknown-name refusal echoes back.
MAX_GENDER_PREFERENCES = len(VALID_GENDERS)

# Editing any of these changes who the viewer should be shown, so the deck built under the
# old values cannot be paged through any more.
_DECK_FIELDS = {"age_min", "age_max", "gender_preference", "interests", "dating_goal"}

# These are what a pair's activity page is scored from, so editing one of them makes the
# cached page of another person's match stale rather than merely older.
_REC_FIELDS = {"interests", "city", "dating_goal"}

# The percent a match row carries is computed from less than the page above: CompatibilityInput
# is the answer vector, the interest set and the goal, and city enters none of them. Editing a
# city therefore drops the cached page and rewrites a number that cannot move.
_SCORE_FIELDS = {"interests", "dating_goal"}


def _parse_birth_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError("birth_date must be in YYYY-MM-DD format.")


def _validate_age(birth: date) -> int:
    age = age_years(birth, utc_today())
    if age < 18:
        raise ValidationError("Users must be 18 or older.")
    if age > 120:
        raise ValidationError("Invalid birth date.")
    return age


class ProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def get_for_write(self, user_id: uuid.UUID) -> Profile:
        """The row a request is about to write, held without the list that write consults.

        ``set_profile_interests`` replaces the whole set and a write that leaves interests out of
        its payload never touches them, so the list belongs to the answer rather than to the
        write. The session keeps its objects after the commit (``expire_on_commit=False``,
        ``app/core/database.py:43``), so this row is still readable then and already carries the
        values the request wrote; ``answer_from`` adds only the set.
        """
        profile = await self.users.get_profile_for_write(user_id)
        if profile is None:
            raise NotFoundError("Profile not found.")
        return profile

    async def answer_from(
        self, profile: Profile, written_interests: list[Interest] | None
    ) -> Profile:
        """The same row the write holds, with the interest set the answer shows hung onto it.

        Two reads used to follow every profile write: the row again, and with it the set. The row
        is not needed — ``expire_on_commit=False`` keeps the instance readable and its column
        values are the ones this request just wrote, and ``age`` is a property over ``birth_date``
        rather than a value the server computes, so nothing in the answer waits on the table. The
        set is needed only when the request did not replace it: a write that did has the rows in
        hand already, since it read them from the catalogue in order to store them.
        """
        interests = (
            await self.users.load_interests(profile.id)
            if written_interests is None
            else written_interests
        )
        return self.users.attach_interests(profile, interests)

    async def complete_onboarding(self, user_id: uuid.UUID, data: dict) -> Profile:
        profile = await self.get_for_write(user_id)

        name = data.get("name")
        if not name or not name.strip():
            raise ValidationError("Name is required.")
        birth = _parse_birth_date(data["birth_date"])
        _validate_age(birth)

        gender = data.get("gender", "other")
        if gender not in VALID_GENDERS:
            raise ValidationError("Invalid gender.")
        goal = data.get("dating_goal", "relationship")
        if goal not in VALID_GOALS:
            raise _rejected_goal(goal)
        # The schema counts characters, so "   " reaches here as a three-character answer to
        # a mandatory question. Stripping is what turns it into nothing, so the check that
        # the answer means something belongs after the strip, not before it.
        city = (data.get("city") or "").strip()
        if not city:
            raise ValidationError("City is required.")

        profile.name = name.strip()[:80]
        profile.birth_date = birth
        profile.gender = gender
        profile.city = city[:120]
        profile.about = (data.get("about") or None)
        profile.dating_goal = goal
        profile.lifestyle = data.get("lifestyle") or {}
        profile.age_min = int(data.get("age_min", 18))
        profile.age_max = int(data.get("age_max", 60))
        if profile.age_min > profile.age_max:
            profile.age_min, profile.age_max = profile.age_max, profile.age_min
        profile.gender_preference = self._checked_genders(data.get("gender_preference") or [])
        # The stamp is what makes this profile showable to anybody else. A re-submitted
        # onboarding keeps the first answer's timestamp: the second one does not change
        # the fact that the person finished, and it must not look like they only just did.
        if profile.onboarding_completed_at is None:
            profile.onboarding_completed_at = datetime.now(timezone.utc)

        written_interests = await self._set_interests(profile, data.get("interests") or [])
        await self.session.commit()
        # The set onboarding wrote is the set the answer shows, and the row this request wrote is
        # the row it answers from, so neither comes back from the table.
        profile = await self.answer_from(profile, written_interests)
        # Onboarding answers the whole preference set in one request — age band, genders,
        # goal, city, interests — and every one of those is an input to the deck, to the
        # cached activity page, and to the percent a stored match row carries. `update()`
        # drops exactly those three when the same fields change there; without the same
        # block here a deck built while the profile was still a shell (the feed answers as
        # soon as a profile row exists) stays ranked by an answer nobody gave, and a person
        # who re-answers after matching keeps showing their match list the old percent.
        await DiscoveryRepository(self.session).deck_invalidate(user_id)
        await ActivityRepository(self.session).invalidate_for_user(user_id)
        await CompatibilityService(self.session).refresh_pair_scores(user_id)
        await self.session.commit()
        return profile

    async def update(self, user_id: uuid.UUID, data: dict) -> Profile:
        profile = await self.get_for_write(user_id)

        if "name" in data and data["name"] is not None:
            if not data["name"].strip():
                raise ValidationError("Name cannot be empty.")
            profile.name = data["name"].strip()[:80]
        if "birth_date" in data and data["birth_date"] is not None:
            birth = _parse_birth_date(data["birth_date"])
            _validate_age(birth)
            profile.birth_date = birth
        if "city" in data and data["city"] is not None:
            city = data["city"].strip()
            if not city:
                raise ValidationError("City cannot be empty.")
            profile.city = city[:120]
        if "about" in data:
            profile.about = data["about"]
        if "gender" in data and data["gender"] is not None:
            if data["gender"] not in VALID_GENDERS:
                raise ValidationError("Invalid gender.")
            profile.gender = data["gender"]
        if "dating_goal" in data and data["dating_goal"] is not None:
            if data["dating_goal"] not in VALID_GOALS:
                raise _rejected_goal(data["dating_goal"])
            profile.dating_goal = data["dating_goal"]
        if "lifestyle" in data and data["lifestyle"] is not None:
            profile.lifestyle = data["lifestyle"]
        if data.get("age_min") is not None:
            profile.age_min = int(data["age_min"])
        if data.get("age_max") is not None:
            profile.age_max = int(data["age_max"])
        if profile.age_min > profile.age_max:
            raise ValidationError("age_min cannot be greater than age_max.")
        if "gender_preference" in data and data["gender_preference"] is not None:
            profile.gender_preference = self._checked_genders(data["gender_preference"])
        if "is_hidden" in data and data["is_hidden"] is not None:
            profile.is_hidden = bool(data["is_hidden"])
        written_interests: list[Interest] | None = None
        if "interests" in data and data["interests"] is not None:
            written_interests = await self._set_interests(profile, data["interests"])

        touched_deck = bool(_DECK_FIELDS & data.keys())
        touched_pair = bool(_REC_FIELDS & data.keys())
        touched_score = bool(_SCORE_FIELDS & data.keys())
        await self.session.commit()
        profile = await self.answer_from(profile, written_interests)
        # What the viewer wants decides who lands in their deck and in what order. The
        # ranked part of that deck was built for the previous answer, so it is dropped;
        # cards already shown stay shown-once, which is what the seen rows remember.
        # The pair page is dropped for the same reason from the other side: it explains
        # activities by the interests, the city and the goal that just changed.
        if touched_deck or touched_pair:
            if touched_deck:
                await DiscoveryRepository(self.session).deck_invalidate(user_id)
            if touched_pair:
                await ActivityRepository(self.session).invalidate_for_user(user_id)
                # The goal and the interests are two of the three inputs a pair's percent is
                # computed from, so the number the match list shows has just gone stale too. An
                # edit that moves neither of them has nothing to recompute: the rewrite reads
                # every pair of this person's matches, both profiles of each and both answer
                # vectors, and hands back the number that is already on the row.
                if touched_score:
                    await CompatibilityService(self.session).refresh_pair_scores(user_id)
            await self.session.commit()
        return profile

    async def _set_interests(self, profile: Profile, slugs: list[str]) -> list[Interest]:
        """Store the answered set, refusing an answer the store cannot hold.

        The catalogue read is what turns slugs into interests, so the rows the answer needs are in
        hand before the link rows are written — returning them is what lets the response skip both
        the profile row and the set.

        Both checks below run before anything reaches that write, and the write is a DELETE of the
        old set plus one INSERT of the new. A name the catalogue does not carry used to be dropped
        between them, so an answer of one real name and two invented ones erased the thirty rows the
        profile held and stored one, at HTTP 200 with a shorter list and no word about it. The
        ceiling is checked first because it needs no query, and because it bounds the list the
        unknown-name refusal echoes: a body of two hundred invented slugs gets the ceiling sentence,
        not two hundred names back.
        """
        if any(not s.strip() for s in slugs):
            raise ValidationError("An interest name cannot be empty.")
        cleaned = list(dict.fromkeys(s.strip().lower() for s in slugs))
        if len(cleaned) > MAX_INTERESTS:
            raise ValidationError(
                f"A profile can hold at most {MAX_INTERESTS} interests; "
                f"this answer names {len(cleaned)}."
            )
        interests = await self.users.list_interests_by_slugs(cleaned)
        known = {interest.slug for interest in interests}
        missing = [slug for slug in cleaned if slug not in known]
        if missing:
            raise ValidationError(f"Interests the catalogue does not know: {', '.join(missing)}.")
        await self.users.set_profile_interests(profile.id, interests)
        return interests

    def _checked_genders(self, genders: list[str]) -> list[str]:
        """Return the answered set, refusing an answer the preference filter cannot use.

        Cleaning runs before comparing, the same rule the interest set already follows, so a name
        that differs only by case or spaces is the name the set carries rather than a fault.

        Both silences this closes were measured on the live stand: a body naming one gender the
        server has never heard of alongside a real one stored the real one alone and answered
        ``200``, and a body naming only ``"Male"`` stored the empty list. The second is not a
        shorter preference but a vanished filter — ``social_repo._preference_conditions`` hangs
        ``Profile.gender.in_(...)`` on a non-empty list only — so the deck the person is shown
        widens to every gender while the profile reads back nothing about what was asked. Storing
        the unknown name instead would be the mirror mistake: the same condition would then match
        no profile at all and the deck would be empty forever.
        """
        if any(not gender.strip() for gender in genders):
            raise ValidationError("A gender preference cannot be empty.")
        cleaned = list(dict.fromkeys(gender.strip().lower() for gender in genders))
        if len(cleaned) > MAX_GENDER_PREFERENCES:
            raise ValidationError(
                f"A profile can prefer at most {MAX_GENDER_PREFERENCES} genders; "
                f"this answer names {len(cleaned)}."
            )
        missing = [gender for gender in cleaned if gender not in VALID_GENDERS]
        if missing:
            raise ValidationError(f"Genders the server does not know: {', '.join(missing)}.")
        return cleaned

    async def add_photo(self, user_id: uuid.UUID, url: str, make_primary: bool = False) -> Photo:
        held = await self._photos_of(user_id)
        photo = Photo(user_id=user_id, url=url, is_primary=False, position=0)
        self.session.add(photo)
        await self.session.flush()
        # The new picture leads when the person asked for it to be theirs to show, and holds its
        # place at the end otherwise; either way the whole row is renumbered, because a photograph
        # added beside a list whose positions are 0..n-1 would otherwise sit outside that row.
        ordered = ([photo] + held) if make_primary else (held + [photo])
        await self._write_photo_order(ordered)
        return photo

    async def delete_photo(self, user_id: uuid.UUID, photo_id: uuid.UUID) -> str:
        """Remove one of the owner's photographs, renumber what is left, answer its stored file.

        The head of the row is the avatar every reader paints, so removing it is not a hole: the
        photograph that followed it takes the flag in the same write. Removing the last photograph
        is a profile with no photographs, which is what the person asked for and what every reader
        already answers as its own empty state.
        """
        held = await self._photos_of(user_id, for_update=True)
        target = next((photo for photo in held if photo.id == photo_id), None)
        if target is None:
            raise NotFoundError(_MISSING_PHOTO_MESSAGE)
        await self.session.delete(target)
        await self.session.flush()
        await self._write_photo_order([photo for photo in held if photo.id != photo_id])
        return target.url

    async def set_primary_photo(self, user_id: uuid.UUID, photo_id: uuid.UUID) -> None:
        held = await self._photos_of(user_id, for_update=True)
        target = next((photo for photo in held if photo.id == photo_id), None)
        if target is None:
            raise NotFoundError(_MISSING_PHOTO_MESSAGE)
        await self._write_photo_order([target] + [photo for photo in held if photo.id != photo_id])

    async def reorder_photos(self, user_id: uuid.UUID, photo_ids: list[uuid.UUID]) -> None:
        """Write the order the owner named, or refuse the list — never a part of it.

        A submitted order that names a stranger's row is refused as a row that is not there, the way
        every other route here refuses it: confirming the photograph exists is what 403 does. An order
        that leaves one of the owner's photographs out is refused rather than applied, because writing
        half a permutation is exactly how `position` and `is_primary` come apart: the left-out row
        would keep an index the rest of the row has been renumbered past.
        """
        held = await self._photos_of(user_id, for_update=True)
        if len(photo_ids) != len(set(photo_ids)):
            raise ValidationError("A photo order cannot name the same photograph twice.")
        held_ids = {photo.id for photo in held}
        if not held_ids.issuperset(photo_ids):
            raise NotFoundError(_MISSING_PHOTO_MESSAGE)
        missing = held_ids - set(photo_ids)
        if missing:
            raise ValidationError(
                f"A photo order must name every photograph the profile holds; it leaves out {len(missing)}."
            )
        by_id = {photo.id: photo for photo in held}
        await self._write_photo_order([by_id[photo_id] for photo_id in photo_ids])

    async def _photos_of(self, user_id: uuid.UUID, *, for_update: bool = False) -> list[Photo]:
        """The owner's photographs in the one order readers see them, optionally held for a write."""
        stmt = select(Photo).where(Photo.user_id == user_id).order_by(*PHOTO_DISPLAY_ORDER)
        if for_update:
            # Two management requests from one account can land together — a tap on «Удалить» next
            # to a drag — and both would read the same row and write a renumbering of it. Holding the
            # rows makes the second wait for the first's commit instead of racing it, so the order
            # that reaches disk is one of the two the person asked for, never a blend.
            stmt = stmt.with_for_update()
        return list((await self.session.execute(stmt)).scalars().all())

    async def _write_photo_order(self, photos: list[Photo]) -> list[Photo]:
        """The only writer of `position` and `is_primary`, so the two cannot drift apart.

        Both come out of one list in one pass: the position is the row's index in the order the owner
        chose, and `is_primary` holds of that order's head alone — of nothing at all when the list is
        empty, which is the honest state of a profile whose last photograph was removed.
        """
        for index, photo in enumerate(photos):
            photo.position = index
            photo.is_primary = index == 0
        await self.session.commit()
        return photos
