"""A page link is the server's word about a frontier, and this file takes that word apart.

`docs/RELEASE.md` §11 item 10 named the gap in one sentence: the deck printed `rank:<число>` and the
tap list printed `tap:<микросекунды>:<id>`, and each handed the client a string from which it could
build any other. Shape checks and bounds were already in place — a digit run that is not a digit run, a
rank past int32, a moment past the clock were all refused — so nothing crashed. What was missing was
provenance: the payload was the client's assertion, and every one of those bounds was the server asking
"is this a sane number?" of a value the caller chose.

Stage 126 moved the choice to the server. A link is now
`base64url("v1|<kid>|<door>|<reader>|<window>|<place>") + "." + base64url(hmac_sha256)`, and the
refusal of anything that does not verify is the same 422 with the same sentence the deck has always
given a broken link — because which half failed is exactly what somebody probing the door would want to
learn, and a link is a string with a reader's place in it, which is not something to repeat into a log.

Checked here, in order: what a link says and what it must never carry; that every way of breaking the
claim is refused (the place, the signature, the key id, the reader, the door, the version, the window);
that a rotation keeps the retired key alive for the span of the links it sealed and not one second
longer; that all of those refusals are one answer; what a production deployment may and may not set the
page key to; and what the whole bargain costs, against the shoot published in `s126_seal_cost.json`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from httpx import AsyncClient
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.core.exceptions import ValidationError
from app.core.page_cursor import (
    BAD_CURSOR,
    DECK,
    INBOX,
    MOMENT_PREFIX,
    PAIRS,
    PASSES,
    RANK_PREFIX,
    TAPS,
    VERSION,
    open_link,
    open_moment,
    seal,
)

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE = _ROOT / "docker-compose.yml"
_ENV_EXAMPLE = _ROOT / ".env.example"

_PAGE_SECRET = "s126-page-key-0123456789abcdef-0123456789abcdef"
_RETIRED_SECRET = "s126-retired-key-0123456789abcdef-0123456789abcde"
_JWT_A = "prod-access-secret-value-that-is-long-enough-1234567890"
_JWT_B = "prod-refresh-secret-value-that-is-long-enough-0987654321"
_WINDOW_SECONDS = 600
_ONE_PLACE = f"{MOMENT_PREFIX}:1730000000000000:{uuid.uuid4().hex}"


def _ring(
    monkeypatch, *, current: str = _PAGE_SECRET, retired: str | None = None,
    current_id: str = "new", window: int = _WINDOW_SECONDS,
) -> None:
    """The key ring one test needs, written onto the settings object the module reads at call time."""
    monkeypatch.setattr(settings, "cursor_secret", current)
    monkeypatch.setattr(settings, "cursor_key_id", current_id)
    monkeypatch.setattr(settings, "cursor_secret_previous", retired or "")
    monkeypatch.setattr(settings, "cursor_key_id_previous", "old" if retired else "")
    monkeypatch.setattr(settings, "cursor_link_minutes", window // 60)


def _payload(token: str) -> str:
    body = token.split(".", 1)[0]
    return base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()


def _reseal(payload: str, secret: str = _PAGE_SECRET) -> str:
    """A link built around a payload somebody edited, signed with the key that is really in the ring.

    The distinction matters: an unsigned string is refused for a reason the bounds already covered
    before this stage, and proving that the *claims inside* a correctly signed envelope are checked is
    what this file is for.
    """
    body = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{body}.{signature}"


def test_a_link_names_the_door_and_the_reader_and_carries_no_secret(monkeypatch) -> None:
    _ring(monkeypatch)
    reader = uuid.uuid4()
    token = seal(TAPS, reader, _ONE_PLACE)
    fields = _payload(token).split("|")

    assert fields[0] == VERSION
    assert fields[1] == "new", "the link does not say which key sealed it"
    assert fields[2] == TAPS
    assert fields[3] == reader.hex, "the link does not say whose frontier it is"
    assert fields[5] == _ONE_PLACE
    assert len(fields) == 6
    assert _PAGE_SECRET not in token, "the signing key travelled inside the link it signed"


def test_a_link_whose_payload_was_edited_after_signing_is_refused(monkeypatch) -> None:
    """The place swapped inside a real envelope, the signature left as the server wrote it.

    This is the exact shape the doors used to answer: a client that took a link it was given, rewrote
    the number at the end of it and sent it back. Under the seal the two halves disagree, and the
    disagreement is the refusal — no re-reading of a rank, no resuming from somebody's moment.
    """
    _ring(monkeypatch)
    reader = uuid.uuid4()
    token = seal(TAPS, reader, _ONE_PLACE)
    body, _, signature = token.rpartition(".")
    fields = _payload(token).split("|")
    fields[5] = f"{MOMENT_PREFIX}:1730000000000000:{uuid.uuid4().hex}"
    edited = base64.urlsafe_b64encode("|".join(fields).encode()).decode().rstrip("=")

    with pytest.raises(ValidationError) as refused:
        open_link(f"{edited}.{signature}", door=TAPS, reader_id=reader)
    assert refused.value.message == BAD_CURSOR
    # And the same edited payload, honestly signed, is read: what the door refuses is the lie about the
    # signature, not the new number — the place of a link is the server's to write and nobody else's.
    assert open_link(_reseal("|".join(fields)), door=TAPS, reader_id=reader) == fields[5]


def test_a_link_whose_signature_was_edited_is_refused(monkeypatch) -> None:
    _ring(monkeypatch)
    reader = uuid.uuid4()
    token = seal(TAPS, reader, _ONE_PLACE)
    body = token.split(".", 1)[0]

    for broken in (f"{body}.{'A' * 43}", f"{body}.AAAA", f"{body}."):
        with pytest.raises(ValidationError) as refused:
            open_link(broken, door=TAPS, reader_id=reader)
        # A signature too short to hold a digest, one of the right length and an absent one are refused
        # alike: the door does not get to say which of the three a valid one is not.
        assert refused.value.message == BAD_CURSOR


def test_a_link_naming_a_key_the_server_does_not_hold_is_refused(monkeypatch) -> None:
    """Signed with the live key, under an id nobody has: the ring lookup is the gate.

    With one key in the ring the two cases are indistinguishable, and that is the point of naming the
    key in the link — during a rotation an unknown id must be refused on its own, or a dropped key would
    turn its old links into a probe for which key is current.
    """
    _ring(monkeypatch)
    reader = uuid.uuid4()
    forged = _reseal(f"{VERSION}|ghost|{TAPS}|{reader.hex}|0|{MOMENT_PREFIX}:1:x")

    with pytest.raises(ValidationError) as refused:
        open_link(forged, door=TAPS, reader_id=reader, now=datetime(2026, 11, 2, tzinfo=UTC))
    assert refused.value.message == BAD_CURSOR


def test_a_link_signed_with_another_key_is_refused(monkeypatch) -> None:
    _ring(monkeypatch)
    reader = uuid.uuid4()
    forged = _reseal(
        f"{VERSION}|new|{TAPS}|{reader.hex}|0|{MOMENT_PREFIX}:1:x",
        secret="a-key-not-in-the-ring-0123456789abc",
    )

    with pytest.raises(ValidationError):
        open_link(forged, door=TAPS, reader_id=reader)


def test_a_link_issued_to_another_reader_is_refused(monkeypatch) -> None:
    """A frontier belongs to the walk it was issued for, and the reader is inside the signed payload."""
    _ring(monkeypatch)
    holder, asker = uuid.uuid4(), uuid.uuid4()
    token = seal(TAPS, holder, _ONE_PLACE)

    with pytest.raises(ValidationError) as refused:
        open_link(token, door=TAPS, reader_id=asker)
    assert refused.value.message == BAD_CURSOR


@pytest.mark.parametrize(
    ("issued", "asked"),
    [
        (DECK, TAPS), (DECK, INBOX), (DECK, PAIRS), (TAPS, INBOX), (TAPS, PAIRS),
        (INBOX, PASSES), (PASSES, PAIRS), (PAIRS, TAPS), (INBOX, DECK), (PAIRS, PASSES),
    ],
)
def test_a_link_from_one_door_does_not_open_another(
    monkeypatch, issued: str, asked: str
) -> None:
    """Ten pairs of doors. The place of one list is a row of another table.

    Read across, the moment and the id name a row that does not exist in this ordering, and the page
    would answer with somebody's tail rather than refuse. The deck's rank is the sharpest case, since a
    rank is an integer that any list's key columns would accept as a plausible number.
    """
    _ring(monkeypatch)
    reader = uuid.uuid4()
    place = f"{RANK_PREFIX}:3" if issued == DECK else _ONE_PLACE
    token = seal(issued, reader, place)

    with pytest.raises(ValidationError) as refused:
        open_link(token, door=asked, reader_id=reader)
    assert refused.value.message == BAD_CURSOR


def test_a_link_of_an_unknown_version_is_refused_though_correctly_signed(monkeypatch) -> None:
    """The version is checked after the signature, so a future format cannot be read by accident."""
    _ring(monkeypatch)
    reader = uuid.uuid4()
    forged = _reseal(f"v2|new|{TAPS}|{reader.hex}|0|{MOMENT_PREFIX}:1:x")

    with pytest.raises(ValidationError):
        open_link(forged, door=TAPS, reader_id=reader)


def test_a_link_is_read_for_one_window_and_two_at_most(monkeypatch) -> None:
    """The age a link carries is a window, so its life is between one and two of them.

    Both ends are asserted rather than estimated: a link minted in window `n` is read at `n` and at
    `n + 1` and refused at `n + 2`, and that is the span `docs/API.md` publishes. The window is a
    window rather than a timestamp for one reason that is easy to miss: a page hands out its own next
    link, and a payload stamped with the instant would make that link a different string on every
    answer — which would break the promise the tap list has held since stage 123 that one link, turned
    twice, gives one page.
    """
    _ring(monkeypatch)
    reader = uuid.uuid4()
    minted = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    token = seal(TAPS, reader, _ONE_PLACE, issued_at=minted)

    assert open_link(token, door=TAPS, reader_id=reader, now=minted) == _ONE_PLACE
    middle = minted + timedelta(seconds=_WINDOW_SECONDS - 1)
    assert open_link(token, door=TAPS, reader_id=reader, now=middle) == _ONE_PLACE
    with pytest.raises(ValidationError) as refused:
        open_link(token, door=TAPS, reader_id=reader, now=minted + timedelta(seconds=2 * _WINDOW_SECONDS))
    assert refused.value.message == BAD_CURSOR


def test_a_link_minted_at_the_end_of_a_window_is_read_in_the_next_one(monkeypatch) -> None:
    """The boundary case the span claim rests on: issued at the last second, read at the first."""
    _ring(monkeypatch)
    reader = uuid.uuid4()
    last_second = datetime.fromtimestamp(
        (_WINDOW_SECONDS * 7) - 1, tz=UTC
    )
    token = seal(TAPS, reader, _ONE_PLACE, issued_at=last_second)

    assert open_link(token, door=TAPS, reader_id=reader, now=last_second + timedelta(seconds=2))


def test_a_rotated_key_turns_pages_until_its_links_age_out(monkeypatch) -> None:
    """A rotation retires a key and keeps its links alive for their span — and no longer.

    The retired key sits in the ring under its own id, which is the only reason a link has to name an
    id at all: trying two keys in some order would answer the same pages and leave no record of which
    key a walk was standing on. Dropping the retired entry is the second half of the procedure, and the
    refusal below is the half that proves it happened.
    """
    _ring(monkeypatch, current=_RETIRED_SECRET, current_id="old")
    reader = uuid.uuid4()
    old_link = seal(TAPS, reader, _ONE_PLACE)

    _ring(monkeypatch, current=_PAGE_SECRET, retired=_RETIRED_SECRET)
    assert _payload(old_link).split("|")[1] == "old"
    assert open_link(old_link, door=TAPS, reader_id=reader) == _ONE_PLACE
    assert _payload(seal(TAPS, reader, _ONE_PLACE)).split("|")[1] == "new", (
        "a fresh link is still being sealed by the retired key"
    )

    _ring(monkeypatch, current=_PAGE_SECRET, retired=None)
    with pytest.raises(ValidationError) as refused:
        open_link(old_link, door=TAPS, reader_id=reader)
    assert refused.value.message == BAD_CURSOR


@pytest.mark.parametrize(
    "junk", ["", ".", "abc", "abc.", ".abc", "a.b.c", "%%%", "!!!!", "a" * 400, "###.###"]
)
def test_a_string_that_is_not_a_link_is_refused_as_input(junk: str) -> None:
    with pytest.raises(ValidationError) as refused:
        open_link(junk, door=TAPS, reader_id=uuid.uuid4())
    assert refused.value.message == BAD_CURSOR


def test_every_refusal_is_the_same_answer_and_names_no_mechanism(monkeypatch) -> None:
    """Ten ways to break a link, one sentence — and that sentence says nothing about the seal.

    The refusal is the only channel through which a caller learns anything about the check, so it is the
    channel that must not carry the answer. Each failure below is asserted to be the same message, the
    same status and the same machine code, and none of them may name a part of the mechanism.
    """
    _ring(monkeypatch)
    reader, stranger = uuid.uuid4(), uuid.uuid4()
    good = seal(TAPS, reader, _ONE_PLACE)
    body = good.split(".", 1)[0]

    def refusal(name: str) -> ValidationError:
        # Read through the door codec, which is the only way a door in the product asks a link
        # anything: `open_link` returns the place verbatim, and the bounds inside a place — a moment
        # past the clock, a rank past int32 — are the codec's own check, not the seal's.
        window = int(datetime.now(UTC).timestamp()) // _WINDOW_SECONDS
        token, caller, door = good, reader, TAPS
        if name == "unsigned":
            token = base64.urlsafe_b64encode(b"tap:1:x").decode().rstrip("=")
        elif name == "torn":
            token = f"{body}.{'A' * 43}"
        elif name == "unknown_key":
            token = _reseal(f"{VERSION}|ghost|{TAPS}|{reader.hex}|{window}|{MOMENT_PREFIX}:1:x")
        elif name == "wrong_key":
            token = _reseal(
                f"{VERSION}|new|{TAPS}|{reader.hex}|{window}|{MOMENT_PREFIX}:1:x", secret="x" * 40
            )
        elif name == "wrong_reader":
            caller = stranger
        elif name == "wrong_door":
            door = INBOX
        elif name == "old_version":
            token = _reseal(f"v0|new|{TAPS}|{reader.hex}|{window}|{MOMENT_PREFIX}:1:x")
        elif name == "expired":
            token = seal(TAPS, reader, _ONE_PLACE, issued_at=datetime(2020, 1, 1, tzinfo=UTC))
        elif name == "absurd_moment":
            token = seal(TAPS, reader, f"{MOMENT_PREFIX}:{10 ** 25}:x")
        else:
            token = good[: -6] + "ZZZZZZ"
        with pytest.raises(ValidationError) as caught:
            open_moment(door, caller, token)
        return caught.value

    names = (
        "unsigned", "torn", "unknown_key", "wrong_key", "wrong_reader", "wrong_door",
        "old_version", "expired", "absurd_moment", "tail_edited",
    )
    answers = {name: refusal(name) for name in names}

    assert {answer.message for answer in answers.values()} == {BAD_CURSOR}
    # One machine code for all ten, and it names the object — a page link — not the check that failed.
    # The client needs this one thing to tell a broken frontier from an ordinary bad input: on hearing
    # it the screen drops its link and re-reads the newest page, while `validation_error` would say
    # "something you typed is wrong" about a string the server itself handed out.
    assert {answer.code for answer in answers.values()} == {"broken_page_link"}
    assert {answer.status_code for answer in answers.values()} == {422}
    for name, answer in answers.items():
        lowered = answer.message.lower()
        for word in ("hmac", "signature", "sign", "key", "kid", "expir", "secret", "version", "cursor"):
            assert word not in lowered, f"{name} leaked {word!r} into the answer: {answer.message}"


def _production(**overrides) -> Settings:
    """A correctly configured production stand, so each case below is about exactly one mistake."""
    base = {
        "ENVIRONMENT": "production",
        "JWT_SECRET": _JWT_A,
        "JWT_REFRESH_SECRET": _JWT_B,
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
        "CORS_ORIGINS": "https://befos.example.com",
        "DEBUG": "false",
        "DEMO_ENABLED": "false",
        "CURSOR_SECRET": _PAGE_SECRET,
    }
    base.update(overrides)
    return Settings(**base)


@pytest.mark.parametrize(
    ("overrides", "refuses"),
    [
        pytest.param({"CURSOR_SECRET": "change-me-cursor-secret-min-32-chars"}, True,
                     id="the shipped placeholder"),
        pytest.param({"CURSOR_SECRET": "short"}, True, id="a key under 32 chars"),
        pytest.param({"CURSOR_SECRET": _JWT_A}, True, id="a copy of the access key"),
        pytest.param({"CURSOR_SECRET": _JWT_B}, True, id="a copy of the refresh key"),
        pytest.param({"CURSOR_SECRET_PREVIOUS": _RETIRED_SECRET}, True, id="a retired key with no id"),
        pytest.param({"CURSOR_KEY_ID_PREVIOUS": "old"}, True, id="an id with no retired key"),
        pytest.param(
            {"CURSOR_SECRET_PREVIOUS": _PAGE_SECRET, "CURSOR_KEY_ID_PREVIOUS": "old"}, True,
            id="the same secret under two ids",
        ),
        pytest.param(
            {"CURSOR_SECRET_PREVIOUS": "short", "CURSOR_KEY_ID_PREVIOUS": "old"}, True,
            id="a weak retired key",
        ),
        pytest.param(
            {"CURSOR_SECRET_PREVIOUS": _RETIRED_SECRET, "CURSOR_KEY_ID_PREVIOUS": "a"}, True,
            id="two keys under one id",
        ),
        pytest.param({"CURSOR_KEY_ID": "a.b"}, True, id="an id holding a separator"),
        pytest.param({"CURSOR_KEY_ID": ""}, True, id="an unnamed key"),
        pytest.param({"CURSOR_KEY_ID": "x" * 40}, True, id="an id longer than a field"),
        pytest.param({"CURSOR_LINK_MINUTES": 0}, True, id="a life of no minutes"),
        pytest.param({"CURSOR_LINK_MINUTES": -5}, True, id="a life before its own issue"),
        pytest.param({"CURSOR_LINK_MINUTES": 100_000}, True, id="a life past a day"),
        pytest.param({"CURSOR_LINK_MINUTES": 45}, False, id="a life of three quarters of an hour"),
        pytest.param(
            {"CURSOR_SECRET_PREVIOUS": _RETIRED_SECRET, "CURSOR_KEY_ID_PREVIOUS": "old"}, False,
            id="a ring in the middle of a rotation",
        ),
    ],
)
def test_the_settings_decide_what_a_page_key_may_be(overrides: dict, refuses: bool) -> None:
    """A page link is only as strong as the secret behind it, so startup is where that is decided.

    The page key is kept apart from the two session keys on purpose: the first is handed out on every
    scroll and the second opens an account, and one secret for both would rotate them together and make
    a leaked link-signing key a token-forgery key. The development stand keeps its placeholder; the guard
    is for a deployment that says `ENVIRONMENT=production` and means it.
    """
    if refuses:
        with pytest.raises(PydanticValidationError):
            _production(**overrides)
        return
    built = _production(**overrides)
    assert built.cursor_link_seconds == int(overrides.get("CURSOR_LINK_MINUTES", 720)) * 60
    ring = built.cursor_keys
    assert "a" not in ring or ring  # the default id is current, never both
    assert built.cursor_signing_key[0] in ring


def test_a_retired_key_and_a_retired_id_are_one_pair_or_neither(monkeypatch) -> None:
    """Half a ring is not a ring: the refusal names the pair rather than guessing a key."""
    with pytest.raises(PydanticValidationError) as caught:
        _production(CURSOR_SECRET_PREVIOUS=_RETIRED_SECRET)
    assert "PREVIOUS" in str(caught.value)


_CURSOR_VARS = (
    "CURSOR_SECRET", "CURSOR_KEY_ID", "CURSOR_SECRET_PREVIOUS",
    "CURSOR_KEY_ID_PREVIOUS", "CURSOR_LINK_MINUTES",
)


def test_the_deployment_can_actually_set_the_page_key() -> None:
    """A guard the operator cannot reach is a guard that gets turned off by editing the image.

    `config.py` reads five names for the seal; a deployment that ships placeholders for them cannot
    rotate anything. Checked where the operator reads: the compose service really carries all five
    (parsed, so a name inside a comment does not count), the file an operator copies names them too,
    and the sample key either file ships is one that production refuses — otherwise a deployment
    starts with a signing key printed in a public repository and still passes the startup guard.
    """
    compose = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    env = compose["services"]["backend"]["environment"]
    assert isinstance(env, dict), "the backend no longer takes its environment as a map"
    for name in _CURSOR_VARS:
        assert name in env, f"docker-compose.yml never passes {name}, so a container cannot set it"

    example = _ENV_EXAMPLE.read_text(encoding="utf-8")
    for name in _CURSOR_VARS:
        assert f"{name}=" in example, f"{name} is missing from the file an operator copies"

    sample = next(
        row.split("=", 1)[1].strip()
        for row in example.splitlines()
        if row.startswith("CURSOR_SECRET=")
    )
    # `${CURSOR_SECRET:-…}` in compose is the same string the container gets when the .env is silent.
    compose_default = env["CURSOR_SECRET"].split(":-")[-1].rstrip("}")
    for source, value in ((".env.example", sample), ("docker-compose.yml", compose_default)):
        assert value, f"{source} passes an empty page key"
        with pytest.raises(PydanticValidationError):
            _production(CURSOR_SECRET=value)
    assert sample == compose_default, (
        "the two files an operator reads give a container two different default page keys"
    )


async def test_the_doors_still_answer_pages_through_the_seal(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The route, the service and the seal are one path: nothing here is mocked.

    A door with nothing to show answers no link; a link the server did not issue is refused at the route
    with the deck's own sentence; and a page the server did hand out is read back by the same door.
    """
    creds = await register_and_auth(client, f"s126_walk_{uuid.uuid4().hex[:8]}@befos.app")
    await complete_onboarding(client, creds["token"], name="Вера")
    await answer_all_questions(client, creds["token"])
    reader = uuid.UUID(creds["user_id"])

    empty = await client.get("/api/v1/discover/liked-me", headers=auth_headers(creds["token"]))
    assert empty.status_code == 200, empty.text
    assert empty.json() == {"likes": [], "has_more": False, "next_cursor": None}

    forged = base64.urlsafe_b64encode(b"rank:3").decode().rstrip("=")
    for url in ("/api/v1/discover/liked-me", "/api/v1/discover/passed", "/api/v1/matches"):
        refused = await client.get(url, headers=auth_headers(creds["token"]), params={"cursor": forged})
        assert refused.status_code == 422, f"{url} read a link it never issued: {refused.text[:160]}"
        assert refused.json()["error"]["message"] == BAD_CURSOR
        # The code is the part the client reads. A screen holding a link the server will not open has
        # to drop it and re-read the newest page; `validation_error` would tell it that something it
        # typed is wrong, and the retry would ask for the same dead frontier again.
        assert refused.json()["error"]["code"] == "broken_page_link", refused.text[:200]

    from app.core.page_cursor import seal as _seal

    mine = _seal("inbox", reader, f"{MOMENT_PREFIX}:1730000000000000:{uuid.uuid4().hex}")
    turns = await client.get(
        "/api/v1/discover/liked-me", headers=auth_headers(creds["token"]), params={"cursor": mine}
    )
    assert turns.status_code == 200, (
        "a link the server signed was refused by its own door: " + turns.text[:160]
    )
    assert turns.json() == {"likes": [], "has_more": False, "next_cursor": None}


async def test_the_access_log_names_the_route_and_neither_the_link_nor_the_key(
    client: AsyncClient, monkeypatch, caplog
) -> None:
    """A link is a frontier somebody holds; the log has no business repeating it.

    The server's own line is what is checked — the one `app/core/observability.py` writes for every
    request — because that is where a string with a reader's place in it would be copied into whatever
    pipeline collects the log. The route is named, the status is named, the token and the key are not.
    """
    _ring(monkeypatch)
    creds = await register_and_auth(client, f"s126_log_{uuid.uuid4().hex[:8]}@befos.app")
    await complete_onboarding(client, creds["token"], name="Вера")
    await answer_all_questions(client, creds["token"])

    with caplog.at_level("INFO"):
        await client.get("/api/v1/matches", headers=auth_headers(creds["token"]))
        refused = await client.get(
            "/api/v1/matches", headers=auth_headers(creds["token"]), params={"cursor": "abc"}
        )
    assert refused.status_code == 422

    lines = [record.getMessage() for record in caplog.records]
    assert any("/api/v1/matches -> 200" in line for line in lines), lines[:5]
    assert _PAGE_SECRET not in "\n".join(lines), "the signing key reached the log"

    # Only the server's own line is promised not to repeat a query string. The test client writes
    # its INFO record before the request leaves the process, so it names the URL it was handed —
    # checking that would only prove httpx prints what it was given.
    ours = [r.getMessage() for r in caplog.records if r.name == "befos.access"]
    assert ours, "the request went through without the server logging it"
    joined = "\n".join(ours)
    assert "abc" not in joined and "cursor" not in joined, (
        f"the server copied a page link into its own log: {joined[:300]}"
    )


def test_sealing_and_reading_a_page_link_costs_the_measured_microseconds(monkeypatch) -> None:
    """The bound is copied from a shoot, not picked: `s126_seal_cost.json` holds the medians.

    Seven repeats of three thousand calls on this machine gave 13.7…14.0 мкс for a seal, 18.7…18.8 for
    a read and 33.3…37.2 for the pair a page costs (`s126_seal_cost.json`, Python 3.12.4). Four hundred
    microseconds is more than ten times the worst of those medians and still two orders under the
    27…61 мс the stand publishes for a page of taps, so it cannot flake on a loaded runner while it does
    catch the way this would actually break: a door that started deriving a key per call, or hashing a
    list of them, lands in milliseconds and this test says so here rather than a re-shot table later.
    """
    _ring(monkeypatch)
    reader = uuid.uuid4()
    medians = []
    for _ in range(5):
        samples = []
        for _ in range(500):
            started = datetime.now(UTC)
            token = seal(TAPS, reader, _ONE_PLACE)
            open_link(token, door=TAPS, reader_id=reader)
            samples.append((datetime.now(UTC) - started) / timedelta(microseconds=1))
        samples.sort()
        medians.append(samples[len(samples) // 2])

    worst = max(medians)
    assert worst <= 400, (
        f"a page link costs {worst:.1f} мкс at the median here; the shoot published in "
        "`s126_seal_cost.json` measured 33.3…37.2 мкс for the same pair"
    )
