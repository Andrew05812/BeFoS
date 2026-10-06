"""Observability: one correlation id per request, the cost of that request, and no
credentials in either.

The point of these tests is not that a log line exists — it is that a line can be tied
back to the request that caused it, and that the tying never carries the token itself.
"""

from __future__ import annotations

import logging
import string
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.core.context import adopt_inbound, new_request_id
from app.core.logging import RequestIdFilter
from app.core.observability import HEADER, RequestContextMiddleware
from app.websocket.chat_ws import chat_socket

from .conftest import auth_headers, register_and_auth

_ALLOWED = set(string.ascii_letters + string.digits + "-_.")

pytestmark = pytest.mark.usefixtures("_stamp_captured")


@pytest.fixture(autouse=True)
def _stamp_captured(caplog):
    """caplog installs its own handler, which does not run the filters the shipped one
    does. Without the id filter these records would read as uncorrelated even though the
    production ones are, and the assertions below would be checking the test harness."""
    caplog.handler.addFilter(RequestIdFilter())


def _rows(caplog) -> list[tuple[str, str, str]]:
    return [
        (str(getattr(record, "request_id", "")), record.levelname, record.getMessage())
        for record in caplog.records
    ]


async def test_every_response_carries_a_correlation_id(client: AsyncClient) -> None:
    first = await client.get("/api/v1/users/me")
    second = await client.get("/api/v1/users/me")

    assert first.headers.get(HEADER)
    assert second.headers.get(HEADER)
    assert first.headers[HEADER] != second.headers[HEADER], "two requests must not share one id"


async def test_a_request_id_the_caller_supplied_is_kept(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me", headers={HEADER: "probe-77"})
    assert response.headers[HEADER] == "probe-77"


async def test_the_access_line_names_the_request_and_its_cost(client: AsyncClient, caplog) -> None:
    await client.get("/api/v1/users/me")

    access = [m for _, _, m in _rows(caplog) if m.startswith("request ")]
    assert any("GET /api/v1/users/me -> 401 in " in m for m in access), access
    assert all(m.endswith(" ms") for m in access)


async def test_an_injected_correlation_id_cannot_write_a_second_log_line(
    client: AsyncClient, caplog
) -> None:
    """A header value is attacker text. Adopting it verbatim would let a caller plant a
    fake record, or a five-kilobyte blob, in a stream that reads as the server's own."""
    hostile = "probe" + " " * 200 + "|ERROR FakeAccessLogEntry"
    response = await client.get("/api/v1/users/me", headers={HEADER: hostile})

    assert response.headers[HEADER] != hostile
    assert "FakeAccessLogEntry" not in response.headers[HEADER]
    assert " " not in response.headers[HEADER]
    assert all("FakeAccessLogEntry" not in rid for rid, _, _ in _rows(caplog))


@pytest.mark.parametrize(
    "value",
    [None, "", "x" * 65, "has space", "has|pipe", "has\nnewline", "кириллица"],
)
def test_only_a_plain_single_line_token_is_adopted(value: str | None) -> None:
    adopted = adopt_inbound(value)
    # isalnum() is true for cyrillic digits and letters; only plain ascii survives here.
    printable = bool(value) and set(value) <= _ALLOWED and len(value) <= 64
    if printable:
        assert adopted == value
    else:
        assert adopted != value
        assert len(adopted) == 16 and set(adopted) <= set(string.hexdigits.lower())


def test_a_generated_id_is_not_reused() -> None:
    assert len({new_request_id() for _ in range(200)}) == 200


async def test_the_request_log_never_carries_the_credential(client: AsyncClient, caplog) -> None:
    viewer = await register_and_auth(client, "obs_viewer@befos.app")
    caplog.clear()

    await client.get("/api/v1/users/me", headers=auth_headers(viewer["token"]))

    rows = _rows(caplog)
    assert any(m.startswith("request GET /api/v1/users/me -> 200") for _, _, m in rows)
    joined = "\n".join(m for _, _, m in rows)
    assert viewer["token"] not in joined, "the access token must stay out of the log"
    assert "Bearer" not in joined


async def test_a_login_that_is_rejected_leaves_no_password_behind(client: AsyncClient, caplog) -> None:
    await client.post(
        "/api/v1/auth/login", json={"email": "nobody@befos.app", "password": "Secret12345"}
    )
    joined = "\n".join(m for _, _, m in _rows(caplog))
    assert "Secret12345" not in joined


async def test_a_liveness_probe_does_not_fill_the_log(client: AsyncClient, caplog) -> None:
    await client.get("/api/v1/health")

    noisy = [
        (record.levelname, record.getMessage())
        for record in caplog.records
        if record.name == "befos.access" and "/api/v1/health " in record.getMessage()
        and record.levelname != "DEBUG"
    ]
    assert noisy == [], f"health polls must not reach info: {noisy}"


async def test_a_request_that_outstays_its_budget_is_called_out(
    client: AsyncClient, caplog, monkeypatch
) -> None:
    from app.core import observability

    monkeypatch.setattr(observability, "SLOW_MS", -1.0)
    await client.get("/api/v1/users/me")

    slow = [
        m for _, level, m in _rows(caplog) if level == "WARNING" and m.startswith("slow request ")
    ]
    assert any("GET /api/v1/users/me -> 401" in m for m in slow), slow


async def test_the_error_and_the_access_line_of_one_request_share_one_id(caplog) -> None:
    """The value of a correlation id is that a stack trace and a status line can be read
    together. If they differ, neither finding is usable."""
    probe = FastAPI()
    probe.add_middleware(RequestContextMiddleware)
    error_logger = logging.getLogger("probe")

    @probe.get("/boom")
    async def boom() -> None:
        raise RuntimeError("deliberate failure")

    @probe.exception_handler(RuntimeError)
    async def handle(_: object, exc: Exception) -> JSONResponse:
        error_logger.exception("request failed")
        return JSONResponse(status_code=500, content={"detail": "boom"})

    async with AsyncClient(transport=ASGITransport(app=probe), base_url="http://probe") as ac:
        response = await ac.get("/boom")

    assert response.status_code == 500
    rows = _rows(caplog)
    failed = [rid for rid, _, m in rows if m == "request failed"]
    access = [rid for rid, _, m in rows if m.startswith("request GET /boom -> 500")]
    assert failed and access
    assert failed[0] == access[0] == response.headers[HEADER]


async def test_a_refused_socket_says_why_without_saying_what_it_was_given(caplog) -> None:
    class _Socket:
        def __init__(self) -> None:
            self.closed: int | None = None
            # A stand-in for a connection has to carry the peer address the handshake
            # limiter reads; a double narrower than the real object hides the guard.
            self.client = SimpleNamespace(host="testclient")
            self.headers: dict[str, str] = {}

        async def close(self, code: int) -> None:
            self.closed = code

    socket = _Socket()
    await chat_socket(socket, uuid.uuid4(), "eyJhbGciOi.private-token")

    assert socket.closed == 1008
    refused = [m for _, level, m in _rows(caplog) if level == "WARNING" and "socket refused" in m]
    assert refused
    assert all("private-token" not in m and "eyJhbGciOi" not in m for m in refused)
    assert all("\n" not in m for m in refused), "one event, one line"


async def test_a_socket_line_is_stamped_with_its_own_connection_id(caplog) -> None:
    class _Socket:
        def __init__(self) -> None:
            self.client = SimpleNamespace(host="testclient")
            self.headers: dict[str, str] = {}

        async def close(self, code: int) -> None:
            pass

    await chat_socket(_Socket(), uuid.uuid4(), None)

    ids = [rid for rid, _, m in _rows(caplog) if "socket refused" in m]
    assert ids
    assert len(set(ids)) == 1, "the whole handshake reads as one connection"
    assert ids[0].startswith("ws-")
