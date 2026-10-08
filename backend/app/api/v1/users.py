from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.config import settings
from app.core.database import get_session
from app.models import PHOTO_DISPLAY_ORDER, User
from app.repositories.user_repo import UserRepository
from app.schemas.schemas import OnboardingProfile, ProfileOut, ProfileUpdate
from app.services import photo_service
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/users", tags=["users"])


def _profile_to_out(profile, photos: list) -> ProfileOut:
    return ProfileOut(
        user_id=str(profile.user_id),
        name=profile.name,
        age=profile.age,
        city=profile.city,
        gender=profile.gender,
        about=profile.about,
        dating_goal=profile.dating_goal,
        photos=[
            {"id": str(p.id), "url": p.url, "is_primary": p.is_primary, "position": p.position}
            for p in photos
        ],
        interests=[{"slug": i.slug, "name": i.name, "category": i.category} for i in profile.interests],
        lifestyle=profile.lifestyle or {},
        age_min=profile.age_min,
        age_max=profile.age_max,
        gender_preference=profile.gender_preference or [],
        is_hidden=bool(profile.is_hidden),
    )


@router.get("/me", response_model=ProfileOut)
async def get_me(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repo = UserRepository(session)
    profile = await repo.get_profile(current_user.id)
    from app.models import Photo
    from sqlalchemy import select

    photos = list(
        (await session.execute(select(Photo).where(Photo.user_id == current_user.id).order_by(*PHOTO_DISPLAY_ORDER)))
        .scalars()
        .all()
    )
    return _profile_to_out(profile, photos)


@router.post("/me/onboarding", response_model=ProfileOut)
async def complete_onboarding(
    payload: OnboardingProfile,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ProfileService(session)
    # The service hands back the row it just wrote, read back after its own commit with the
    # interests that write stored, so the answer is built from it. Asking for the profile again
    # here would read a row and a set the session is already holding.
    profile = await service.complete_onboarding(current_user.id, payload.model_dump())
    from app.models import Photo
    from sqlalchemy import select

    photos = list(
        (await session.execute(select(Photo).where(Photo.user_id == current_user.id).order_by(*PHOTO_DISPLAY_ORDER)))
        .scalars()
        .all()
    )
    return _profile_to_out(profile, photos)


@router.patch("/me", response_model=ProfileOut)
async def update_me(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ProfileService(session)
    profile = await service.update(current_user.id, payload.model_dump(exclude_unset=True))
    from app.models import Photo
    from sqlalchemy import select

    photos = list(
        (await session.execute(select(Photo).where(Photo.user_id == current_user.id).order_by(*PHOTO_DISPLAY_ORDER)))
        .scalars()
        .all()
    )
    return _profile_to_out(profile, photos)


@router.post("/me/photo", response_model=ProfileOut)
async def upload_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    file_bytes = await photo_service.read_upload_capped(file, settings.max_upload_size_bytes)
    url = await photo_service.process_and_store_upload(file_bytes, file.content_type)
    service = ProfileService(session)
    await service.add_photo(current_user.id, url, make_primary=True)
    repo = UserRepository(session)
    profile = await repo.get_profile(current_user.id)
    from app.models import Photo
    from sqlalchemy import select

    photos = list(
        (await session.execute(select(Photo).where(Photo.user_id == current_user.id).order_by(*PHOTO_DISPLAY_ORDER)))
        .scalars()
        .all()
    )
    return _profile_to_out(profile, photos)


@router.get("/interests")
async def list_interests(session: AsyncSession = Depends(get_session)):
    repo = UserRepository(session)
    interests = await repo.list_all_interests()
    return {"interests": [{"slug": i.slug, "name": i.name, "category": i.category} for i in interests]}


@router.get("/{user_id}")
async def get_public_profile(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from app.services.discovery_service import DiscoveryService

    service = DiscoveryService(session)
    return await service.get_public_profile(current_user.id, user_id)
