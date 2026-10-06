"""Adversarial reliability guards: duplicate writes under concurrency, limiter
identity, and the state an account leaves behind once it is gone.

These cases were found by deliberately breaking the app (double taps, retries,
spoofed headers, deleted accounts), not by reading the happy path.
"""
from __future__ import annotations

import asyncio
import io
import os
import struct
import time
import zlib

import pytest
from httpx import AsyncClient
from PIL import Image
from starlette.requests import Request

from app.core.config import settings
from app.core.exceptions import RateLimitedError, ValidationError
from app.core.logging import redact
from app.core.rate_limit import _MAX_KEYS, SlidingWindowRateLimiter, _client_key
from app.services.photo_service import process_and_store_upload
from app.websocket.chat_ws import parse_client_frame
from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)


def _request(headers: dict[str, str], client: tuple[str, int] = ("192.0.2.7", 51234)) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": client,
        }
    )


def test_client_key_uses_peer_address_not_forgable_header(monkeypatch) -> None:
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit.settings, "trust_proxy_headers", False)
    spoofed = _request({"x-forwarded-for": "1.2.3.4"})
    assert _client_key(spoofed) == "192.0.2.7"


def test_client_key_reads_forwarded_header_only_when_proxy_is_trusted(monkeypatch) -> None:
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit.settings, "trust_proxy_headers", True)
    assert _client_key(_request({"x-forwarded-for": "1.2.3.4, 10.0.0.1"})) == "1.2.3.4"


def test_limiter_evicts_buckets_instead_of_growing_per_identity() -> None:
    limiter = SlidingWindowRateLimiter(limit=10_000, window_seconds=60)
    for i in range(_MAX_KEYS * 2):
        limiter.check(f"key-{i}")
    assert len(limiter._hits) <= _MAX_KEYS


def test_limiter_blocks_after_the_configured_number_of_hits() -> None:
    limiter = SlidingWindowRateLimiter(limit=3, window_seconds=60)
    for _ in range(3):
        limiter.check("same-client")
    with pytest.raises(RateLimitedError):
        limiter.check("same-client")


def test_limiter_window_expires_and_frees_the_client() -> None:
    limiter = SlidingWindowRateLimiter(limit=1, window_seconds=1)
    limiter.check("same-client")
    time.sleep(1.05)
    limiter.check("same-client")


async def _pair(client: AsyncClient):
    a = await register_and_auth(client, "race-a@befos.app")
    b = await register_and_auth(client, "race-b@befos.app")
    await complete_onboarding(client, a["token"], name="А", gender="female")
    await complete_onboarding(client, b["token"], name="Б", gender="male")
    return a, b


async def test_repeated_like_is_recorded_once(client: AsyncClient) -> None:
    """A double tap sends the same like twice; it must not 500 on the unique pair."""
    a, b = await _pair(client)
    responses = await asyncio.gather(
        *[client.post(f"/api/v1/users/{b['user_id']}/like", headers=auth_headers(a["token"])) for _ in range(5)]
    )
    assert [r.status_code for r in responses] == [200] * 5
    bodies = [r.json() for r in responses]
    assert all(x["liked"] for x in bodies)
    assert not any(x["match"] for x in bodies), "one-sided likes must not announce a match"


async def test_simultaneous_mutual_likes_create_exactly_one_match(client: AsyncClient) -> None:
    a, b = await _pair(client)
    responses = await asyncio.gather(
        *[client.post(f"/api/v1/users/{b['user_id']}/like", headers=auth_headers(a["token"])) for _ in range(4)],
        *[client.post(f"/api/v1/users/{a['user_id']}/like", headers=auth_headers(b["token"])) for _ in range(4)],
    )
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses if r.status_code != 200]
    matched = [r.json() for r in responses if r.json()["match"]]
    assert len(matched) == 1, "the match moment must be announced once, not once per request"
    assert len({m["match_id"] for m in matched}) == 1

    a_matches = (await client.get("/api/v1/matches", headers=auth_headers(a["token"]))).json()["matches"]
    b_matches = (await client.get("/api/v1/matches", headers=auth_headers(b["token"]))).json()["matches"]
    assert len(a_matches) == 1 and len(b_matches) == 1


async def test_liking_an_existing_match_again_is_quiet(client: AsyncClient) -> None:
    a, b = await _pair(client)
    await client.post(f"/api/v1/users/{b['user_id']}/like", headers=auth_headers(a["token"]))
    second = await client.post(f"/api/v1/users/{a['user_id']}/like", headers=auth_headers(b["token"]))
    assert second.json()["match"] is True
    repeat = await client.post(f"/api/v1/users/{b['user_id']}/like", headers=auth_headers(a["token"]))
    assert repeat.status_code == 200
    assert repeat.json()["match"] is False, "a stale card must not fire the match dialog twice"


async def test_repeated_pass_and_block_are_recorded_once(client: AsyncClient) -> None:
    a, b = await _pair(client)
    passes = await asyncio.gather(
        *[client.post(f"/api/v1/users/{b['user_id']}/pass", headers=auth_headers(a["token"])) for _ in range(4)]
    )
    assert [p.status_code for p in passes] == [200] * 4
    blocks = await asyncio.gather(
        *[client.post(f"/api/v1/users/{b['user_id']}/block", headers=auth_headers(a["token"])) for _ in range(4)]
    )
    assert [b_.status_code for b_ in blocks] == [200] * 4


async def test_concurrent_duplicate_reports_conflict_instead_of_500(client: AsyncClient) -> None:
    a, b = await _pair(client)
    responses = await asyncio.gather(
        *[
            client.post(
                f"/api/v1/users/{b['user_id']}/report",
                headers=auth_headers(a["token"]),
                json={"reason": "spam", "details": "одинаковая жалоба"},
            )
            for _ in range(4)
        ]
    )
    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 409, 409, 409], codes


async def test_deleted_account_tokens_are_closed_out(client: AsyncClient) -> None:
    """After «Удалить аккаунт» neither the live access token nor the refresh works."""
    a = await register_and_auth(client, "gone@befos.app")
    await complete_onboarding(client, a["token"])
    deleted = await client.delete("/api/v1/users/me", headers=auth_headers(a["token"]))
    assert deleted.status_code == 200, deleted.text

    me = await client.get("/api/v1/users/me", headers=auth_headers(a["token"]))
    # 401 and not 403: the mobile client only clears its session and returns to the
    # login screen on an unauthorized response, so a 403 strands the user on «Нет доступа».
    assert me.status_code == 401, me.text
    refresh = await client.post("/api/v1/auth/refresh", json={"refresh_token": a["refresh"]})
    assert refresh.status_code == 401, refresh.text


async def test_hidden_profile_is_not_readable_by_someone_elses_id(client: AsyncClient) -> None:
    """Hiding is a request to disappear, including for an id learned before the tap."""
    a, b = await _pair(client)
    hidden = await client.post(
        "/api/v1/users/me/visibility", headers=auth_headers(a["token"]), json={"hidden": True}
    )
    assert hidden.status_code == 200, hidden.text

    peek = await client.get(f"/api/v1/users/{a['user_id']}", headers=auth_headers(b["token"]))
    assert peek.status_code == 404, peek.text
    own = await client.get(f"/api/v1/users/{a['user_id']}", headers=auth_headers(a["token"]))
    assert own.status_code == 200, own.text


async def test_delete_account_takes_the_pair_and_its_chat_with_it(client: AsyncClient) -> None:
    """An ex-partner must not keep a chat that still accepts messages."""
    a, b = await _pair(client)
    await client.post(f"/api/v1/users/{b['user_id']}/like", headers=auth_headers(a["token"]))
    match = await client.post(f"/api/v1/users/{a['user_id']}/like", headers=auth_headers(b["token"]))
    match_id = match.json()["match_id"]

    sent = await client.post(
        f"/api/v1/matches/{match_id}/messages",
        headers=auth_headers(a["token"]),
        json={"body": "привет"},
    )
    assert sent.status_code == 201, sent.text

    deleted = await client.delete("/api/v1/users/me", headers=auth_headers(a["token"]))
    assert deleted.status_code == 200, deleted.text

    b_matches = (await client.get("/api/v1/matches", headers=auth_headers(b["token"]))).json()["matches"]
    assert b_matches == []
    history = await client.get(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(b["token"])
    )
    assert history.status_code == 404, history.text


async def test_concurrent_answers_write_one_row_per_question(client: AsyncClient) -> None:
    """§4: a question answered twice by accident is still answered once."""
    a = await register_and_auth(client, "race-answers@befos.app")
    await complete_onboarding(client, a["token"])
    questions = (await client.get("/api/v1/tests", headers=auth_headers(a["token"]))).json()["questions"]
    q = questions[0]
    responses = await asyncio.gather(
        *[
            client.post(
                "/api/v1/tests/answers",
                headers=auth_headers(a["token"]),
                json={"answers": [{"question_id": q["id"], "option_id": q["options"][i % len(q["options"])]["id"]}]},
            )
            for i in range(6)
        ]
    )
    assert [r.status_code for r in responses] == [200] * 6, [r.text for r in responses if r.status_code != 200]
    progress = (await client.get("/api/v1/tests/progress", headers=auth_headers(a["token"]))).json()
    assert progress["answered"] == 1, "six taps on one question must not count as six answers"


async def test_concurrent_complete_writes_one_profile(client: AsyncClient) -> None:
    """Rapid taps of «показать результат» recompute the same profile, not two of them."""
    a = await register_and_auth(client, "race-complete@befos.app")
    await complete_onboarding(client, a["token"])
    await answer_all_questions(client, a["token"])
    responses = await asyncio.gather(
        *[client.post("/api/v1/tests/complete", headers=auth_headers(a["token"]), json={}) for _ in range(5)]
    )
    assert [r.status_code for r in responses] == [200] * 5, [r.text for r in responses if r.status_code != 200]
    shapes = {frozenset(c["category"] for c in r.json()["categories"]) for r in responses}
    assert len(shapes) == 1, "every tap must return the same categories"
    scores = {tuple(sorted((c["category"], c["score"]) for c in r.json()["categories"])) for r in responses}
    assert len(scores) == 1, "the engine must not produce two answers for one set of replies"


async def test_concurrent_onboarding_keeps_one_interest_set(client: AsyncClient) -> None:
    """§3: a second tap of «продолжить» on the last onboarding step must not 500."""
    a = await register_and_auth(client, "race-onboarding@befos.app")
    catalog = (await client.get("/api/v1/users/interests", headers=auth_headers(a["token"]))).json()["interests"]
    slugs = [i["slug"] for i in catalog][:6]
    payload = {
        "name": "Гонка", "birth_date": "1995-02-02", "city": "Москва", "gender": "female",
        "about": "Тест", "dating_goal": "relationship", "interests": slugs,
        "lifestyle": {"smoking": "never", "alcohol": "rarely", "sport": "often"},
        "age_min": 20, "age_max": 40, "gender_preference": ["male"],
    }

    async def submit() -> int:
        r = await client.post(
            "/api/v1/users/me/onboarding", json=payload, headers=auth_headers(a["token"])
        )
        return r.status_code

    codes = await asyncio.gather(*[submit() for _ in range(4)])
    assert codes == [200] * 4, codes
    me = (await client.get("/api/v1/users/me", headers=auth_headers(a["token"]))).json()
    got = [i["slug"] for i in me["interests"]]
    assert got == sorted(slugs) or set(got) == set(slugs), got
    assert len(got) == len(set(got)), "interests must not be recorded twice"


async def test_concurrent_duplicate_registration_is_a_conflict(client: AsyncClient) -> None:
    """§2: two taps of «Зарегистрироваться» with one email — one account, no 500."""
    payload = {"email": "twin@befos.app", "password": "Test12345", "password_confirm": "Test12345"}
    responses = await asyncio.gather(
        *[client.post("/api/v1/auth/register", json=payload) for _ in range(4)]
    )
    codes = sorted(r.status_code for r in responses)
    assert codes == [201, 409, 409, 409], [(r.status_code, r.text[:120]) for r in responses]


async def test_concurrent_read_receipts_are_recorded_once(client: AsyncClient) -> None:
    """Opening a chat on two devices at once must not break the receipt write."""
    a, b = await _pair(client)
    await client.post(f"/api/v1/users/{b['user_id']}/like", headers=auth_headers(a["token"]))
    match_id = (
        await client.post(f"/api/v1/users/{a['user_id']}/like", headers=auth_headers(b["token"]))
    ).json()["match_id"]
    await client.post(
        f"/api/v1/matches/{match_id}/messages", headers=auth_headers(a["token"]), json={"body": "привет"}
    )
    responses = await asyncio.gather(
        *[client.post(f"/api/v1/matches/{match_id}/read", headers=auth_headers(b["token"])) for _ in range(4)]
    )
    assert [r.status_code for r in responses] == [200] * 4, [r.text for r in responses if r.status_code != 200]
    history = await client.get(f"/api/v1/matches/{match_id}/messages", headers=auth_headers(b["token"]))
    assert all(m["is_read"] for m in history.json()["messages"]), history.json()


@pytest.mark.parametrize(
    "raw",
    ["", "{not json", "[1, 2, 3]", '"just a string"', "null", "3", None, b"message"],
)
def test_a_malformed_socket_frame_is_rejected_without_a_crash(raw) -> None:
    """One bad frame is a bad message, not a reason to drop the connection."""
    assert parse_client_frame(raw) is None


def test_a_wellformed_socket_frame_keeps_its_fields() -> None:
    assert parse_client_frame('{"type": "typing", "typing": true}') == {"type": "typing", "typing": True}


def test_the_access_log_never_carries_the_socket_token() -> None:
    """The handshake puts the access token in the query string; the log must not keep it."""
    line = ('WebSocket /ws/chat/6c352984?token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxODRkNyJ9.abc123 [accepted]')
    scrubbed = redact(line)
    assert "eyJhbGciOiJIUzI1NiJ9" not in scrubbed
    assert "token=[redacted]" in scrubbed
    assert "/ws/chat/6c352984" in scrubbed, "the request itself still has to be readable"


def test_a_logged_body_never_carries_a_password() -> None:
    scrubbed = redact('incoming {"email": "demo@befos.app", "password": "Demo12345"}')
    assert "Demo12345" not in scrubbed
    assert '"password": "[redacted]"' in scrubbed
    assert "demo@befos.app" in scrubbed


def _declared_png(width: int, height: int) -> bytes:
    """A real PNG whose IHDR is patched to declare a far larger canvas than it holds.

    The file stays a few hundred bytes, which is exactly the shape of a decompression
    bomb: cheap to send, ruinous to decode.
    """
    canvas = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(canvas, format="PNG")
    raw = bytearray(canvas.getvalue())
    raw[16:24] = struct.pack(">II", width, height)
    raw[29:33] = struct.pack(">I", zlib.crc32(bytes(raw[12:29])) & 0xFFFFFFFF)
    return bytes(raw)


@pytest.mark.parametrize(
    "width, height, expected",
    [
        # Pillow's own guard fires while the header is read, before our size check runs.
        (20000, 20000, "not a valid image"),
        # Above our cap but under Pillow's own thresholds, so our size check is the one
        # that answers rather than a library warning escaping into the log.
        (9200, 9200, "too large"),
    ],
    ids=["pillow-bomb", "over-our-cap"],
)
async def test_a_huge_declared_canvas_is_refused_as_input(width, height, expected) -> None:
    """A declared canvas is paid for in RAM: refusing it is an answer, never a 500."""
    with pytest.raises(ValidationError) as raised:
        await process_and_store_upload(_declared_png(width, height), "image/png")
    assert expected in str(raised.value).lower()


async def test_the_pixel_cap_refuses_bombs_and_not_phone_cameras() -> None:
    """63 MP is past the largest sensor on the market and well inside the cap, so the
    refusal this file raises for the same bytes has to be about the missing pixels."""
    with pytest.raises(ValidationError) as raised:
        await process_and_store_upload(_declared_png(9000, 7000), "image/png")
    assert "too large" not in str(raised.value).lower()


async def test_a_valid_photo_still_survives_the_guards() -> None:
    picture = io.BytesIO()
    Image.new("RGBA", (120, 90), (200, 40, 60, 128)).save(picture, format="PNG")
    # A picker that labels a transparent photo JPEG is ordinary input; JPEG has no alpha,
    # so the target format, not the source mode, decides how it is re-encoded.
    path = await process_and_store_upload(picture.getvalue(), "image/jpeg")
    assert path.startswith("/uploads/") and path.endswith(".jpg")
    stored = Image.open(os.path.join(settings.upload_dir, path.removeprefix("/uploads/")))
    assert stored.mode == "RGB" and max(stored.size) <= 1600

    # A full-resolution camera JPEG: downscaled during the decode, never refused.
    photo = io.BytesIO()
    Image.new("RGB", (4000, 3000), "darkorange").save(photo, format="JPEG")
    path = await process_and_store_upload(photo.getvalue(), "image/jpeg")
    stored = Image.open(os.path.join(settings.upload_dir, path.removeprefix("/uploads/")))
    assert max(stored.size) <= 1600


@pytest.mark.parametrize("content_type", ["image/png", "image/jpeg"])
async def test_truncated_bytes_answer_validation_not_internal_error(content_type) -> None:
    picture = io.BytesIO()
    Image.new("RGB", (200, 200), "steelblue").save(picture, format="PNG")
    half = picture.getvalue()[:60]
    with pytest.raises(ValidationError):
        await process_and_store_upload(half, content_type)


async def test_a_photo_upload_never_ends_the_request_with_a_500(client: AsyncClient) -> None:
    """This route receives the user's camera roll: every rejection must be an answer they can act on."""
    account = await register_and_auth(client, "photo_edges@befos.app")
    headers = auth_headers(account["token"])
    good = io.BytesIO()
    Image.new("RGB", (2400, 1800), "seagreen").save(good, format="PNG")

    cases = {
        "declared bomb": _declared_png(20000, 20000),
        "over our cap": _declared_png(9200, 9200),
        "truncated": good.getvalue()[:80],
        "not a picture at all": b"PK\x03\x04pretending to be an image",
        "empty": b"",
    }
    for name, body in cases.items():
        response = await client.post(
            "/api/v1/users/me/photo",
            headers=headers,
            files={"file": ("photo.png", body, "image/png")},
        )
        assert response.status_code == 422, (name, response.status_code, response.text)
        assert response.json()["error"]["code"] == "validation_error", name

    # The whole point of answering instead of crashing: the session is still usable after.
    ok = await client.post(
        "/api/v1/users/me/photo",
        headers=headers,
        files={"file": ("photo.png", good.getvalue(), "image/png")},
    )
    assert ok.status_code == 200, ok.text
    url = ok.json()["photos"][0]["url"]
    stored = Image.open(os.path.join(settings.upload_dir, url.removeprefix("/uploads/")))
    assert max(stored.size) <= 1600, "an oversized photo is scaled, not refused"



async def test_the_default_bucket_gates_an_ordinary_route(
    client: AsyncClient, monkeypatch
) -> None:
    """A limiter attached to nothing is a class with unit tests and no effect.

    ``_default_limiter`` was configured from ``RATE_LIMIT_PER_MINUTE`` and its window, its
    eviction and its choice of key were all pinned below — while every router except
    ``/auth`` was mounted without it, so the suite stayed green with the guard switched off
    and an authenticated loop could hit discovery, likes, uploads and messages without a
    ceiling. This asks an ordinary authenticated route rather than the class.
    """
    from app.core import rate_limit

    account = await register_and_auth(client, "bucket_wired@befos.app")
    monkeypatch.setattr(rate_limit._default_limiter, "limit", 2)
    for _ in range(2):
        ok = await client.get("/api/v1/users/me", headers=auth_headers(account["token"]))
        assert ok.status_code == 200, ok.text

    blocked = await client.get("/api/v1/users/me", headers=auth_headers(account["token"]))
    assert blocked.status_code == 429, blocked.text
    assert blocked.json()["error"]["code"] == "rate_limited"


async def test_health_keeps_answering_while_the_rest_of_the_api_is_throttled(
    client: AsyncClient, monkeypatch
) -> None:
    """The one route left unthrottled, and on purpose.

    A load balancer or a monitor that gets a 429 reports the service as down, so a busy
    minute turns into an outage nobody caused. Pinning the carve-out also stops it from
    being "fixed" by whoever wires the routers up next.
    """
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit._default_limiter, "limit", 1)
    for _ in range(3):
        assert (await client.get("/api/v1/health")).status_code == 200


async def test_the_database_probe_is_throttled_apart_from_liveness(
    client: AsyncClient, monkeypatch
) -> None:
    """A probe that borrows a connection cannot keep the free pass the plain one has.

    ``/health/db`` reads the pool that authenticated traffic shares, so an anonymous loop
    against it is a way to starve the app while asking it nothing. The two buckets stay
    separate on purpose: the ceiling on the expensive probe must not turn a busy minute
    into a false "service down" for the cheap one.
    """
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit._probe_limiter, "limit", 2)
    for _ in range(2):
        answered = await client.get("/api/v1/health/db")
        # 200 or 503 both mean the probe was allowed to ask; only a 429 means it was not.
        assert answered.status_code in (200, 503), answered.text

    refused = await client.get("/api/v1/health/db")
    assert refused.status_code == 429, refused.text
    assert (await client.get("/api/v1/health")).status_code == 200, (
        "the probe's ceiling must not become an outage for the process as a whole"
    )


async def test_socket_handshakes_are_bounded_per_address(
    client: AsyncClient, monkeypatch
) -> None:
    """Every handshake costs two row reads, so the door itself needs a ceiling.

    The REST limiter never sees a socket: the connection is established once and then
    writes freely. Without a limit at the door, a script can hold the app in a loop of
    authentication and room joins without ever sending a message.
    """
    import uuid

    from app.core import rate_limit
    from app.websocket.chat_ws import chat_socket
    from .test_chat_idempotency import FakeSocket, _close, _open, _wait_until
    from .test_idor_authorization import _matched_pair

    a, _, match_id = await _matched_pair(client)
    monkeypatch.setattr(rate_limit._ws_handshake_limiter, "limit", 1)

    # The accepted socket has to be driven as a task: it enters its read loop and stays
    # there, and an awaited handler would never return to ask the second question.
    first = FakeSocket()
    task = await _open(first, match_id, a["token"])
    assert first.accepted is True, "the first handshake of the minute is the room's own"
    try:
        second = FakeSocket()
        await chat_socket(second, uuid.UUID(match_id), token=a["token"])
        assert second.closed_code == 1008, second.sent
        assert second.accepted is False
        assert second.sent == [], "a refused handshake sends nothing into the room"
    finally:
        await _close(first, task)


async def test_a_socket_cannot_write_past_its_frame_budget(
    client: AsyncClient, monkeypatch
) -> None:
    """The budget counts frames, not requests, and it answers with an error rather than a drop.

    A client that is simply too fast is not a policy violation, so the socket stays open and
    is told to slow down; a client that is ignored would just retry into the same wall.
    """
    import uuid as uuid_module

    from app.core import rate_limit
    from app.websocket.chat_ws import chat_socket
    from .test_chat_idempotency import FakeSocket, _wait_until
    from .test_idor_authorization import _matched_pair

    a, _, match_id = await _matched_pair(client)
    monkeypatch.setattr(rate_limit._ws_frame_limiter, "limit", 1)

    socket = FakeSocket()
    task = asyncio.create_task(
        chat_socket(socket, uuid_module.UUID(match_id), token=a["token"])
    )
    assert await _wait_until(lambda: socket.accepted)
    try:
        # The first frame spends the minute's single slot and is answered with silence: a
        # typing signal goes to the peer and is never echoed back to whoever sent it. The
        # second is over budget, and the only frame this socket may then receive is the
        # instruction to slow down.
        socket.incoming.put_nowait({"type": "typing"})
        socket.incoming.put_nowait({"type": "typing"})
        assert await _wait_until(
            lambda: any(f.get("type") == "error" for f in socket.sent)
        ), socket.sent
        assert all(f.get("type") == "error" for f in socket.sent), socket.sent
        assert "slow down" in socket.sent[0]["message"].lower(), socket.sent
        assert socket.closed_code is None, "over budget is a wait, not a hanging up"
    finally:
        socket.incoming.put_nowait(None)
        await asyncio.wait_for(task, timeout=5.0)
