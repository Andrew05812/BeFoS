"""A photograph a person uploaded is theirs to remove, to lead with, and to reorder.

Stage 99 gave the profile tab a way to send a picture; the same tab could then do nothing else with
it. `Photo.position` existed and nothing wrote it (every row stood at 0, so the display order fell
through to `created_at`), `Photo.is_primary` was set by the upload alone, and `delete_stored_photo`
was reached only when an account was purged — which left a wrong photograph, an order nobody chose,
and a picture the owner now hates all unfixable from the app.

Three routes close that, and this file pins what they promise:

* an id a caller sends is checked against the caller's own rows, never believed — a stranger's
  photograph is answered as a row that is not there (404), the way every other refusal here reads,
  because 403 would confirm that the picture exists;
* `position` and `is_primary` come from one writer over one list, so no answer can hold two leading
  photographs, a gap in the row, or a flag pointing at a photograph nobody sees;
* a write that is refused changes nothing, including the file on disk, and a write that lands is
  answered by the row the server now holds rather than by what the request asked for.

What is not covered here is the screen: the row of tiles, the arrows and the confirmation dialog are
Composable code, and nothing in this repository's Android set renders it (see the note in
`docs/VERIFICATION.md` on what the mobile row does and does not execute).
"""

from __future__ import annotations

import asyncio
import io
import os
import uuid

from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import PHOTO_DISPLAY_ORDER, Photo
from .conftest import auth_headers, complete_onboarding, register_and_auth


def _png(colour: str) -> bytes:
    picture = io.BytesIO()
    Image.new("RGB", (24, 24), colour).save(picture, format="PNG")
    return picture.getvalue()


async def _owner_with(client: AsyncClient, email: str) -> dict:
    """An account the deck is willing to show, so its own routes answer 200 rather than 404."""
    account = await register_and_auth(client, email)
    await complete_onboarding(client, account["token"], name="Хозяин")
    return account


async def _upload(client: AsyncClient, account: dict, colour: str) -> dict:
    """One photograph sent up the route that stores it; answers the leading row it was sent into."""
    response = await client.post(
        "/api/v1/users/me/photo",
        headers=auth_headers(account["token"]),
        files={"file": (f"{colour}.png", _png(colour), "image/png")},
    )
    assert response.status_code == 200, response.text
    return response.json()["photos"][0]


async def _fill(client: AsyncClient, account: dict, *colours: str) -> list[dict]:
    """The owner's row after sending each colour in turn — newest leading, as the upload route leaves it."""
    for colour in colours:
        await _upload(client, account, colour)
    return await _row(client, account)


async def _row(client: AsyncClient, account: dict) -> list[dict]:
    response = await client.get("/api/v1/users/me", headers=auth_headers(account["token"]))
    assert response.status_code == 200, response.text
    return response.json()["photos"]


def _ids(photos: list[dict]) -> list[str]:
    return [photo["id"] for photo in photos]


def _assert_one_row(photos: list[dict]) -> None:
    """The invariant every write here holds: a contiguous row, one head, and the flag on that head.

    Asserted as one fact rather than two, because the defect this guards is exactly the pair coming
    apart: a row whose `position` leads one way while `is_primary` names another photograph gives
    readers two answers to «чья фотография показана первой».
    """
    assert [photo["position"] for photo in photos] == list(range(len(photos))), (
        f"positions are not the contiguous 0..n-1 the row is read as: {photos}"
    )
    leading = [photo for photo in photos if photo["is_primary"]]
    if not photos:
        assert not leading, "a profile with no photographs still flags one as leading"
        return
    assert len(leading) == 1, f"the row claims {len(leading)} leading photographs: {photos}"
    assert leading[0]["position"] == 0, f"is_primary points away from the head of the row: {photos}"


async def test_the_owner_deletes_one_of_their_photos_and_it_leaves_their_row(
    client: AsyncClient,
) -> None:
    account = await _owner_with(client, "delete-one@befos.app")
    held = await _fill(client, account, "red", "blue")
    # The newest upload leads, so the row is [blue, red] whatever the two numbers are.
    oldest = held[-1]

    removed = await client.delete(
        f"/api/v1/users/me/photo/{oldest['id']}", headers=auth_headers(account["token"])
    )
    assert removed.status_code == 200, removed.text
    assert _ids(removed.json()["photos"]) == [held[0]["id"]], removed.json()["photos"]
    _assert_one_row(removed.json()["photos"])
    assert _ids(await _row(client, account)) == [held[0]["id"]], "the row came back with the photo"


async def test_a_removed_photograph_stops_being_a_file_the_server_hands_out(
    client: AsyncClient,
) -> None:
    """A photograph is a row and a file, and removing one of the two leaves a link that serves it.

    `/uploads` is a public static mount, so an owner who deleted an unwanted picture and was left
    with a working URL for it had not deleted anything a person with the link cannot still see.
    """
    account = await _owner_with(client, "delete-file@befos.app")
    photo = await _upload(client, account, "green")
    stored = os.path.join(settings.upload_dir, photo["url"].removeprefix("/uploads/"))
    assert os.path.exists(stored)

    deleted = await client.delete(
        f"/api/v1/users/me/photo/{photo['id']}", headers=auth_headers(account["token"])
    )
    assert deleted.status_code == 200, deleted.text
    assert not os.path.exists(stored), f"{stored} is still readable after its row was deleted"


async def test_deleting_the_leading_photo_hands_the_flag_to_the_one_behind_it(
    client: AsyncClient,
) -> None:
    account = await _owner_with(client, "delete-head@befos.app")
    held = await _fill(client, account, "red", "blue")

    deleted = await client.delete(
        f"/api/v1/users/me/photo/{held[0]['id']}", headers=auth_headers(account["token"])
    )
    assert deleted.status_code == 200, deleted.text
    photos = deleted.json()["photos"]
    _assert_one_row(photos)
    assert photos[0]["is_primary"] is True, (
        f"the photograph that took the head of the row must be the one readers are shown: {photos}"
    )


async def test_deleting_the_last_photo_leaves_the_profile_without_one(client: AsyncClient) -> None:
    account = await _owner_with(client, "delete-last@befos.app")
    photo = await _upload(client, account, "red")

    deleted = await client.delete(
        f"/api/v1/users/me/photo/{photo['id']}", headers=auth_headers(account["token"])
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["photos"] == [], "a profile whose last photograph was removed still lists one"
    _assert_one_row(deleted.json()["photos"])
    assert await _row(client, account) == []


async def test_a_photo_number_that_is_not_yours_is_refused_as_a_row_that_is_not_there(
    client: AsyncClient,
) -> None:
    """The id arrives from the caller; ownership is read off the token, and a stranger's row stays hidden.

    403 would look friendlier and be a leak: it tells the caller the photograph exists and belongs to
    somebody else. Every other refusal of a foreign row in this API answers 404, and neither person's
    row may change.
    """
    owner = await _owner_with(client, "photo-owner@befos.app")
    stranger = await _owner_with(client, "photo-stranger@befos.app")
    theirs = await _upload(client, owner, "red")
    mine = await _upload(client, stranger, "blue")

    refused = await client.delete(
        f"/api/v1/users/me/photo/{theirs['id']}", headers=auth_headers(stranger["token"])
    )
    assert refused.status_code == 404, refused.text
    assert _ids(await _row(client, stranger)) == [mine["id"]], "the refusal deleted for the stranger"
    assert _ids(await _row(client, owner)) == [theirs["id"]], "the refusal touched the owner's row"


async def test_a_photo_number_that_is_not_a_number_is_refused_before_any_row_is_read(
    client: AsyncClient,
) -> None:
    account = await _owner_with(client, "delete-uuid@befos.app")
    photo = await _upload(client, account, "red")

    garbage = await client.delete(
        "/api/v1/users/me/photo/not-a-uuid", headers=auth_headers(account["token"])
    )
    assert garbage.status_code == 422, garbage.text
    absent = await client.delete(
        f"/api/v1/users/me/photo/{uuid.uuid4()}", headers=auth_headers(account["token"])
    )
    assert absent.status_code == 404, absent.text
    assert _ids(await _row(client, account)) == [photo["id"]]


async def test_deleting_the_same_photograph_twice_answers_404_the_second_time(
    client: AsyncClient,
) -> None:
    """A double tap, or a retry over an answer that never arrived: the row must survive it whole."""
    account = await _owner_with(client, "delete-twice@befos.app")
    held = await _fill(client, account, "red", "blue")
    headers = auth_headers(account["token"])

    first = await client.delete(f"/api/v1/users/me/photo/{held[0]['id']}", headers=headers)
    assert first.status_code == 200, first.text
    second = await client.delete(f"/api/v1/users/me/photo/{held[0]['id']}", headers=headers)
    assert second.status_code == 404, second.text
    photos = await _row(client, account)
    assert _ids(photos) == [held[1]["id"]], photos
    _assert_one_row(photos)


async def test_making_a_photograph_primary_moves_it_to_the_front_and_leaves_one_flag(
    client: AsyncClient,
) -> None:
    account = await _owner_with(client, "primary-switch@befos.app")
    held = await _fill(client, account, "red", "blue", "seagreen")

    moved = await client.post(
        f"/api/v1/users/me/photo/{held[-1]['id']}/primary", headers=auth_headers(account["token"])
    )
    assert moved.status_code == 200, moved.text
    photos = moved.json()["photos"]
    assert photos[0]["id"] == held[-1]["id"], photos
    _assert_one_row(photos)
    assert _ids(await _row(client, account)) == _ids(photos), (
        "the write answered one row and the read holds another"
    )


async def test_making_a_strangers_photograph_primary_is_refused_as_a_row_that_is_not_there(
    client: AsyncClient,
) -> None:
    owner = await _owner_with(client, "primary-owner@befos.app")
    stranger = await _owner_with(client, "primary-stranger@befos.app")
    theirs = await _fill(client, owner, "red", "blue")
    mine = await _fill(client, stranger, "seagreen")

    refused = await client.post(
        f"/api/v1/users/me/photo/{theirs[0]['id']}/primary",
        headers=auth_headers(stranger["token"]),
    )
    assert refused.status_code == 404, refused.text
    assert _ids(await _row(client, stranger)) == _ids(mine)
    assert _ids(await _row(client, owner)) == _ids(theirs), "the refusal reordered the owner's row"


async def test_an_order_the_owner_names_is_the_row_every_reader_then_shows(
    client: AsyncClient,
) -> None:
    account = await _owner_with(client, "reorder@befos.app")
    held = await _fill(client, account, "red", "blue", "seagreen")
    wanted = list(reversed(_ids(held)))

    moved = await client.patch(
        "/api/v1/users/me/photo/order",
        headers=auth_headers(account["token"]),
        json={"photo_ids": wanted},
    )
    assert moved.status_code == 200, moved.text
    photos = moved.json()["photos"]
    assert _ids(photos) == wanted, f"asked for {wanted}, got {photos}"
    _assert_one_row(photos)
    assert len(photos) == len(held), "a reorder changed the size of the row"

    viewer = await register_and_auth(client, "reorder-viewer@befos.app")
    theirs = await client.get(
        f"/api/v1/users/{account['user_id']}", headers=auth_headers(viewer["token"])
    )
    assert theirs.status_code == 200, theirs.text
    # The public answer carries plain urls and paints photos[0] as the card's avatar.
    assert theirs.json()["photos"][0] == held[-1]["url"], (
        "the person swiping the deck still sees the photograph the owner moved away from the head"
    )


async def test_the_same_order_sent_twice_leaves_the_same_row(client: AsyncClient) -> None:
    account = await _owner_with(client, "reorder-twice@befos.app")
    held = await _fill(client, account, "red", "blue", "seagreen")
    wanted = list(reversed(_ids(held)))

    answers = []
    for _ in range(2):
        moved = await client.patch(
            "/api/v1/users/me/photo/order",
            headers=auth_headers(account["token"]),
            json={"photo_ids": wanted},
        )
        assert moved.status_code == 200, moved.text
        answers.append(moved.json()["photos"])
    assert _ids(answers[0]) == wanted
    assert answers[0] == answers[1], "a repeated order drifted the row instead of holding it"


async def test_an_order_that_leaves_a_photograph_out_is_refused_and_changes_nothing(
    client: AsyncClient,
) -> None:
    """Half a permutation is how the order and the flag come apart.

    Writing the two named photographs and leaving the third its old index would hand the row a
    duplicate position and a head nobody chose, so the whole request is refused and the row that
    stood before it stands after it.
    """
    account = await _owner_with(client, "reorder-short@befos.app")
    held = await _fill(client, account, "red", "blue", "seagreen")

    refused = await client.patch(
        "/api/v1/users/me/photo/order",
        headers=auth_headers(account["token"]),
        json={"photo_ids": [_ids(held)[1], _ids(held)[2]]},
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "validation_error", refused.text
    after = await _row(client, account)
    assert _ids(after) == _ids(held), "the refused order wrote the row"
    _assert_one_row(after)


async def test_an_order_naming_the_same_photograph_twice_is_refused(client: AsyncClient) -> None:
    account = await _owner_with(client, "reorder-dup@befos.app")
    held = await _fill(client, account, "red", "blue")

    refused = await client.patch(
        "/api/v1/users/me/photo/order",
        headers=auth_headers(account["token"]),
        json={"photo_ids": [_ids(held)[0], _ids(held)[0]]},
    )
    assert refused.status_code == 422, refused.text
    assert _ids(await _row(client, account)) == _ids(held)


async def test_an_order_holding_a_strangers_photograph_is_refused_as_absent(
    client: AsyncClient,
) -> None:
    owner = await _owner_with(client, "order-owner@befos.app")
    stranger = await _owner_with(client, "order-stranger@befos.app")
    theirs = await _upload(client, owner, "red")
    mine = await _fill(client, stranger, "blue", "seagreen")

    refused = await client.patch(
        "/api/v1/users/me/photo/order",
        headers=auth_headers(stranger["token"]),
        json={"photo_ids": [theirs["id"], _ids(mine)[0]]},
    )
    assert refused.status_code == 404, refused.text
    assert _ids(await _row(client, stranger)) == _ids(mine)
    assert _ids(await _row(client, owner)) == [theirs["id"]]


async def test_an_empty_order_is_refused_rather_than_read_as_a_profile_with_nothing(
    client: AsyncClient,
) -> None:
    """`[]` would be a legal full order for a profile holding no photographs and a lie for one holding three.

    Removing every photograph is what the delete route is for; an order naming none of them must not
    become a second, quieter way to empty a profile.
    """
    account = await _owner_with(client, "order-empty@befos.app")
    held = await _fill(client, account, "red", "blue")

    refused = await client.patch(
        "/api/v1/users/me/photo/order",
        headers=auth_headers(account["token"]),
        json={"photo_ids": []},
    )
    assert refused.status_code == 422, refused.text
    assert _ids(await _row(client, account)) == _ids(held)


async def test_two_writes_from_one_account_leave_one_row_rather_than_a_blend(
    client: AsyncClient,
) -> None:
    """A reorder landing next to a lead-with tap is the shape that used to corrupt the row.

    Both requests read the photograph list before either writes it, so without holding the rows the
    two renumberings interleave and the result can carry the same index twice, or none at all. Held,
    the second waits for the first's commit — and the row that stands is the row the last of the two
    answered, which is what the person who sent it was told.
    """
    account = await _owner_with(client, "order-race@befos.app")
    held = await _fill(client, account, "red", "blue", "seagreen")
    ids = _ids(held)
    headers = auth_headers(account["token"])

    reversed_order, leading_write = await asyncio.gather(
        client.patch(
            "/api/v1/users/me/photo/order", headers=headers, json={"photo_ids": ids[::-1]}
        ),
        client.post(f"/api/v1/users/me/photo/{ids[0]}/primary", headers=headers),
    )
    assert reversed_order.status_code == 200, reversed_order.text
    assert leading_write.status_code == 200, leading_write.text

    photos = await _row(client, account)
    _assert_one_row(photos)
    answers = [_ids(reversed_order.json()["photos"]), _ids(leading_write.json()["photos"])]
    assert _ids(photos) in answers, (
        f"the row stands as neither write answered it — a blend of the two: {_ids(photos)} over {answers}"
    )
    assert answers[0] != answers[1], (
        f"the two writes answered the same row, so this race proved nothing: {answers}"
    )


async def test_the_invariant_holds_through_a_sequence_of_the_three_writes(
    client: AsyncClient,
) -> None:
    """Delete, lead with, reorder — one after another on the same profile, checked at every step."""
    account = await _owner_with(client, "sequence@befos.app")
    held = await _fill(client, account, "red", "blue", "seagreen", "gold")
    headers = auth_headers(account["token"])
    _assert_one_row(held)

    removed = await client.delete(f"/api/v1/users/me/photo/{_ids(held)[-1]}", headers=headers)
    assert removed.status_code == 200, removed.text
    _assert_one_row(removed.json()["photos"])

    after_delete = _ids(removed.json()["photos"])
    lead = await client.post(
        f"/api/v1/users/me/photo/{after_delete[-1]}/primary", headers=headers
    )
    assert lead.status_code == 200, lead.text
    _assert_one_row(lead.json()["photos"])

    after_primary = _ids(lead.json()["photos"])
    moved = await client.patch(
        "/api/v1/users/me/photo/order", headers=headers, json={"photo_ids": after_primary[::-1]}
    )
    assert moved.status_code == 200, moved.text
    final = moved.json()["photos"]
    _assert_one_row(final)

    async with AsyncSessionLocal() as session:
        rows = list(
            (
                await session.execute(
                    select(Photo)
                    .where(Photo.user_id == uuid.UUID(account["user_id"]))
                    .order_by(*PHOTO_DISPLAY_ORDER)
                )
            )
            .scalars()
            .all()
        )
    assert [str(row.id) for row in rows] == _ids(final), (
        "the row the app paints is not the row the database holds"
    )
    assert [row.position for row in rows] == list(range(len(rows)))
    assert sum(1 for row in rows if row.is_primary) == 1
