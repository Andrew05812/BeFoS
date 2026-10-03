"""Adversarial reliability guards: duplicate writes under concurrency, limiter
identity, and the state an account leaves behind once it is gone.

These cases were found by deliberately breaking the app (double taps, retries,
spoofed headers, deleted accounts), not by reading the happy path.
"""
from __future__ import annotations

import asyncio
import time

import pytest
from httpx import AsyncClient
from starlette.requests import Request

from app.core.exceptions import RateLimitedError
from app.core.logging import redact
from app.core.rate_limit import _MAX_KEYS, SlidingWindowRateLimiter, _client_key
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
    assert history.status_code in (403, 404), history.text


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

