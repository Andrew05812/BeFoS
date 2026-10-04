"""The media pipeline's three promises: pay only for the cap, show the chosen photo,
leave nothing behind once the account is gone.

An upload route is the only place in this API that takes bytes from a stranger and keeps
them, so each of these is pinned by a test rather than by the size of a happy-path request.
"""

from __future__ import annotations

import io
import os
import uuid

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import ValidationError
from app.models import Photo
from app.services.photo_service import read_upload_capped
from .conftest import auth_headers, register_and_auth


def _png(width: int = 40, height: int = 40, colour: str = "seagreen") -> bytes:
    picture = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(picture, format="PNG")
    return picture.getvalue()


class _ChunkedUpload:
    """The shape of Starlette's UploadFile, with a counter attached.

    A capped read is only worth something if it stops asking, so this records every call
    and hands out the body in fixed pieces the way a real stream would.
    """

    def __init__(self, payload: bytes, chunk: int) -> None:
        self._pieces = [payload[i : i + chunk] for i in range(0, len(payload), chunk)]
        self.reads = 0

    async def read(self, size: int = -1) -> bytes:
        assert size > 0, "a capped reader must ask for a bounded piece, never the whole stream"
        self.reads += 1
        return self._pieces.pop(0) if self._pieces else b""


async def test_a_body_larger_than_the_cap_is_refused_while_it_is_still_arriving() -> None:
    """`await file.read()` materialises the whole body before any limit is looked at.

    Measured on the live stack: one 60 MB upload to a route capped at 5 MB grew the
    worker's RSS by 57.3 MB before answering 422. The answer was right and the cost was
    not — thirty of those at once is the outage.
    """
    cap = 5 * 1024 * 1024
    upload = _ChunkedUpload(b"x" * (60 * 1024 * 1024), chunk=1024 * 1024)

    with pytest.raises(ValidationError):
        await read_upload_capped(upload, cap)  # type: ignore[arg-type]

    # 5 MB cap read in 1 MB pieces: it may look at one piece past the cap, not sixty.
    assert upload.reads <= 7, f"kept reading after the cap: {upload.reads} chunks"


async def test_a_body_within_the_cap_comes_through_untouched() -> None:
    upload = _ChunkedUpload(b"y" * (3 * 1024 * 1024), chunk=1024 * 1024)
    payload = await read_upload_capped(upload, 5 * 1024 * 1024)  # type: ignore[arg-type]
    assert len(payload) == 3 * 1024 * 1024


async def test_the_photo_chosen_as_primary_is_the_one_readers_see_first(
    client: AsyncClient,
) -> None:
    """Every reader of this list treats element 0 as the avatar, so `is_primary` has to
    decide it; ordering by `position` alone sorted a column that is always 0, which leaves
    the order to whatever the heap handed back."""
    owner = await register_and_auth(client, "primary-order@befos.app")
    headers = auth_headers(owner["token"])

    first = await client.post(
        "/api/v1/users/me/photo",
        headers=headers,
        files={"file": ("first.png", _png(colour="red"), "image/png")},
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        "/api/v1/users/me/photo",
        headers=headers,
        files={"file": ("second.png", _png(colour="blue"), "image/png")},
    )
    assert second.status_code == 200, second.text
    photos = second.json()["photos"]
    assert len(photos) == 2, photos
    # The flag, not the position in this very list: an assertion that reads element 0 here
    # would be comparing the ordering under test against itself.
    primary_url = next(p["url"] for p in photos if p["is_primary"])

    mine = await client.get("/api/v1/users/me", headers=headers)
    assert mine.json()["photos"][0]["url"] == primary_url, (
        "the owner's own screen must show the photo they picked"
    )

    viewer = await register_and_auth(client, "primary-viewer@befos.app")
    theirs = await client.get(
        f"/api/v1/users/{owner['user_id']}",
        headers=auth_headers(viewer["token"]),
    )
    assert theirs.status_code == 200, theirs.text
    # This route answers with plain urls; photos[0] is the avatar the card paints.
    assert theirs.json()["photos"][0] == primary_url, (
        "the card another person swipes shows photos[0] as the avatar"
    )


async def test_a_deleted_account_leaves_no_photographs_behind(client: AsyncClient) -> None:
    """The account is soft-deleted and anonymised, and the profile is hidden, so no route
    serves it — but the file stays under `/uploads`, which is a public static mount.
    A URL somebody already saw keeps working after the person is gone."""
    account = await register_and_auth(client, "photo-tombstone@befos.app")
    headers = auth_headers(account["token"])

    upload = await client.post(
        "/api/v1/users/me/photo",
        headers=headers,
        files={"file": ("photo.png", _png(), "image/png")},
    )
    assert upload.status_code == 200, upload.text
    url = upload.json()["photos"][0]["url"]
    stored = os.path.join(settings.upload_dir, url.removeprefix("/uploads/"))
    assert os.path.exists(stored)
    user_id = uuid.UUID(account["user_id"])

    deleted = await client.delete("/api/v1/users/me", headers=headers)
    assert deleted.status_code == 200, deleted.text

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(Photo).where(Photo.user_id == user_id))).scalars().all()
        assert list(rows) == [], "the photograph must not outlive the account that owns it"
    assert not os.path.exists(stored), f"{stored} is still readable after the account was deleted"
