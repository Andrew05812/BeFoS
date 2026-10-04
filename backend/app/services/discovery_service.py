from __future__ import annotations

import base64
import binascii
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.tracker import Event, tracker
from app.compatibility.engine import compute_compatibility
from app.core.exceptions import NotFoundError, ValidationError
from app.models import PHOTO_DISPLAY_ORDER, Photo, Profile
from app.repositories.social_repo import DiscoveryRepository, SocialRepository
from app.repositories.user_repo import UserRepository
from app.services.compatibility_service import CompatibilityService

# Candidates ranked and appended in one go. Big enough that a viewer rarely waits on a
# rebuild, small enough that one rebuild never pulls the whole selection into Python.
DECK_BATCH = 150
# Refill once the undelivered part of the deck drops below this, so the next swipe is
# always served from rows that already exist.
DECK_FLOOR = 40
# How many claims one page may spend. A normal page fills in one; the rest are for the
# rows that went stale while they waited, and a page needing more than this has more
# broken promises than a refill can be expected to repair in a single request.
CLAIM_ROUNDS = 4

CURSOR_PREFIX = "rank"
BAD_CURSOR = "The link to the next page is broken."


def encode_cursor(rank: int) -> str:
    raw = f"{CURSOR_PREFIX}:{rank}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> int:
    """Where the viewer stopped. Absent means "from the top of my deck".

    A cursor is opaque to the client and comes back tampered with only if somebody is
    poking at the API by hand, so it is refused as input rather than trusted as a rank.
    """
    if not cursor:
        return -1
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise ValidationError(BAD_CURSOR)
    prefix, _, digits = raw.partition(":")
    if prefix != CURSOR_PREFIX or not digits.isdigit():
        raise ValidationError(BAD_CURSOR)
    return int(digits)


def _highlight(viewer_profile: Profile, profile: Profile, shared_slugs: set[str], result) -> str | None:
    """One-line, data-derived answer to 'why is this person shown to me?'."""
    names = [i.name for i in profile.interests if i.slug in shared_slugs]
    if len(names) >= 2:
        return "Общие интересы: " + ", ".join(names[:3])
    if len(names) == 1:
        # Label form, not a sentence: "нравится" would disagree with a plural
        # interest name ("Иностранные языки"), and we cannot inflect for number here.
        # No quotes either — the chips above render the same names bare, and the
        # plural branch two lines up does too.
        return f"Общий интерес: {names[0]}"
    viewer_city = (viewer_profile.city or "").strip().lower()
    if viewer_city and (profile.city or "").strip().lower() == viewer_city:
        return "Из вашего города"
    best = max(result.categories, key=lambda c: c.percent, default=None)
    if best is not None and best.percent >= 70:
        return f"Высокое совпадение: {best.label.lower()} — {best.percent}%"
    return None


class DiscoveryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.social = SocialRepository(session)
        self.discovery = DiscoveryRepository(session)
        self.compatibility = CompatibilityService(session)

    @staticmethod
    def _preferences(viewer_profile: Profile) -> dict:
        return {
            "gender_pref": viewer_profile.gender_preference or [],
            "age_min": viewer_profile.age_min,
            "age_max": viewer_profile.age_max,
            "city": viewer_profile.city_preference or None,
        }

    async def _ranked_scores(
        self, viewer_input, ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Compatibility of every id in ``ids`` against the viewer, in one batch."""
        profiles = {p.user_id: p for p in await self.users.get_profiles_by_ids(ids)}
        comp_profiles = await self.compatibility.tests.get_compatibility_profiles(ids)

        scores: dict[uuid.UUID, int] = {}
        for candidate_id, profile in profiles.items():
            candidate_input = CompatibilityService.input_from(
                profile, comp_profiles.get(candidate_id)
            )
            result = compute_compatibility(
                viewer_input, candidate_input, self.compatibility.weight_config
            )
            scores[candidate_id] = result.overall_percent
        return scores

    async def _refill_deck(self, viewer_id: uuid.UUID, viewer_input, prefs: dict) -> bool:
        """Rank a fresh batch of never-shown candidates and put it at the end of the deck.

        Returns whether the deck grew, so a caller that ran out of cards mid-page can tell
        "there is nobody left" from "there is more, keep going".
        """
        fresh = await self.discovery.new_candidate_ids(
            viewer_id=viewer_id, limit=DECK_BATCH, **prefs
        )
        if not fresh:
            return False
        scores = await self._ranked_scores(viewer_input, fresh)
        # Highest compatibility first. The batch came out of SQL newest-first and sorted
        # by id, so a tie keeps that order and the deck is reproducible for the same data.
        ranked = sorted(
            ((cid, scores[cid]) for cid in fresh if cid in scores),
            key=lambda item: (-item[1], str(item[0])),
        )
        if not ranked:
            return False
        await self.discovery.deck_append(
            viewer_id, ranked, first_rank=await self.discovery.deck_next_rank(viewer_id)
        )
        return True

    async def _build_cards(
        self, viewer_profile: Profile, viewer_input, ids: list[uuid.UUID]
    ) -> list[dict]:
        """Cards for the claimed ids, in deck order — one query per concern, not per card."""
        if not ids:
            return []
        profiles = {p.user_id: p for p in await self.users.get_profiles_by_ids(ids)}
        photos = await self.users.get_primary_photos(ids)
        comp_profiles = await self.compatibility.tests.get_compatibility_profiles(ids)

        cards: list[dict] = []
        for candidate_id in ids:
            profile = profiles.get(candidate_id)
            if profile is None:
                continue
            candidate_input = CompatibilityService.input_from(
                profile, comp_profiles.get(candidate_id)
            )
            result = compute_compatibility(
                viewer_input, candidate_input, self.compatibility.weight_config
            )
            photo = photos.get(candidate_id)
            shared_slugs = viewer_input.interests & candidate_input.interests
            cards.append(
                {
                    "user_id": str(candidate_id),
                    "name": profile.name,
                    "age": profile.age,
                    "city": profile.city,
                    "about": profile.about,
                    "dating_goal": profile.dating_goal,
                    "photo_url": photo.url if photo else None,
                    "interests": [i.name for i in profile.interests][:8],
                    "compatibility": result.overall_percent,
                    "shared_interests_count": len(shared_slugs),
                    "highlight": _highlight(viewer_profile, profile, shared_slugs, result),
                }
            )
        return cards

    async def feed(
        self, viewer_id: uuid.UUID, *, limit: int = 20, cursor: str | None = None
    ) -> dict:
        viewer_profile = await self.users.get_profile(viewer_id)
        if viewer_profile is None:
            raise NotFoundError("Complete your profile before discovering people.")

        after_rank = decode_cursor(cursor)
        prefs = self._preferences(viewer_profile)
        viewer_input = await self.compatibility.build_input(viewer_id)

        # Rank more candidates before the viewer runs out, not after: the page that
        # follows a rebuild costs the same as any other.
        refilled = False
        if await self.discovery.deck_ready_count(viewer_id, cap=DECK_FLOOR) < DECK_FLOOR:
            refilled = await self._refill_deck(viewer_id, viewer_input, prefs)

        # Fill the page from the deck. A claim can come back short: a queued row is a
        # promise about a person who may have hidden or been blocked since it was written,
        # and the rows that no longer hold are dropped rather than served. The loop is
        # bounded, because a page made entirely of broken promises is a signal to stop
        # paging now, not a puzzle to solve forever.
        ids: list[uuid.UUID] = []
        last_rank = after_rank
        for _ in range(CLAIM_ROUNDS):
            if len(ids) >= limit:
                break
            rows = await self.discovery.deck_claim(
                viewer_id, after_rank=last_rank, limit=limit - len(ids)
            )
            if not rows:
                # Either the deck held only stale rows or the viewer is at its end. A
                # refill tells which; asking twice when the selection is empty would only
                # read the same answer twice, so one attempt per request is enough.
                if refilled:
                    break
                refilled = await self._refill_deck(viewer_id, viewer_input, prefs)
                if not refilled:
                    break
                continue
            last_rank = rows[-1][1]
            ids.extend(await self.discovery.deck_fresh_ids(viewer_id, [row[0] for row in rows]))

        cards = await self._build_cards(viewer_profile, viewer_input, ids)
        # The cards delivered are the cards consumed: a page that came up short still moved
        # the cursor to the last row it read, so nothing behind it is skipped and nothing
        # before it returns.
        advanced = last_rank != after_rank
        has_more = await self.discovery.deck_has_more(viewer_id, beyond_rank=last_rank) or (
            await self.discovery.has_unqueued_candidate(viewer_id=viewer_id, **prefs)
        )
        # The page is only delivered once: the rows it claimed are seen, and the ranking
        # that produced it is stored. Both have to survive this request.
        await self.session.commit()
        tracker.track(Event.DISCOVERY_FEED, str(viewer_id), cards=len(cards))
        return {
            "items": cards,
            "next_cursor": encode_cursor(last_rank) if advanced else None,
            "has_more": has_more,
        }


    async def get_public_profile(self, viewer_id: uuid.UUID, target_id: uuid.UUID) -> dict:
        profile = await self.users.get_profile_with_user(target_id)
        if profile is None:
            raise NotFoundError("User not found.")
        # Hiding the profile is a request to disappear, and a user id learned earlier —
        # from a card that was already on screen, or a shared link — must not keep working.
        if profile.is_hidden and viewer_id != target_id:
            raise NotFoundError("User not found.")
        if await self.social.is_blocked_either(viewer_id, target_id):
            raise NotFoundError("User not found.")
        tracker.track(Event.PROFILE_VIEWED, str(viewer_id), target=str(target_id))

        result = await self.compatibility.score_pair(viewer_id, target_id)
        photos_stmt = select(Photo).where(Photo.user_id == target_id).order_by(*PHOTO_DISPLAY_ORDER)
        photos = list((await self.session.execute(photos_stmt)).scalars().all())
        viewer_input = await self.compatibility.build_input(viewer_id)
        target_input = await self.compatibility.build_input(target_id)
        shared = sorted(viewer_input.interests & target_input.interests)
        name_by_slug = {i.slug: i.name for i in profile.interests}
        shared = [name_by_slug.get(s, s) for s in shared]

        return {
            "user_id": str(target_id),
            "name": profile.name,
            "age": profile.age,
            "city": profile.city,
            "about": profile.about,
            "dating_goal": profile.dating_goal,
            "gender": profile.gender,
            "interests": [i.name for i in profile.interests],
            "photos": [p.url for p in photos],
            "compatibility": result.overall_percent,
            "categories": [
                {
                    "category": c.key,
                    "label": c.label,
                    "score": c.percent,
                    "weight": c.weight,
                }
                for c in result.categories
            ],
            "shared_interests": shared,
        }
