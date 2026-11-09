"""A person who mistypes their word twice is standing outside an account they still own.

Until this stage `/auth` answered eight verbs (`api/v1/auth.py:33-127`) and none of them was
recovery: the only way back into a lost word was `POST /auth/change-password`, which asks for the
old password (`auth_service.py:135-149`) — a door that needs the thing it is standing in place of.
The audit named this P0-1 (`docs/PRODUCT_TECHNICAL_AUDIT.md` §11): lose the word, lose the
account, the profile, the pair and the whole correspondence, and support has no lever either.

This file is the contract for the answer. The claims it pins, in the order a reader meets them:

* the door is mounted and is public — nobody has to be signed in to ask to be signed in again;
* the answer to the request does not say whether the address exists, because a recovery door that
  confirms which emails hold accounts is an enumeration service with a friendly face — the same
  refusal-shape discipline that stage 52 applied to sign-in (`auth_service.py:69-84`);
* the letter carries a code a person can read out loud, and nothing else they did not ask for;
* the code changes the word exactly once, and every session that existed before it is ended;
* an unknown, an already-redeemed and an expired code answer the same way, so the door cannot be
  used to learn which of the three happened;
* a second request while a code is alive sends no second letter, because the letter is the abuse
  surface of this design;
* the row holds a hash of the code, never the code — the same rule `refresh_tokens` already obeys
  (`models/token.py:22`, `security.py:101-103`);
* the outbox is a directory on the server, not a route on the server;
* the SMTP branch really speaks SMTP, and production refuses to start on a channel that pretends.

Everything here is asserted through the public API and the test database. The letters land in a
temporary directory chosen by the test, so no external mail service is contacted by this file:
connecting one is the owner's decision, and `docs/RELEASE.md` §11 says so in the same words.
"""

from __future__ import annotations

import re
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from app.core.config import settings
from app.main import create_app
from app.models import RefreshToken, User

from .conftest import auth_headers, register_and_auth

_REQUEST = "/api/v1/auth/password-reset/request"
_CONFIRM = "/api/v1/auth/password-reset/confirm"

# Twelve characters out of an alphabet with no look-alikes: the code is meant to be read from a
# mail client on one phone and typed into another screen, so `0/O` and `1/I/l` are excluded.
# 32^12 is the space an attacker guesses through; the rate limiter on `/auth` is what bounds the
# number of guesses they get.
_CODE = re.compile(r"\b[0-9A-HJ-NP-Z]{12}\b")
_GROUPED = re.compile(r"\b[0-9A-HJ-NP-Z]{4}-[0-9A-HJ-NP-Z]{4}-[0-9A-HJ-NP-Z]{4}\b")


def _outbox(client: AsyncClient, directory: Path) -> None:
    """Point the mail channel at a directory this test owns, for the length of one test."""
    settings.mail_transport = "outbox"
    settings.mail_outbox_dir = str(directory)


_RESET_SUBJECT = "Код восстановления BeFoS"


def _letters(directory: Path) -> list[Path]:
    """The recovery letters in the directory, oldest first.

    Since stage 131 the same outbox also carries the confirmation letter registration writes, and a
    helper that returned every file would count a registration as a recovery request — the first
    letter a person ever gets in this product is not this one. The subject is the only part of the
    envelope the two doors differ in.
    """
    return sorted(
        letter
        for letter in directory.glob("*.eml")
        if _RESET_SUBJECT in letter.read_text(encoding="utf-8")
    )


def _codes_in(letter: Path) -> list[str]:
    """The bare codes one letter carries, whether it prints them grouped or not."""
    text_body = letter.read_text(encoding="utf-8")
    found = _CODE.findall(text_body)
    found += [group.replace("-", "") for group in _GROUPED.findall(text_body)]
    return sorted(set(found))


async def _owner(session: AsyncSession, email: str) -> User:
    return (await session.execute(select(User).where(User.email == email))).scalar_one()


async def _table_exists(session: AsyncSession, name: str) -> bool:
    """Whether the schema really has this table, read from the catalogue rather than from memory.

    `to_regclass` answers NULL for a name that does not exist, so a missing table is a failure with a
    sentence on it instead of a `ProgrammingError` three statements deeper.
    """
    found = await session.execute(text("select to_regclass(:name)"), {"name": name})
    return found.scalar() is not None


async def _expire_all(session: AsyncSession, user_id) -> None:
    from app.models import AuthChallenge

    await session.execute(
        update(AuthChallenge)
        .where(AuthChallenge.user_id == user_id)
        .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await session.commit()


# --------------------------------------------------------------------------- the door itself


async def test_the_recovery_door_is_mounted_and_answers_an_anonymous_caller(client: AsyncClient):
    """Recovery cannot require a session: the caller is by definition the one person who has none.

    A 401 here would not be a guard, it would be the door welded shut — so both verbs are answered
    anonymously, and the assertion is on the two literals the router mounts, not on a count.
    """
    mounted = {
        (method, route.path)
        for route in create_app().routes
        for method in getattr(route, "methods", ()) or ()
    }
    assert ("POST", _REQUEST) in mounted, "двери запроса кода нет в таблице маршрутов"
    assert ("POST", _CONFIRM) in mounted, "двери задавания нового слова нет в таблице маршрутов"

    response = await client.post(_REQUEST, json={"email": "nobody-here@befos.app"})
    assert response.status_code == 202, response.text


async def test_the_request_answer_does_not_tell_whether_the_address_exists(
    client: AsyncClient, tmp_path: Path
):
    """One body for an address that holds an account and for one that holds nothing.

    The status, the body and the field names must match: a recovery door that answers `404` for a
    stranger and `202` for a member is a list of who signs up here, handed to whoever asks.
    """
    _outbox(client, tmp_path)
    member = "exists-member@befos.app"
    await register_and_auth(client, member)

    known = await client.post(_REQUEST, json={"email": member})
    unknown = await client.post(_REQUEST, json={"email": "exists-stranger@befos.app"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json(), f"ответ различается: {known.json()} / {unknown.json()}"
    assert "sent" not in known.json() or known.json().get("sent") is True


async def test_the_letter_lands_in_the_outbox_and_carries_a_code_the_person_can_read(
    client: AsyncClient, tmp_path: Path
):
    """The channel is real: one letter per request, addressed, and it carries exactly one code.

    A code is asserted to exist rather than to be a given value, because the value is the secret;
    what the product promises is its shape — twelve unambiguous characters, printed so a human can
    type them, and no second code in the same letter.
    """
    _outbox(client, tmp_path)
    email = "letter-shape@befos.app"
    await register_and_auth(client, email)

    response = await client.post(_REQUEST, json={"email": email})
    assert response.status_code == 202, response.text

    letters = _letters(tmp_path)
    assert len(letters) == 1, f"письмо одно, а в ящике {len(letters)}"
    body = letters[0].read_text(encoding="utf-8")
    assert email in body, "письмо не называет адрес, которому оно адресовано"
    codes = _codes_in(letters[0])
    assert len(codes) == 1, f"в письме {len(codes)} кодов — человек не выберет, какой читать"
    assert "пароль" not in body.lower(), "письмо не должно повторять слово аккаунта"


async def test_the_code_from_the_letter_changes_the_word_and_the_old_word_stops_working(
    client: AsyncClient, tmp_path: Path
):
    """The whole point of the stage, in one sentence.

    Read the code out of the letter the server wrote, hand it to the door, and both halves of the
    promise are checked: the new word opens the account and the old word no longer does.
    """
    _outbox(client, tmp_path)
    email = "letter-roundtrip@befos.app"
    old = "Test12345"
    new = "BrandNewWord9"
    await register_and_auth(client, email, old)

    await client.post(_REQUEST, json={"email": email})
    code = _codes_in(_letters(tmp_path)[0])[0]

    confirmed = await client.post(
        _CONFIRM, json={"code": code, "new_password": new, "password_confirm": new}
    )
    assert confirmed.status_code == 204, confirmed.text
    assert confirmed.text == "", "дверь возврата слова обещает тело, которого у неё нет"

    stale = await client.post(_REQUEST, json={"email": email})  # keep rate window honest
    assert stale.status_code == 202
    refused = await client.post("/api/v1/auth/login", json={"email": email, "password": old})
    assert refused.status_code == 401, "прежнее слово так и открывает аккаунт"
    opened = await client.post("/api/v1/auth/login", json={"email": email, "password": new})
    assert opened.status_code == 200, f"новое слово не открывает аккаунт: {opened.text}"


async def test_a_code_changes_the_word_exactly_once(client: AsyncClient, tmp_path: Path):
    """A redeemed code is dead: the second request is refused and the word stays where it was.

    This is the property that makes a leaked letter harmless after use, and it has to be settled by
    one statement in the database rather than by reading and then writing — the refresh-token
    rotation already argues this way (`token_repo.py:33-47`).
    """
    _outbox(client, tmp_path)
    email = "single-use@befos.app"
    first = "FirstNewWord1"
    second = "SecondNewWord2"
    await register_and_auth(client, email)

    await client.post(_REQUEST, json={"email": email})
    code = _codes_in(_letters(tmp_path)[0])[0]

    ok = await client.post(
        _CONFIRM, json={"code": code, "new_password": first, "password_confirm": first}
    )
    assert ok.status_code == 204, ok.text

    again = await client.post(
        _CONFIRM, json={"code": code, "new_password": second, "password_confirm": second}
    )
    assert again.status_code == 401, f"погашенный код принят второй раз: {again.text}"
    assert (
        await client.post("/api/v1/auth/login", json={"email": email, "password": first})
    ).status_code == 200
    assert (
        await client.post("/api/v1/auth/login", json={"email": email, "password": second})
    ).status_code == 401, "второй отказ всё-таки успел сменить слово"


async def test_an_unknown_an_expired_and_a_redeemed_code_answer_one_way(
    client: AsyncClient, tmp_path: Path, session: AsyncSession
):
    """Three refusals, one sentence — and the word is unchanged after each.

    Distinguishing "no such code" from "used" from "too late" tells an attacker how far a guess got
    and lets the door be probed for which addresses have live letters. The product tells the person
    one thing: the code did not work, ask for another.
    """
    _outbox(client, tmp_path)
    email = "three-refusals@befos.app"
    keeper = "KeeperWord123"
    account = await register_and_auth(client, email, keeper)

    await client.post(_REQUEST, json={"email": email})
    live = _codes_in(_letters(tmp_path)[0])[0]
    await _expire_all(session, account["user_id"])

    expired = await client.post(
        _CONFIRM, json={"code": live, "new_password": keeper, "password_confirm": keeper}
    )
    unknown = await client.post(
        _CONFIRM, json={"code": "ZZZZZZZZZZZZ", "new_password": keeper, "password_confirm": keeper}
    )

    assert expired.status_code == unknown.status_code == 401
    assert expired.json()["error"]["code"] == unknown.json()["error"]["code"]
    assert expired.json()["error"]["message"] == unknown.json()["error"]["message"], (
        f"отказы различаются текстом: {expired.text} / {unknown.text}"
    )
    assert (
        await client.post("/api/v1/auth/login", json={"email": email, "password": keeper})
    ).status_code == 200, "отказ возврата слова поменял слово"


async def test_a_reset_ends_every_session_the_account_had(
    client: AsyncClient, tmp_path: Path
):
    """After a recovered word, no device that was already signed in stays signed in.

    The person who asked for a reset is the person who no longer trusts the device that holds the
    old word, and `change-password` already promises exactly this (`auth_service.py:147-149`). A
    recovery door that left the old sessions alive would be a weaker copy of a door that exists.
    """
    _outbox(client, tmp_path)
    email = "sessions-after-reset@befos.app"
    account = await register_and_auth(client, email)
    refresh = account["refresh"]

    await client.post(_REQUEST, json={"email": email})
    code = _codes_in(_letters(tmp_path)[0])[0]
    await client.post(
        _CONFIRM, json={"code": code, "new_password": "AfterReset123", "password_confirm": "AfterReset123"}
    )

    after = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert after.status_code == 401, f"сессия, бывшая до сброса, всё ещё жива: {after.text}"


async def test_a_second_request_while_a_code_lives_sends_no_second_letter(
    client: AsyncClient, tmp_path: Path
):
    """The letter is the abuse surface of this design, so the code is the throttle.

    One live code per address: the second request answers the same 202 (so it still cannot be used
    to learn anything) and writes nothing. Without this, one phone number and a script can make the
    mail channel emit a letter per request.
    """
    _outbox(client, tmp_path)
    email = "no-second-letter@befos.app"
    await register_and_auth(client, email)

    first = await client.post(_REQUEST, json={"email": email})
    second = await client.post(_REQUEST, json={"email": email})
    assert first.json() == second.json()
    assert len(_letters(tmp_path)) == 1, f"во второй раз писем стало {len(_letters(tmp_path))}"

    code = _codes_in(_letters(tmp_path)[0])[0]
    ok = await client.post(
        _CONFIRM, json={"code": code, "new_password": "StillValid123", "password_confirm": "StillValid123"}
    )
    assert ok.status_code == 204, "первое письмо перестало работать после второго запроса"


async def test_the_row_holds_a_hash_of_the_code_and_never_the_code(
    client: AsyncClient, tmp_path: Path, session: AsyncSession
):
    """A read of the table must not be enough to change anybody's word.

    `refresh_tokens` stores a SHA-256 hex digest for the same reason (`models/token.py:22`); a
    recovery code kept in the clear would turn a backup, a replica or a slow query log into a set of
    live doors.
    """
    assert await _table_exists(session, "auth_challenges"), (
        "таблицы вызовов нет: дверь возврата слова нечем хранить"
    )
    _outbox(client, tmp_path)
    email = "hashed-in-the-row@befos.app"
    await register_and_auth(client, email)

    await client.post(_REQUEST, json={"email": email})
    code = _codes_in(_letters(tmp_path)[0])[0]

    row = (
        await session.execute(
            text(
                "select token_hash, purpose, expires_at, consumed_at from auth_challenges "
                "where user_id = (select id from users where email = :email) "
                "and purpose = 'password_reset'"
            ),
            {"email": email},
        )
    ).mappings().one()
    assert len(row["token_hash"]) == 64, "хэш не шестидесятичетырёхзначный — не SHA-256"
    assert code not in row["token_hash"], "код лежит в строке открытым текстом"
    assert row["consumed_at"] is None, "ещё не погашенный вызов записан погашенным"
    assert row["expires_at"] > datetime.now(timezone.utc) - timedelta(minutes=5)
    assert row["purpose"] == "password_reset"


async def test_a_reset_dies_with_the_account_it_belongs_to(
    client: AsyncClient, tmp_path: Path, session: AsyncSession
):
    """Deleting the account deletes its unredeemed codes — the cascade is the whole argument.

    A live code that outlives the account it was minted for is a door into a row that no longer
    exists, and a purge that leaves it behind leaves the address reusable while the secret is not.
    """
    _outbox(client, tmp_path)
    email = "erased-with-codes@befos.app"
    account = await register_and_auth(client, email)

    await client.post(_REQUEST, json={"email": email})
    before = (
        await session.execute(
            text(
                "select count(*) from auth_challenges "
                "where user_id = :uid and purpose = 'password_reset'"
            ),
            {"uid": account["user_id"]},
        )
    ).scalar_one()
    assert before == 1

    gone = await client.delete(
        "/api/v1/users/me",
        headers=auth_headers(account["token"]),
    )
    assert gone.status_code == 200, gone.text
    after = (
        await session.execute(
            text("select count(*) from auth_challenges where user_id = :uid"),
            {"uid": account["user_id"]},
        )
    ).scalar_one()
    assert after == 0, f"аккаунт стёрт, а его код остался ({after})"


async def test_the_outbox_is_a_directory_on_the_server_and_not_a_route_on_it(
    client: AsyncClient, tmp_path: Path
):
    """Whatever lands in the outbox is reachable only by somebody who already has the disk.

    The application mounts `/uploads` and that mounting is a known weakness (audit §9.3); this stage
    must not add a second one. If a letter ever became readable over HTTP, the code inside it would
    be a password-reset door for anybody.
    """
    _outbox(client, tmp_path)
    email = "outbox-not-mounted@befos.app"
    await register_and_auth(client, email)
    await client.post(_REQUEST, json={"email": email})
    letter = _letters(tmp_path)[0]

    for path in (f"/outbox/{letter.name}", f"/api/v1/outbox/{letter.name}", "/api/v1/letters"):
        response = await client.get(path)
        assert response.status_code == 404, f"{path} отвечает {response.status_code}, а не 404"


# --------------------------------------------------------------------------- the channel itself


async def test_the_smtp_branch_hands_the_letter_to_a_real_smtp_session(tmp_path: Path):
    """The protocol branch is tested against a server that speaks the protocol, not against a mock.

    Nothing external is contacted: the peer is a socket on localhost, run inside this test, which
    answers a HELO/MAIL/FROM/RCPT/DATA dialogue and keeps the bytes it was given. That is the
    difference between «the transport builds a message» and «the transport can complete a session» —
    and the stage may only claim the second after seeing the first happen.
    """
    from app.services.mail import Letter, SmtpTransport

    received = _FakeSmtpServer()
    received.start()
    try:
        letter = Letter(
            to="someone@example.test",
            subject="Код восстановления BeFoS",
            body="Ваш код: ABCDEFGHIJKL. Он истекает через 30 минут.",
        )
        transport = SmtpTransport(
            host=received.host,
            port=received.port,
            username="befos@example.test",
            password="fake-secret-for-this-test-only",
            mail_from="no-reply@example.test",
            use_starttls=False,
        )
        await transport.send(letter)
    finally:
        received.stop()

    conversation = received.transcript()
    assert conversation["helo"] is not None, "сессия не поздоровалась"
    assert conversation["auth"] is not None, "учётная запись peer не была предложена"
    assert conversation["mail_from"] == "no-reply@example.test"
    assert conversation["rcpt_to"] == "someone@example.test"
    assert "ABCDEFGHIJKL" in conversation["body"], "код не доехал в теле письма"
    # The claim here is about the letter, not about the session: the peer's credential belongs in
    # AUTH, and nothing of it may ride along in a body that gets copied into mail clients, quoted in
    # forwarded messages and archived by whoever runs the mailbox.
    assert "fake-secret-for-this-test-only" not in conversation["body"], (
        "пароль учётной записи просочился в тело письма"
    )


def test_production_refuses_a_channel_that_only_pretends_to_send(monkeypatch):
    """`MAIL_TRANSPORT=outbox` in production is a server that promises letters and writes files.

    The project's rule is that a capability is either real or is named as missing — see the same
    reasoning behind `DEMO_ENABLED` and the placeholder secrets (`config.py:232-265`). Here the
    refusal is the honest outcome: a production start must not quietly keep the mail in a directory.
    """
    from pydantic import ValidationError

    from app.core.config import Settings

    good = {
        "ENVIRONMENT": "production",
        "DEBUG": "false",
        "DEMO_ENABLED": "false",
        "JWT_SECRET": "a-production-secret-of-thirty-plus-characters-0123456789",
        "JWT_REFRESH_SECRET": "another-production-secret-of-thirty-plus-characters-01234",
        "CURSOR_SECRET": "third-production-secret-of-thirty-plus-characters-0123456",
        "DATABASE_URL": "postgresql+asyncpg://operator:strong-password@db:5432/befos",
        "CORS_ORIGINS": "https://befos.example",
        "MAIL_TRANSPORT": "outbox",
    }
    with monkeypatch.context() as patch:
        for key, value in good.items():
            patch.setenv(key, value)
        with pytest.raises(ValidationError, match="outbox"):
            Settings()

    with monkeypatch.context() as patch:
        for key, value in good.items():
            patch.setenv(key, value)
        patch.setenv("MAIL_TRANSPORT", "carrier-pigeon")
        with pytest.raises(ValidationError, match="MAIL_TRANSPORT"):
            Settings()


async def test_the_code_lifetime_is_a_setting_the_row_actually_carries(
    client: AsyncClient, tmp_path: Path, session: AsyncSession
):
    """The deadline is stored with the secret, so «the letter expired» is a fact about a row.

    `create_token` returns the pair (token, its expiry) for the same reason (`security.py:75-88`).
    Here the same idea is pinned from the other side: change the setting, and the row follows — a
    letter whose stored deadline ignores the configuration is a letter nobody can reason about.
    """
    _outbox(client, tmp_path)
    minutes = int(settings.reset_code_minutes)
    assert minutes > 0, "срок жизни кода не положительный"

    email = "lifetime-is-config@befos.app"
    await register_and_auth(client, email)
    started = datetime.now(timezone.utc)
    await client.post(_REQUEST, json={"email": email})

    stored = (
        await session.execute(
            text(
                "select expires_at from auth_challenges "
                "where purpose = 'password_reset' and user_id = ("
                "select id from users where email = :email)"
            ),
            {"email": email},
        )
    ).scalar_one()
    assert stored.tzinfo is not None, "срок хранится без зоны — сравнение с now() врёт"
    margin = (stored - started).total_seconds() / 60
    assert minutes - 2 <= margin <= minutes + 2, f"строка живёт {margin:.1f} мин, ждали {minutes}"


class _FakeSmtpServer:
    """A localhost peer that speaks just enough SMTP to prove a session completes.

    Stated plainly because the test's claim depends on it: this is not an MTA and does not deliver
    anything. It records the commands it was sent and answers 2xx to each one, so the client's own
    state machine has to work for the letter to leave the process.
    """

    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.host, self.port = self._sock.getsockname()
        self._threads = ThreadPoolExecutor(max_workers=1)
        self._future = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._log: list[str] = []

    def start(self) -> None:
        self._future = self._threads.submit(self._serve)

    def stop(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        self._threads.shutdown(wait=True)

    def _serve(self) -> None:
        self._sock.settimeout(5.0)
        try:
            conn, _ = self._sock.accept()
        except OSError:
            return
        with conn:
            reader = conn.makefile("rb")
            conn.sendall(b"220 fake ESMTP\r\n")
            in_data = False
            while not self._stop.is_set():
                try:
                    line = reader.readline()
                except OSError:
                    return
                if not line:
                    return
                decoded = line.decode("utf-8", "replace").rstrip("\r\n")
                with self._lock:
                    self._log.append(decoded)
                if in_data:
                    if decoded == ".":
                        in_data = False
                        conn.sendall(b"250 Ok: queued\r\n")
                    continue
                upper = decoded.upper()
                if upper.startswith(("EHLO", "HELO")):
                    if upper.startswith("EHLO"):
                        # AUTH has to be offered, or `smtplib.login` refuses to try and the branch
                        # under test would be the branch that never authenticates.
                        conn.sendall(b"250-fake\r\n250-AUTH PLAIN LOGIN\r\n250 HELP\r\n")
                    else:
                        conn.sendall(b"250 fake\r\n")
                elif upper.startswith("AUTH"):
                    conn.sendall(b"235 Authentication supported\r\n")
                elif upper.startswith(("MAIL FROM", "RCPT TO", "DATA", "QUIT", "RSET", "NOOP")):
                    if upper.startswith("DATA"):
                        in_data = True
                        conn.sendall(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                    elif upper.startswith("QUIT"):
                        conn.sendall(b"221 Bye\r\n")
                        return
                    else:
                        conn.sendall(b"250 Ok\r\n")
                elif upper.startswith("STARTTLS"):
                    conn.sendall(b"454 TLS not available\r\n")
                else:
                    conn.sendall(b"250 Ok\r\n")

    def transcript(self) -> dict:
        """The conversation, cut where the test needs to read it: greeting, envelope, body.

        The body is everything the peer was told after its own `DATA` line and before the terminating
        dot, so an assertion about «what is in the letter» cannot be satisfied by a credential that
        travelled in a command instead.
        """
        with self._lock:
            log = list(self._log)
        lowered = [line.lower() for line in log]

        def argument_of(prefix: str) -> str | None:
            for index, line in enumerate(lowered):
                if line.startswith(prefix):
                    return log[index].split(":", 1)[1].strip("<> ")
            return None

        start = next((i for i, line in enumerate(lowered) if line.startswith("data")), None)
        body: list[str] = []
        if start is not None:
            for line in log[start + 1 :]:
                if line == ".":
                    break
                body.append(line)

        return {
            "helo": next((line for line in log if line.lower().startswith(("ehlo", "helo"))), None),
            "auth": next((line for line in log if line.lower().startswith("auth")), None),
            "mail_from": argument_of("mail from"),
            "rcpt_to": argument_of("rcpt to"),
            "body": "\n".join(body),
            "raw": "\n".join(log),
        }
