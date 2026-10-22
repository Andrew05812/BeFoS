from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_session_id, get_current_user
from app.core.config import settings
from app.core.database import get_session
from app.models import PHOTO_DISPLAY_ORDER, Photo, User
from app.repositories.user_repo import UserRepository
from app.schemas.schemas import (
    OnboardingProfile,
    PhotoOrderUpdate,
    ProfileOut,
    ProfileUpdate,
)
from app.services import photo_service
from app.services.export_service import ExportService
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/users", tags=["users"])


def _profile_to_out(profile, photos: list, is_moderator: bool) -> ProfileOut:
    return ProfileOut(
        user_id=str(profile.user_id),
        is_moderator=bool(is_moderator),
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
        city_preference=profile.city_preference,
        is_hidden=bool(profile.is_hidden),
    )


async def _owner_answer(
    session: AsyncSession, user_id: uuid.UUID, is_moderator: bool
) -> ProfileOut:
    """What every write to this profile answers with: the profile and the photograph row as left.

    The row is read back rather than assembled from what the write was asked to do, so a person
    moving or removing a picture sees the order the server actually holds — including the flag that
    moved to the next photograph when the leading one was removed. The role is not read here: the
    caller already holds the account row that `get_current_user` loaded, and asking for it again
    would pay a second SELECT per write to answer one word.
    """
    repo = UserRepository(session)
    photos = list(
        (
            await session.execute(
                select(Photo).where(Photo.user_id == user_id).order_by(*PHOTO_DISPLAY_ORDER)
            )
        )
        .scalars()
        .all()
    )
    return _profile_to_out(await repo.get_profile(user_id), photos, is_moderator)


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
    return _profile_to_out(profile, photos, current_user.is_moderator)


@router.get("/me/export")
async def export_account(
    current_user: User = Depends(get_current_user),
    current_session_id: uuid.UUID | None = Depends(get_current_session_id),
    session: AsyncSession = Depends(get_session),
):
    """Everything this account wrote, in one file it can keep.

    The door exists because of the one beside it: `DELETE /users/me` anonymises the profile, deletes
    the photographs and the files behind them, drops the questionnaire, the scored profile, the deck
    and the whole social graph, and nothing brings them back. Before that tap there was no verb in
    this API by which a person could read their own life out of the app they are leaving, so the
    choice on the settings screen was between staying and losing.

    `Content-Disposition` names a file rather than a page: this answer is not something to render, it
    is something to keep. Nothing in the body names a caller — the bearer token already said whose —
    and `counts` answers with the rows that stand even when `limits.truncated` names a section the
    ceiling cut, so the file cannot describe itself as complete while it is holding part of a list.
    """
    document = await ExportService(session).build(current_user, current_session_id)
    filename = f"befos-account-{current_user.id}.json"
    return JSONResponse(
        content=jsonable_encoder(document),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    return _profile_to_out(profile, photos, current_user.is_moderator)


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
    return _profile_to_out(profile, photos, current_user.is_moderator)


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
    return _profile_to_out(profile, photos, current_user.is_moderator)


@router.delete("/me/photo/{photo_id}", response_model=ProfileOut)
async def delete_photo(
    photo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ProfileService(session)
    url = await service.delete_photo(current_user.id, photo_id)
    # The row is committed and gone, so the file it named belongs to nobody now. Removing it after
    # the commit is what keeps a refused delete — a stranger's number, an absent one — from
    # destroying a photograph that is still in somebody's list.
    photo_service.delete_stored_photo(url)
    return await _owner_answer(session, current_user.id, current_user.is_moderator)


@router.post("/me/photo/{photo_id}/primary", response_model=ProfileOut)
async def make_photo_primary(
    photo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ProfileService(session)
    await service.set_primary_photo(current_user.id, photo_id)
    return await _owner_answer(session, current_user.id, current_user.is_moderator)


@router.patch("/me/photo/order", response_model=ProfileOut)
async def reorder_photos(
    payload: PhotoOrderUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ProfileService(session)
    await service.reorder_photos(current_user.id, payload.photo_ids)
    return await _owner_answer(session, current_user.id, current_user.is_moderator)


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
