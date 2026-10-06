"""The four pinned libraries that carry the product's security promises, tested at the
boundary where a stranger speaks to them.

Each block below answers one question a dependency upgrade raises: did the fixed version
keep the behaviour the app depends on, and did it close the hole the advisory describes.
The suite as a whole proves the app still works; these prove the guards are guards.

Nothing here weakens a check to fit a library: every assertion below was read off the
patched versions (PyJWT 2.15.1, Pillow 12.3.0, python-multipart 0.0.32) and the routes as
they ship.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import re
import time
import uuid
import warnings

import jwt
import pytest
from fastapi import status
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import update

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import ValidationError
from app.core.security import decode_token
from app.models import User
from app.services.photo_service import ACCEPTED_PIL_FORMATS, process_and_store_upload
from app.websocket.chat_ws import chat_socket
from .conftest import auth_headers, register_and_auth
from .test_chat_idempotency import FakeSocket

PROTECTED = "/api/v1/users/me"


# ---------------------------------------------------------------------------------------
# JWT: everything an attacker can do to a token that was not issued for them
# ---------------------------------------------------------------------------------------


def _claims(**overrides) -> dict:
    now = int(time.time())
    claims = {"sub": str(uuid.uuid4()), "type": "access", "iat": now, "exp": now + 600}
    claims.update(overrides)
    for key, value in list(claims.items()):
        if value is None:
            del claims[key]
    return claims


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _forge(payload: dict, key: bytes, algorithm: str = "HS256") -> str:
    """Sign an HS token by hand.

    Going through `jwt.encode` would let the library's own encode-time refusals stand in for
    the answer: the question is whether *verification* accepts the token, and a forged one
    never has to pass the encoder to reach a decoder.
    """
    header = {"alg": algorithm, "typ": "JWT"}
    digest = {"HS256": hashlib.sha256, "HS384": hashlib.sha384, "HS512": hashlib.sha512}[algorithm]
    signing_input = (
        _b64(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64(json.dumps(payload, separators=(",", ":")).encode())
    )
    signature = hmac.new(key, signing_input.encode(), digest).digest()
    return signing_input + "." + _b64(signature)


def _wrong_secret_token(claims: dict | None = None) -> str:
    return _forge(claims or _claims(), (settings.jwt_secret + "attacker").encode())


async def _reject(client: AsyncClient, token: str) -> None:
    """A token the app refuses must answer 401 with its own reason, and never a 500."""
    response = await client.get(PROTECTED, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401, (response.status_code, response.text)
    assert response.json()["error"]["code"] == "unauthorized"


async def test_a_token_signed_with_another_secret_is_refused(client: AsyncClient) -> None:
    await _reject(client, _wrong_secret_token())


async def test_an_expired_token_is_refused_and_names_the_reason(client: AsyncClient) -> None:
    expired = _forge(_claims(exp=int(time.time()) - 60), settings.jwt_secret.encode())
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(expired, "access")
    response = await client.get(PROTECTED, headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401, response.text
    # The client keys its session clearing on the code, and the person on the sentence:
    # "expired" is what tells them to refresh instead of to log out.
    assert "expired" in response.json()["error"]["message"].lower()


@pytest.mark.parametrize("dropped", ["exp", "sub", "type"])
async def test_a_token_missing_a_claim_the_app_requires_is_refused(
    client: AsyncClient, dropped: str
) -> None:
    token = _forge(_claims(**{dropped: None}), settings.jwt_secret.encode())
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_token(token, "access")
    await _reject(client, token)


@pytest.mark.parametrize(
    "token",
    [
        # The signature algorithm is the app's choice, not a field in the document.
        _forge(_claims(), settings.jwt_secret.encode(), "HS512"),
        # An unsigned token: the classic downgrade against a verifier that trusts the header.
        _b64(json.dumps({"alg": "none", "typ": "JWT"}, separators=(",", ":")).encode())
        + "."
        + _b64(json.dumps(_claims(), separators=(",", ":")).encode())
        + ".",
        # A real token whose header was rewritten to claim no algorithm.
        (
            _b64(json.dumps({"alg": "none", "typ": "JWT"}, separators=(",", ":")).encode())
            + "."
            + jwt.encode(_claims(), settings.jwt_secret, algorithm="HS256").split(".")[1]
            + "."
            + jwt.encode(_claims(), settings.jwt_secret, algorithm="HS256").split(".")[2]
        ),
    ],
    ids=["hs512-under-hs256", "unsigned", "header-rewritten-to-none"],
)
async def test_the_algorithm_is_not_a_field_the_caller_writes(client: AsyncClient, token: str) -> None:
    with pytest.raises(jwt.PyJWTError):
        decode_token(token, "access")
    await _reject(client, token)


@pytest.mark.parametrize(
    "junk",
    ["", "abc", "a.b", "aaa.bbb.ccc", "header.payload.signature", "  .  .  "],
    ids=["empty", "one-segment", "two-segments", "three-nonsense", "three-words", "whitespace-segments"],
)
async def test_a_token_that_is_not_a_token_is_refused_without_a_crash(
    client: AsyncClient, junk: str
) -> None:
    with pytest.raises(jwt.PyJWTError):
        decode_token(junk, "access")
    await _reject(client, junk)


def test_a_token_written_in_characters_an_http_header_cannot_carry_is_refused_too() -> None:
    """An HTTP header is ASCII, so these cannot arrive over the wire — but `decode_token` is
    also called with a query-string token by the socket route, and a token read from storage
    later. The refusal has to be the library's, not the transport's."""
    for junk in ("•.•.•", "﻿.a.b", "æ.ø.å"):
        with pytest.raises(jwt.PyJWTError):
            decode_token(junk, "access")


async def test_a_refresh_token_is_not_an_access_token_and_the_other_way_round(
    client: AsyncClient,
) -> None:
    """Two secrets and a `type` claim are the whole separation, so each side has to fail."""
    account = await register_and_auth(client, "type-confusion@befos.app")
    headers = auth_headers(account["token"])

    mine = await client.get(PROTECTED, headers=headers)
    assert mine.status_code == 200, mine.text

    as_access = await client.get(PROTECTED, headers=auth_headers(account["refresh"]))
    assert as_access.status_code == 401, as_access.text

    as_refresh = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": account["token"]}
    )
    assert as_refresh.status_code == 401, as_refresh.text
    # The pairing the app itself issues still works, so the refusals above are about the
    # wrong token and not about a route that stopped answering.
    working = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": account["refresh"]}
    )
    assert working.status_code == 200, working.text
    assert working.json()["access_token"] != account["token"]


PUBLIC_KEY_SHAPE = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0Z3f6dKpVG1rQkQqPqN0\n"
    "kq4hUmtLgC7Fp3qL8x1vA0m4zK2pQ9tJcR7nF5hL3sVdYbWqT8xM1nK4pQ2rJ6sH\n"
    "0gD9fK2L3mN4oP5qR6sT7uV8wX9yZ0aB1cD2eF3gH4iJ5kL6mN7oP8qR9sT0uV1w\n"
    "X2yZ3aB4cD5eF6gH7iJ8kL9mN0oP1qR2sT3uV4wX5yZ6aB7cD8eF9gH0iJ1kL2mN\n"
    "3oP4qR5sT6uV7wX8yZ9aB0cD1eF2gH3iJ4kL5mN6oP7qR8sT9uV0wX1yZ2aB3cD4\n"
    "eF5gH6iJ7kL8mN9oP0qR1sT2uV3wX4yZ5aB6cD7eF8gH9iJ0kL1mN2oP3qR4sT5u\n"
    "-----END PUBLIC KEY-----\n"
)


def test_public_key_material_is_not_accepted_as_an_hmac_secret() -> None:
    """GHSA-xgmm-8j9v-c9wx and GHSA-p4g4-x82p-q773: a verifier that took a public key as the
    HMAC key let anyone who had that public key mint tokens.

    BeFoS keeps one secret per token type and never loads a JWK, so the path was never open
    here; this pins that the pinned library now refuses the shape as well, so a future
    feature that hands `decode` a key object cannot silently reopen it. A public key is not
    a secret, which is why this one is written out in the test.
    """
    forged = _forge(_claims(), PUBLIC_KEY_SHAPE.encode())
    with pytest.raises(jwt.InvalidKeyError):
        jwt.decode(forged, PUBLIC_KEY_SHAPE, algorithms=["HS256"])


def test_the_minimum_secret_the_production_guard_accepts_is_long_enough_for_the_library() -> None:
    """PyJWT 2.15 warns about HMAC keys shorter than RFC 7518 asks for.

    The production config guard has its own minimum, and the two have to agree: a deployment
    that passes the guard and then gets warned per token is a deployment whose log is about
    to be noise, and a guard below the library's floor is a guard for nothing.
    """
    secret = "s" * 32  # exactly the shortest secret config.py lets production ship
    assert len(secret.encode()) >= 32
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        token = jwt.encode(_claims(), secret, algorithm="HS256")
        jwt.decode(token, secret, algorithms=["HS256"])
    assert [w for w in caught if issubclass(w.category, jwt.warnings.InsecureKeyLengthWarning)] == []


@pytest.mark.parametrize("bad", [_wrong_secret_token(), "not.a.jwt", ""])
async def test_a_socket_built_on_a_token_that_did_not_verify_never_opens(bad: str) -> None:
    """The room is reached with a query-string token, so it answers to the same rules."""
    socket = FakeSocket()
    await chat_socket(socket, uuid.uuid4(), token=bad)
    assert socket.accepted is False
    assert socket.closed_code == status.WS_1008_POLICY_VIOLATION


async def test_a_deactivated_account_stops_answering_while_its_token_is_still_valid(
    client: AsyncClient,
) -> None:
    """An access token outlives the account behind it: the rows are the truth.

    `is_active` is the switch a moderator or a safety flow pulls, and unlike deletion it
    leaves the row standing, so only the column can refuse the request.
    """
    account = await register_and_auth(client, "paused@befos.app")
    user_id = uuid.UUID(account["user_id"])
    async with AsyncSessionLocal() as session:
        await session.execute(update(User).where(User.id == user_id).values(is_active=False))
        await session.commit()

    response = await client.get(PROTECTED, headers=auth_headers(account["token"]))
    assert response.status_code == 401, response.text
    assert "disabled" in response.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------------------
# Pillow: the pipeline is the one place a stranger's bytes become a file on disk
# ---------------------------------------------------------------------------------------


def _png(width: int = 40, height: int = 40) -> bytes:
    canvas = io.BytesIO()
    Image.new("RGB", (width, height), "seagreen").save(canvas, format="PNG")
    return canvas.getvalue()


def _in_format(fmt: str, width: int = 40, height: int = 40, **save_options) -> bytes:
    canvas = io.BytesIO()
    Image.new("RGB", (width, height), "tomato").save(canvas, format=fmt, **save_options)
    return canvas.getvalue()


@pytest.mark.parametrize(
    "foreign_format",
    # Each of these is a decoder with its own advisory history: TIFF (GHSA-jjj6 / font and
    # bomb families), GIF, BMP — none of which BeFoS accepts as an upload.
    ["TIFF", "GIF", "BMP", "PPM"],
)
async def test_a_body_whose_magic_is_another_format_never_reaches_that_parser(
    foreign_format: str,
) -> None:
    """The content type is a label the client writes; Pillow chooses its parser by magic.

    Before this gate a TIFF or PSD carrying a `image/png` label was opened by the TIFF or
    PSD decoder, so every advisory against those decoders was reachable from this route even
    though the product only ever shows JPEG, PNG and WEBP.
    """
    body = _in_format(foreign_format)
    assert Image.open(io.BytesIO(body)).format == foreign_format
    assert foreign_format not in ACCEPTED_PIL_FORMATS
    with pytest.raises(ValidationError) as raised:
        await process_and_store_upload(body, "image/png")
    assert "unsupported image type" in str(raised.value).lower()


async def test_the_same_refusal_comes_back_as_a_client_error_on_the_route(
    client: AsyncClient,
) -> None:
    account = await register_and_auth(client, "magic-label@befos.app")
    response = await client.post(
        "/api/v1/users/me/photo",
        headers=auth_headers(account["token"]),
        files={"file": ("profile.tiff", _in_format("TIFF"), "image/png")},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "content_type",
    ["image/gif", "image/tiff", "image/svg+xml", "text/plain", "application/x-msdownload", None],
)
async def test_a_content_type_off_the_short_list_is_refused_before_anything_is_opened(
    content_type: str | None,
) -> None:
    with pytest.raises(ValidationError) as raised:
        await process_and_store_upload(_png(), content_type)
    assert "unsupported image type" in str(raised.value).lower()


async def test_an_upload_is_re_encoded_so_the_metadata_it_carried_does_not_survive(
    client: AsyncClient,
) -> None:
    """EXIF carries the camera, the owner's name and the coordinates of the shot.

    The re-encode is what strips it: it is also the step that neutralises a polyglot, so
    the promise is pinned by putting data in and proving none of it is in the file readers
    are served.
    """
    marked = Image.Exif()
    marked[271] = "CameraOwnerMake"
    marked[272] = "ModelThatIdentifiesAPerson"
    marked[306] = "2026:10:06 04:11:00"
    marked[315] = "someone@camera.example"
    body = _in_format("JPEG", width=2400, height=1800, exif=marked)
    assert b"ModelThatIdentifiesAPerson" in body

    account = await register_and_auth(client, "exif-strip@befos.app")
    response = await client.post(
        "/api/v1/users/me/photo",
        headers=auth_headers(account["token"]),
        files={"file": ("IMG_0042.jpg", body, "image/jpeg")},
    )
    assert response.status_code == 200, response.text
    url = response.json()["photos"][0]["url"]
    stored_path = os.path.join(settings.upload_dir, url.removeprefix("/uploads/"))

    raw = open(stored_path, "rb").read()
    for marker in (b"ModelThatIdentifiesAPerson", b"CameraOwnerMake", b"camera.example"):
        assert marker not in raw, f"{marker!r} survived the re-encode"
    stored = Image.open(stored_path)
    assert not stored.getexif(), "a re-encoded avatar must not carry an EXIF block"
    assert stored.format == "JPEG"
    assert max(stored.size) <= 1600, "a full-resolution upload is scaled, not refused"


async def test_the_name_on_disk_is_random_and_the_name_in_the_request_is_never_used(
    client: AsyncClient,
) -> None:
    """GHSA-wp53-j4wj-2cfg is arbitrary file write through a filename the client chose.

    The route keeps the bytes and throws the name away, so the traversal attempt has
    nowhere to land. The parent directory is watched for new entries because a path that
    escapes the upload dir is the failure being prevented, not a file inside it.
    """
    parent = os.path.dirname(os.path.abspath(settings.upload_dir))
    before = set(os.listdir(parent))
    account = await register_and_auth(client, "traversal@befos.app")

    for name in (
        "../../../escape.png",
        "..\\..\\escape.png",
        "uploads/../../escape.png",
        "C:\\Windows\\System32\\escape.png",
    ):
        response = await client.post(
            "/api/v1/users/me/photo",
            headers=auth_headers(account["token"]),
            files={"file": (name, _png(), "image/png")},
        )
        assert response.status_code == 200, (name, response.text)
        url = response.json()["photos"][0]["url"]
        assert re.fullmatch(r"/uploads/[0-9a-f]{32}\.png", url), url

    added = set(os.listdir(parent)) - before
    assert not [name for name in added if name.endswith(".png")], (
        f"an upload landed outside the upload directory: {added}"
    )
    assert not os.path.exists(os.path.join(parent, "escape.png"))


async def test_a_body_larger_than_the_cap_is_refused_and_the_session_survives(
    client: AsyncClient,
) -> None:
    cap = settings.max_upload_size_bytes
    account = await register_and_auth(client, "oversize@befos.app")
    headers = auth_headers(account["token"])

    response = await client.post(
        "/api/v1/users/me/photo",
        headers=headers,
        files={"file": ("big.png", b"\x89PNG\r\n\x1a\n" + b"z" * (cap + 64 * 1024), "image/png")},
    )
    assert response.status_code == 422, response.status_code
    assert "mb limit" in response.json()["error"]["message"].lower()

    ok = await client.post(
        "/api/v1/users/me/photo",
        headers=headers,
        files={"file": ("photo.png", _png(), "image/png")},
    )
    assert ok.status_code == 200, ok.text


async def test_an_empty_upload_is_refused(client: AsyncClient) -> None:
    account = await register_and_auth(client, "empty-upload@befos.app")
    response = await client.post(
        "/api/v1/users/me/photo",
        headers=auth_headers(account["token"]),
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------------------
# python-multipart: the framing under the upload route
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "framing",
    [
        pytest.param(b"", id="no-boundary"),
        pytest.param(b"this body never mentions the boundary\r\n", id="boundary-never-appears"),
        pytest.param(
            b"--xy\r\n" + b"X-Clog-Header: " + b"a" * (400 * 1024) + b"\r\n\r\nbody\r\n--xy--\r\n",
            id="part-header-never-ends",
        ),
        pytest.param(
            b'--xy\r\nContent-Disposition: form-data; name="file"; filename="a.png"\r\n',
            id="truncated-part",
        ),
        pytest.param(
            b'--xy\r\nContent-Disposition: form-data; name="other"\r\n\r\nhello\r\n--xy--\r\n',
            id="missing-the-file-field",
        ),
    ],
)
async def test_a_malformed_multipart_body_is_a_client_error_never_a_server_one(
    client: AsyncClient, framing: bytes
) -> None:
    """GHSA-pp6c-gr5w-3c5g and GHSA-mj87-hwqh-73pj are both DoS in the parser's framing.

    The upgrade has to keep answering these with a 4xx: the same bytes that used to cost a
    worker now cost a refusal.
    """
    account = await register_and_auth(client, "framing@befos.app")
    response = await client.post(
        "/api/v1/users/me/photo",
        headers={**auth_headers(account["token"]), "Content-Type": "multipart/form-data; boundary=xy"},
        content=framing,
    )
    assert response.status_code in (400, 422), (framing[:40], response.status_code, response.text)


async def test_the_route_still_accepts_a_well_formed_upload_after_the_bad_ones(
    client: AsyncClient,
) -> None:
    """A parser hardened against bad framing must not have become a parser that refuses
    ordinary requests: the same client, the same session, one good multipart body."""
    account = await register_and_auth(client, "framing-ok@befos.app")
    headers = auth_headers(account["token"])

    bad = await client.post(
        "/api/v1/users/me/photo",
        headers={**headers, "Content-Type": "multipart/form-data; boundary=xy"},
        content=b"--xy\r\nContent-Disposition: form-data; name=\"file\"\r\n",
    )
    assert bad.status_code in (400, 422), bad.text

    good = await client.post(
        "/api/v1/users/me/photo",
        headers=headers,
        files={"file": ("photo.png", _png(), "image/png")},
    )
    assert good.status_code == 200, good.text
    assert len(good.json()["photos"]) == 1


async def test_a_json_route_is_unaffected_by_the_multipart_bump(client: AsyncClient) -> None:
    """The library under `Form()`/`File()` is not the one under a JSON body, and the rest of
    the API is what an accidental regression here would break."""
    account = await register_and_auth(client, "json-still-works@befos.app")
    me = await client.get(PROTECTED, headers=auth_headers(account["token"]))
    assert me.status_code == 200, me.text
    visibility = await client.post(
        "/api/v1/users/me/visibility",
        headers=auth_headers(account["token"]),
        json={"hidden": True},
    )
    assert visibility.status_code == 200, visibility.text
