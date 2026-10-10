"""A request that burns CPU on the event loop charges that time to everybody on the worker.

The app serves from one uvicorn worker, so one loop carries every request on it. Two paths used
to spend synchronous CPU work there directly: bcrypt at `rounds=12`, and the Pillow re-encode of
an uploaded photo. Measured on one machine, a hash or a verify held the loop for 451-462 ms and a
3024x4032 JPEG for 427-549 ms, and a bystander coroutine that asked to wake every 5 ms recorded
its longest wait as the whole duration of the request it lived through — the loop ran nothing else
meanwhile. Both paths now hand the work to a worker thread, and the same bystander comes back at
16-28 ms against an idle floor of 15.7 ms on that machine.

What these checks assert is the shape of the wait, not its size: off the loop the bystander's
longest gap is a fraction of the call it waited through, on the loop it is the call. The ceiling is
deliberately generous, so a slower CI runner moves the duration of the subject and not the verdict.
That leaves the answer itself unproven here: the last check in this file looks at the stored
picture, and every auth test signs in through these same routes.

The same defect measured over a real socket against a real single-worker uvicorn, where the
bystander is an ordinary second client rather than a coroutine, put the numbers on the client side
of the wire. Both sides of that pair drop the probe's first repeat as warm-up and aggregate the
five that follow, and its baseline is the idle window that opens the run and the same window that
closes it: 24.0 ms and 24.0 ms on the pre-fix tree, 24.4 ms and 24.1 ms on the fixed one, so the
harness itself did not drift. In one login's ~492 ms window the loop answered 2 cheap requests
with the slowest waiting 496.6 ms, while the same login on a thread answered 21-22 with nothing
over 100 ms in 107 samples; the cost to the subject was none (492.5 ms on the loop, 505.1 ms on
the thread), what changed was everybody else. Under four concurrent logins the loop version took
1897 ms of wall and left a bystander 1889.9 ms behind it, the thread version 532 ms with a
36.9 ms worst bystander, because bcrypt on the loop is not only slow, it is strictly serial.
"""
from __future__ import annotations

import asyncio
import io
import os
import time
import uuid

from httpx import AsyncClient
from PIL import Image

from app.core.config import settings
from app.services.photo_service import process_and_store_upload
from .conftest import register_and_auth

PERIOD_S = 0.005
# Below this a call is too short to say anything about who owned the loop while it ran.
MIN_DURATION_MS = 100.0
# One scheduling round trip to the thread handover is allowed for: on Windows that costs the
# 15.6 ms timer granularity, and the same shape reappeared at 28 ms under load. Half of the call
# separates "waited through the request" from "waited for a handover".
CEILING_RATIO = 0.5


async def _watch(coro_factory) -> tuple[float, float, int, object]:
    """Run one awaitable while a bystander times how long the loop went without waking."""
    gaps: list[float] = []
    stop = asyncio.Event()

    async def beat() -> None:
        last = time.perf_counter()
        while not stop.is_set():
            await asyncio.sleep(PERIOD_S)
            now = time.perf_counter()
            gaps.append((now - last) * 1000.0)
            last = now

    task = asyncio.create_task(beat())
    await asyncio.sleep(0.05)
    gaps.clear()
    started = time.perf_counter()
    result = await coro_factory()
    duration_ms = (time.perf_counter() - started) * 1000.0
    stop.set()
    await task
    return duration_ms, max(gaps), len(gaps), result


def _assert_loop_came_back(
    subject: str, duration_ms: float, max_gap_ms: float, ticks: int
) -> None:
    assert duration_ms >= MIN_DURATION_MS, (
        f"{subject} took {duration_ms:.1f} ms, below the {MIN_DURATION_MS} ms floor this"
        " check needs to tell a held loop from a free one"
    )
    assert max_gap_ms < duration_ms * CEILING_RATIO, (
        f"{subject} held the event loop: the bystander waited {max_gap_ms:.1f} ms of a "
        f"{duration_ms:.1f} ms call, which is the call itself rather than a thread handover"
    )
    assert ticks >= 3, f"{subject} let the loop wake {ticks} time(s) in {duration_ms:.1f} ms"


async def test_signing_in_returns_the_event_loop(client: AsyncClient) -> None:
    """`POST /auth/login` verifies a bcrypt hash; that verification is not the loop's to run."""
    email = f"loop-login-{uuid.uuid4().hex[:8]}@befos.app"
    account = await register_and_auth(client, email)

    duration, max_gap, ticks, response = await _watch(
        lambda: client.post("/api/v1/auth/login", json={"email": email, "password": "Test12345"})
    )
    assert response.status_code == 200, response.text
    _assert_loop_came_back("POST /auth/login", duration, max_gap, ticks)


async def test_registering_returns_the_event_loop(client: AsyncClient) -> None:
    """Registration hashes the password before it stores anything: ~460 ms of CPU."""
    email = f"loop-register-{uuid.uuid4().hex[:8]}@befos.app"

    def request():
        return client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "Test12345", "password_confirm": "Test12345"},
        )

    duration, max_gap, ticks, response = await _watch(request)
    assert response.status_code == 201, response.text
    _assert_loop_came_back("POST /auth/register", duration, max_gap, ticks)


def _camera_back() -> bytes:
    """A 2400x3200 JPEG with texture, so the encoder cannot shrink it to a few kilobytes."""
    canvas = Image.new("RGB", (2400, 3200))
    pixels = canvas.load()
    for y in range(0, 3200, 7):
        for x in range(0, 2400, 7):
            pixels[x, y] = (
                (x * 37 + y * 91) % 256, (x * 13 + y * 57) % 256, (x * 71 + y * 23) % 256
            )
    buffer = io.BytesIO()
    canvas.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


async def test_a_photo_upload_returns_the_event_loop() -> None:
    """Re-encoding a camera roll is Pillow's work, not the loop's: it ran 427-549 ms there."""
    photo = await asyncio.to_thread(_camera_back)
    assert len(photo) < settings.max_upload_size_bytes, len(photo)

    duration, max_gap, ticks, path = await _watch(
        lambda: process_and_store_upload(photo, "image/jpeg")
    )
    try:
        assert path.startswith("/uploads/")
        _assert_loop_came_back("a photo upload", duration, max_gap, ticks)
    finally:
        stored = os.path.join(settings.upload_dir, path.removeprefix("/uploads/"))
        if os.path.exists(stored):
            os.remove(stored)


async def test_the_offloaded_photo_is_the_same_picture() -> None:
    """Moving the pipeline to a thread must not change the one file the route is for.

    The uploaded canvas is bigger than the pixel cap, so what lands on disk is the re-encoded
    1600 px picture rather than the bytes that arrived: this checks the thread ran the whole
    pipeline and not half of it.
    """
    photo = await asyncio.to_thread(_camera_back)
    path = await process_and_store_upload(photo, "image/jpeg")
    stored_path = os.path.join(settings.upload_dir, path.removeprefix("/uploads/"))
    try:
        with Image.open(stored_path) as stored:
            assert stored.format == "JPEG"
            assert stored.mode == "RGB"
            assert max(stored.size) <= 1600
        # The re-encoded canvas is smaller than the camera bytes that arrived, so what sits on
        # disk is the pipeline's answer rather than a copy of the upload.
        assert os.path.getsize(stored_path) < len(photo)
    finally:
        if os.path.exists(stored_path):
            os.remove(stored_path)
