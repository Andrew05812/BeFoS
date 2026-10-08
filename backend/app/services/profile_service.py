from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models import Photo, Profile
from app.models.base import age_years, utc_today
from app.repositories.activity_repo import ActivityRepository
from app.repositories.social_repo import DiscoveryRepository
from app.repositories.user_repo import UserRepository
from app.services.compatibility_service import CompatibilityService

VALID_GENDERS = {"male", "female", "nonbinary", "other"}
VALID_GOALS = {"relationship", "marriage", "friendship", "casual", "networking"}

# Editing any of these changes who the viewer should be shown, so the deck built under the
# old values cannot be paged through any more.
_DECK_FIELDS = {"age_min", "age_max", "gender_preference", "interests", "dating_goal"}

# These are what a pair's activity page is scored from, so editing one of them makes the
# cached page of another person's match stale rather than merely older.
_REC_FIELDS = {"interests", "city", "dating_goal"}


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

    async def get_or_404(self, user_id: uuid.UUID) -> Profile:
        """The profile as a screen shows it: the row, with its interest list loaded."""
        profile = await self.users.get_profile(user_id)
        if profile is None:
            raise NotFoundError("Profile not found.")
        return profile

    async def get_for_write(self, user_id: uuid.UUID) -> Profile:
        """The row a request is about to write, held without the list that write consults.

        ``set_profile_interests`` replaces the whole set and a write that leaves interests out of
        its payload never touches them, so the list belongs to the answer rather than to the
        write. The answer is built from ``get_or_404`` after the commit, which brings it.
        """
        profile = await self.users.get_profile_for_write(user_id)
        if profile is None:
            raise NotFoundError("Profile not found.")
        return profile

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
            raise ValidationError("Invalid dating goal.")
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
        profile.gender_preference = self._clean_genders(data.get("gender_preference") or [])
        # The stamp is what makes this profile showable to anybody else. A re-submitted
        # onboarding keeps the first answer's timestamp: the second one does not change
        # the fact that the person finished, and it must not look like they only just did.
        if profile.onboarding_completed_at is None:
            profile.onboarding_completed_at = datetime.now(timezone.utc)

        await self._set_interests(profile, data.get("interests") or [])
        await self.session.commit()
        # The row comes back through the read that carries the interest list, because the answer
        # shows it: after a commit the identity map holds nothing cached, so this one read is both
        # the server's own values and the set that was just stored. A refresh of the row alone
        # would leave the list behind, and the answer would carry either an empty set or a load
        # the write path refused.
        profile = await self.get_or_404(user_id)
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
                raise ValidationError("Invalid dating goal.")
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
            profile.gender_preference = self._clean_genders(data["gender_preference"])
        if "is_hidden" in data and data["is_hidden"] is not None:
            profile.is_hidden = bool(data["is_hidden"])
        if "interests" in data and data["interests"] is not None:
            await self._set_interests(profile, data["interests"])

        touched_deck = bool(_DECK_FIELDS & data.keys())
        touched_pair = bool(_REC_FIELDS & data.keys())
        await self.session.commit()
        profile = await self.get_or_404(user_id)
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
                # computed from, so the number the match list shows has just gone stale too.
                await CompatibilityService(self.session).refresh_pair_scores(user_id)
            await self.session.commit()
        return profile

    async def _set_interests(self, profile: Profile, slugs: list[str]) -> None:
        cleaned = list(dict.fromkeys(s.strip().lower() for s in slugs if s and s.strip()))[:30]
        interests = await self.users.list_interests_by_slugs(cleaned)
        await self.users.set_profile_interests(profile.id, interests)

    def _clean_genders(self, genders: list[str]) -> list[str]:
        cleaned = [g for g in genders if g in VALID_GENDERS]
        return list(dict.fromkeys(cleaned))

    async def add_photo(self, user_id: uuid.UUID, url: str, make_primary: bool = False) -> Photo:
        if make_primary:
            await self.session.execute(
                Photo.__table__.update()
                .where(Photo.user_id == user_id)
                .values(is_primary=False)
            )
        photo = Photo(user_id=user_id, url=url, is_primary=make_primary, position=0)
        self.session.add(photo)
        await self.session.commit()
        return photo
