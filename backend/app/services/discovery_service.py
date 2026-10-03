from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.tracker import Event, tracker
from app.core.exceptions import NotFoundError
from app.models import Like, Match, Pass, Photo, Profile
from app.repositories.social_repo import DiscoveryRepository, SocialRepository
from app.repositories.user_repo import UserRepository
from app.services.compatibility_service import CompatibilityService


def _highlight(viewer_profile: Profile, profile: Profile, shared_slugs: set[str], result) -> str | None:
    """One-line, data-derived answer to 'why is this person shown to me?'."""
    names = [i.name for i in profile.interests if i.slug in shared_slugs]
    if len(names) >= 2:
        return "Общие интересы: " + ", ".join(names[:3])
    if len(names) == 1:
        # Label form, not a sentence: "нравится" would disagree with a plural
        # interest name ("Иностранные языки"), and we cannot inflect for number here.
        return f"Общий интерес: «{names[0]}»"
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

    async def _excluded_ids(self, viewer_id: uuid.UUID) -> set[uuid.UUID]:
        excluded: set[uuid.UUID] = set()
        for model, col in ((Like, Like.from_user_id), (Pass, Pass.from_user_id)):
            stmt = select(model.to_user_id).where(col == viewer_id)
            excluded |= {row[0] for row in (await self.session.execute(stmt)).all()}
        stmt = select(Match.user_a_id, Match.user_b_id).where(
            (Match.user_a_id == viewer_id) | (Match.user_b_id == viewer_id)
        )
        for a, b in (await self.session.execute(stmt)).all():
            excluded.add(a if a != viewer_id else b)
        excluded |= await self.social.list_blocked_ids(viewer_id)
        excluded.add(viewer_id)
        return excluded

    async def feed(self, viewer_id: uuid.UUID, *, limit: int = 20, offset: int = 0, city_override: str | None = None) -> dict:
        viewer_profile = await self.users.get_profile(viewer_id)
        if viewer_profile is None:
            raise NotFoundError("Complete your profile before discovering people.")

        excluded = await self._excluded_ids(viewer_id)
        city = city_override if city_override is not None else (viewer_profile.city_preference or None)
        gender_pref = viewer_profile.gender_preference or []
        age_min = viewer_profile.age_min
        age_max = viewer_profile.age_max

        # Fetch a wider pool so we can sort by compatibility, then paginate.
        pool_ids = await self.discovery.candidate_ids(
            viewer_id=viewer_id,
            gender_pref=gender_pref,
            age_min=age_min,
            age_max=age_max,
            city=city,
            exclude_ids=excluded,
            limit=max(limit * 5, 50),
            offset=0,
        )
        total = await self.discovery.total_candidates(
            viewer_id=viewer_id,
            gender_pref=gender_pref,
            age_min=age_min,
            age_max=age_max,
            city=city,
            exclude_ids=excluded,
        )

        viewer_input = await self.compatibility.build_input(viewer_id)
        # Batch-load everything the cards need: one query per concern, not per candidate.
        profiles = {
            p.user_id: p
            for p in await self.users.get_profiles_by_ids(pool_ids)
        }
        photos = await self.users.get_primary_photos(pool_ids)
        comp_profiles = await self.compatibility.tests.get_compatibility_profiles(pool_ids)

        cards = []
        for cand_id in pool_ids:
            profile = profiles.get(cand_id)
            if profile is None:
                continue
            cand_input = CompatibilityService.input_from(profile, comp_profiles.get(cand_id))
            from app.compatibility.engine import compute_compatibility

            result = compute_compatibility(viewer_input, cand_input, self.compatibility.weight_config)
            photo = photos.get(cand_id)
            shared_slugs = viewer_input.interests & cand_input.interests
            shared = len(shared_slugs)
            cards.append(
                {
                    "user_id": str(cand_id),
                    "name": profile.name,
                    "age": profile.age,
                    "city": profile.city,
                    "about": profile.about,
                    "dating_goal": profile.dating_goal,
                    "photo_url": photo.url if photo else None,
                    "interests": [i.name for i in profile.interests][:8],
                    "compatibility": result.overall_percent,
                    "shared_interests_count": shared,
                    "highlight": _highlight(viewer_profile, profile, shared_slugs, result),
                }
            )

        cards.sort(key=lambda c: c["compatibility"], reverse=True)
        page = cards[offset : offset + limit]
        return {
            "items": page,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < len(cards),
        }

    async def get_public_profile(self, viewer_id: uuid.UUID, target_id: uuid.UUID) -> dict:
        profile = await self.users.get_profile_with_user(target_id)
        if profile is None:
            raise NotFoundError("User not found.")
        if await self.social.is_blocked_either(viewer_id, target_id):
            raise NotFoundError("User not found.")
        tracker.track(Event.PROFILE_VIEWED, str(viewer_id), target=str(target_id))

        result = await self.compatibility.score_pair(viewer_id, target_id)
        photos_stmt = select(Photo).where(Photo.user_id == target_id).order_by(Photo.position)
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
