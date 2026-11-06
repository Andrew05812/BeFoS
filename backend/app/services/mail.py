"""Where a one-time code comes from, where it goes, and what happens if the channel is not there.

The recovery door in `api/v1/auth.py` mints a code and needs somebody to carry it to the person who
lost their word. This module is that carrier, and it is deliberately the only place in the product
that knows what carrying means: an `outbox` transport writes the letter into a directory on the
server, an `smtp` transport completes a real protocol session. The two are named differently because
the claim they support is different — «a letter exists on this host» is not «a letter left this
host», and a project that has published «почты нет» (audit §9, README «Чего в проекте нет») has to
be able to tell the two apart from the name.

Two rules the whole module obeys:

* Nothing here contacts an external service unless the operator pointed it at one, and nothing here
  ever holds a credential in the source tree. `SmtpTransport` takes its password as an argument; the
  value comes from the environment, and the settings validator in `core/config.py` refuses a
  production start that names `outbox` — a server that promises letters and files them is the kind
  of placeholder this project has been burned by before.
* The code never appears in a log line. `logger` calls below name a path or a peer and stop there:
  the code is the secret that changes an account's word, and an application log is a place where
  secrets go travelling.
"""

from __future__ import annotations

import asyncio
import os
import smtplib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

RESET_SUBJECT = "Код восстановления BeFoS"

# The alphabet and the length of a code are decided in `core/security.py`, where the secret is minted;
# this module only ever prints one. Splitting the two is what keeps a letter from becoming the place
# that decides how strong a door is.


class MailChannelUnavailable(RuntimeError):
    """The configuration names a channel this build does not have.

    Raised rather than answered: a request that was accepted and then quietly not sent is the exact
    dishonesty this module exists to avoid, so the caller gets a 500 and the operator gets a startup
    error long before that, because `core/config.py` refuses an unknown `MAIL_TRANSPORT` in any
    environment.
    """


@dataclass(frozen=True)
class Letter:
    """What the product can say about a message it is handing over: an address, a subject, a body."""

    to: str
    subject: str
    body: str


class MailTransport(Protocol):
    """One method, one claim: give this letter to the channel and report where it went."""

    async def send(self, letter: Letter) -> str:  # pragma: no cover - a protocol declaration
        ...


def format_code(code: str) -> str:
    """The code as a person reads it: four characters, a break, four, a break, four."""
    return "-".join(code[i : i + 4] for i in range(0, len(code), 4))


def password_reset_letter(to: str, code: str, minutes: int, link_base: str = "") -> Letter:
    """The letter that returns a lost word.

    Stated in the words the product has already published: it says what the code is for, how long it
    lives, that it works once, and that the person did not have to be signed in to ask. The code is
    printed grouped; the link line appears only when the operator configured a base for it, because
    a link built out of nothing is a broken promise in a letter whose whole job is to be a way in.
    """
    lines = [
        "Кто-то попросил вернуть доступ к аккаунту BeFoS с этим адресом.",
        "",
        f"Если это были вы, введите этот код в приложении: {format_code(code)}",
        "",
        f"Код действует {minutes} минут и принимается один раз.",
        "Если вы не просили ничего возвращать, ничего не делайте: без этого кода ничего не изменится.",
    ]
    if link_base:
        lines += ["", f"Можно открыть и по ссылке: {link_base.rstrip('/')}/{format_code(code)}"]
    lines += ["", "BeFoS — не диагноз и не оценка человека, а анкета и тест.", ""]
    return Letter(to=to, subject=RESET_SUBJECT, body="\n".join(lines))


class OutboxTransport:
    """Writes the letter into a directory on this host and says so.

    This is the development default and it is not a simulation of sending: the file is the letter,
    bytes and all, so the live path (`ops/e2e_journey.py`) can read a code out of it the way a person
    reads one out of a mail client. What it does not do is deliver anything anywhere, which is why
    production refuses to start on it.
    """

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)

    async def send(self, letter: Letter) -> str:
        return await asyncio.to_thread(self._write, letter)

    def _write(self, letter: Letter) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        moment = datetime.now(timezone.utc)
        name = f"{moment:%Y%m%dT%H%M%S%f}Z_{uuid.uuid4().hex[:8]}.eml"
        final = self.directory / name
        temporary = final.with_suffix(".part")
        headers = [
            f"From: {settings.mail_from}",
            f"To: {letter.to}",
            f"Subject: {letter.subject}",
            f"Date: {formatdate(timeval=moment.timestamp(), localtime=False)}",
            "Content-Type: text/plain; charset=utf-8",
            "",
        ]
        temporary.write_text("\n".join(headers) + letter.body, encoding="utf-8")
        # Written aside and moved in place, so a reader can never see half a letter: the live path
        # globs this directory, and a truncated file reads as a code that does not exist.
        os.replace(temporary, final)
        logger.info("Mail written to the outbox file=%s", name)
        return f"outbox:{final}"


class SmtpTransport:
    """Completes an SMTP session with a peer the operator named, using only the standard library.

    Deliberately small. There is no queue, no retry policy and no template engine here: a refused
    peer or a dropped connection raises, and the door that called it answers 500 rather than telling
    the person their letter is on its way. Retry and delivery status are a mail service's job, and
    inventing a worse one inside the app is how a project ends up claiming delivery it cannot show.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        mail_from: str,
        use_starttls: bool,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.mail_from = mail_from
        self.use_starttls = use_starttls
        self.timeout_seconds = timeout_seconds

    async def send(self, letter: Letter) -> str:
        return await asyncio.to_thread(self._send_sync, letter)

    def _send_sync(self, letter: Letter) -> str:
        message = EmailMessage()
        message["From"] = self.mail_from
        message["To"] = letter.to
        message["Subject"] = letter.subject
        message["Date"] = formatdate(localtime=False)
        message.set_content(letter.body, charset="utf-8")
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout_seconds) as client:
            client.ehlo()
            if self.use_starttls:
                client.starttls()
                client.ehlo()
            if self.username:
                # The credential travels in the AUTH command, base64-encoded — which is the whole
                # reason `use_starttls` is required in production by core/config.py, and why the
                # letter body below must never repeat it.
                client.login(self.username, self.password)
            client.send_message(message)
        logger.info("Mail handed to the SMTP peer host=%s", self.host)
        return f"smtp:{self.host}"


def current_transport() -> MailTransport:
    """The channel the configuration names, read at call time rather than imported once.

    Read at call time because the settings singleton is what a test retargets: a transport bound at
    import would keep pointing at whatever environment the process started in, and a stage that
    measures a channel has to be able to move it.
    """
    name = (settings.mail_transport or "").strip().lower()
    if name == "outbox":
        return OutboxTransport(settings.mail_outbox_dir)
    if name == "smtp":
        return SmtpTransport(
            host=settings.mail_smtp_host,
            port=settings.mail_smtp_port,
            username=settings.mail_smtp_username,
            password=settings.mail_smtp_password,
            mail_from=settings.mail_from,
            use_starttls=settings.mail_smtp_starttls,
        )
    raise MailChannelUnavailable(
        f"MAIL_TRANSPORT={name!r} names no channel this build has; expected outbox or smtp"
    )
