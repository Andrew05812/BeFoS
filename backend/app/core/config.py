from __future__ import annotations

from functools import lru_cache
from urllib.parse import unquote, urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Known-insecure placeholder secrets shipped for local development only.
_INSECURE_DEFAULTS = {
    "change-me-access-secret-key-min-32-chars",
    "change-me-refresh-secret-key-min-32-chars",
}
# The password the development database of this repository is created with. It is printed
# in .env.example, in docker-compose.yml as a default, and in the README's local-run steps,
# so a deployment that kept it has a database password anybody with the repository knows.
_INSECURE_DB_PASSWORDS = {"befos_password"}
# The address the development default sends letters from. A placeholder in the same sense as the two
# JWT secrets above: it names a domain nobody owns, so a deployment that kept it is mailing as
# somebody else, and the production validator refuses it for the same reason it refuses
# `befos_password` — the value is printed in this repository.
_INSECURE_MAIL_FROM = "no-reply@befos.local"
_MIN_SECRET_LEN = 32
# The key that seals a page link. Kept apart from the two session keys on purpose: a link names a
# place in one reader's own list and is worthless outside it, while a forged access token opens the
# account. Sharing one secret would make the cheaper object — pages are handed out on every scroll —
# the guard of the more valuable one, and would tie their rotation together.
_INSECURE_CURSOR_DEFAULT = "change-me-cursor-secret-min-32-chars"
# The bounds of a page link's life, in minutes. The lower one keeps a link from being a permanent
# claim; the upper one is a day, past which a person who left a list open overnight is better off
# reading it again than resuming a frontier a day old.
_CURSOR_LIFE_MIN, _CURSOR_LIFE_MAX = 1, 1440
# A key id that says nothing is a key ring of one anonymous key, which is how a rotation stops being
# auditable: the id in the link is the only record of which secret sealed it.
_CURSOR_KID_MAX_LEN = 16
# The deployment reads as production only when it says so in one of these two words. A
# typo here silently turns every guard below off, so an unknown value is a startup error.
_KNOWN_ENVIRONMENTS = {"development", "dev", "test", "staging", "production", "prod"}
_DEFAULT_DATABASE_URL = "postgresql+asyncpg://befos:befos_password@localhost:5432/befos"


def _database_password(database_url: str) -> str | None:
    """The password component of a DSN, or None when there is nothing to compare.

    A DSN this function cannot read is not a security question: asyncpg fails on it when
    the app first tries to connect, and refusing startup here would turn a typo in a
    password containing '@' into a mystery.
    """
    try:
        password = urlsplit(database_url).password
    except ValueError:
        return None
    if password is None:
        return None
    return unquote(password)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = Field(default="BeFoS", alias="APP_NAME")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=True, alias="DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    backend_host: str = Field(default="0.0.0.0", alias="BACKEND_HOST")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")

    database_url: str = Field(default=_DEFAULT_DATABASE_URL, alias="DATABASE_URL")

    jwt_secret: str = Field(default="change-me-access-secret-key-min-32-chars", alias="JWT_SECRET")
    jwt_refresh_secret: str = Field(
        default="change-me-refresh-secret-key-min-32-chars", alias="JWT_REFRESH_SECRET"
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=30, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    cursor_secret: str = Field(default=_INSECURE_CURSOR_DEFAULT, alias="CURSOR_SECRET")
    cursor_key_id: str = Field(default="a", alias="CURSOR_KEY_ID")
    # The key a rotation retired. A link is a place in a list a person is walking, so turning the
    # current key off instantly would stop every walk in progress: the retired key is still accepted
    # until the links it sealed age out on their own, and it is dropped from the ring at the next
    # rotation. Its id travels in the link, so nothing has to be remembered between the two.
    cursor_secret_previous: str = Field(default="", alias="CURSOR_SECRET_PREVIOUS")
    cursor_key_id_previous: str = Field(default="", alias="CURSOR_KEY_ID_PREVIOUS")
    cursor_link_minutes: int = Field(default=720, alias="CURSOR_LINK_MINUTES")

    cors_origins: str = Field(default="http://localhost:8000", alias="CORS_ORIGINS")

    upload_dir: str = Field(default="./uploads", alias="UPLOAD_DIR")
    max_upload_size_mb: int = Field(default=5, alias="MAX_UPLOAD_SIZE_MB")

    rate_limit_per_minute: int = Field(default=120, alias="RATE_LIMIT_PER_MINUTE")
    # Only enable when a reverse proxy in front of the app sets X-Forwarded-For. This is the
    # app's half of the boundary; the server has to keep its own address out of the picture, so
    # the shipped commands start uvicorn with --no-proxy-headers (its defaults rewrite the peer
    # address for loopback connections before this setting is ever read).
    trust_proxy_headers: bool = Field(default=False, alias="TRUST_PROXY_HEADERS")

    demo_enabled: bool = Field(default=True, alias="DEMO_ENABLED")
    demo_email: str = Field(default="demo@befos.app", alias="DEMO_EMAIL")
    demo_password: str = Field(default="Demo12345", alias="DEMO_PASSWORD")

    # --- The letter channel: how a code leaves this process, if it leaves at all. ---
    # `outbox` writes the letter into a directory on the host and is the development default, because
    # this repository has never held a mail credential and must not invent one — the same reasoning
    # that left the release unsigned (`docs/RELEASE.md` §11, item 1). `smtp` completes a real session
    # with the standard library and nothing else: no dependency is added here, and no provider is
    # contacted until the operator names one in the environment.
    mail_transport: str = Field(default="outbox", alias="MAIL_TRANSPORT")
    mail_outbox_dir: str = Field(default="./outbox", alias="MAIL_OUTBOX_DIR")
    mail_from: str = Field(default=_INSECURE_MAIL_FROM, alias="MAIL_FROM")
    # The absolute prefix a letter is allowed to print as a link. Empty means the letter prints the
    # code and nothing else, which is the honest default: a link built out of a host nobody configured
    # is a broken door inside the one message whose whole job is to be a door.
    mail_link_base: str = Field(default="", alias="MAIL_LINK_BASE")
    # The prefix a personal invitation is printed under. A custom scheme is the honest default
    # while no web front door exists: an `https://` link here would be a promise that a page opens,
    # and no page does. A deployment that owns a domain overrides it, and the client keeps parsing
    # the code as the last path segment either way.
    invite_link_base: str = Field(default="befos://invite", alias="INVITE_LINK_BASE")
    mail_smtp_host: str = Field(default="", alias="MAIL_SMTP_HOST")
    mail_smtp_port: int = Field(default=587, alias="MAIL_SMTP_PORT")
    mail_smtp_username: str = Field(default="", alias="MAIL_SMTP_USERNAME")
    mail_smtp_password: str = Field(default="", alias="MAIL_SMTP_PASSWORD")
    mail_smtp_starttls: bool = Field(default=True, alias="MAIL_SMTP_STARTTLS")
    # How long a recovery code stays spendable. Half an hour is roughly the window in which a person
    # who just lost their word is still sitting at the screen that lost it; past a couple of hours the
    # letter is a door left open on a mailbox that may be shared, rather than an answer to a question
    # that was just asked.
    reset_code_minutes: int = Field(default=30, alias="RESET_CODE_MINUTES")
    # How long the code that proves a mailbox stays spendable. Longer than a recovery code on purpose:
    # a recovery letter answers a question asked a minute ago, while the confirmation letter is waiting
    # for somebody who registered and then went back to their work. A day is the ceiling — past that the
    # letter is less a proof of a request than a door left ajar on an address that may have changed hands
    # — and five minutes the floor, for the same reading-speed reason as above.
    confirm_code_minutes: int = Field(default=60, alias="CONFIRM_CODE_MINUTES")

    @field_validator("cors_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("environment")
    @classmethod
    def _known_environment(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if cleaned not in _KNOWN_ENVIRONMENTS:
            raise ValueError(
                f"ENVIRONMENT={v!r} is not one of {sorted(_KNOWN_ENVIRONMENTS)}. A value that "
                "is not understood reads as 'not production', which is how every production "
                "guard below gets skipped by a typo."
            )
        return cleaned

    @field_validator("cursor_key_id")
    @classmethod
    def _named_key(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError(
                "CURSOR_KEY_ID names the secret that sealed a link, and an empty name is not a "
                "name: the id is the only record of which key a link was read against."
            )
        return cleaned

    @field_validator("cursor_key_id", "cursor_key_id_previous")
    @classmethod
    def _cursor_kid_shape(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) > _CURSOR_KID_MAX_LEN:
            raise ValueError(
                f"CURSOR_KEY_ID is longer than {_CURSOR_KID_MAX_LEN} characters; it travels "
                "inside every page link, so a long name is paid for on every scroll."
            )
        if "." in cleaned or "|" in cleaned:
            raise ValueError(
                "CURSOR_KEY_ID may not contain '.' or '|': the first separates the fields of a "
                "link and the second separates the fields of its payload, so a separator inside "
                "the name makes a link unreadable to the code that reads it back."
            )
        return cleaned

    @field_validator("cursor_link_minutes")
    @classmethod
    def _link_life(cls, v: int) -> int:
        if not _CURSOR_LIFE_MIN <= v <= _CURSOR_LIFE_MAX:
            raise ValueError(
                f"CURSOR_LINK_MINUTES={v} is outside {_CURSOR_LIFE_MIN}..{_CURSOR_LIFE_MAX}. "
                "A zero or negative life refuses every page as soon as it is issued; a life "
                "measured in weeks is a claim that a frontier an old walk left behind still leads "
                "somewhere."
            )
        return v

    @model_validator(mode="after")
    def _cursor_ring_is_consistent(self) -> "Settings":
        """The retired key comes as a pair, or it is not a key the ring can hold.

        A secret without an id cannot be looked up from a link, and an id without a secret turns the
        acceptance of an old link into a crash rather than a refusal. Both halves are also checked
        against the current key: two entries under one id would make the ring's answer depend on the
        order the ring was built in, which is the one question a rotation must not leave open.
        """
        if bool(self.cursor_secret_previous) != bool(self.cursor_key_id_previous):
            raise ValueError(
                "CURSOR_SECRET_PREVIOUS and CURSOR_KEY_ID_PREVIOUS come as a pair: a link carries "
                "the id and the ring must carry the secret that matches it."
            )
        if self.cursor_key_id_previous and self.cursor_key_id_previous == self.cursor_key_id:
            raise ValueError(
                "CURSOR_KEY_ID_PREVIOUS repeats the current id, so a link sealed by either key "
                "reads the same and the rotation cannot be told apart."
            )
        if self.cursor_secret_previous and self.cursor_secret_previous == self.cursor_secret:
            raise ValueError(
                "CURSOR_SECRET_PREVIOUS repeats the current secret under another id: the rotation "
                "would change nothing about what an attacker can forge."
            )
        return self

    @field_validator("reset_code_minutes")
    @classmethod
    def _code_life(cls, v: int) -> int:
        if not 5 <= v <= 180:
            raise ValueError(
                f"RESET_CODE_MINUTES={v} is outside 5..180. Under five minutes a code is refused "
                "before a person has read it off one screen and typed it into another; past three "
                "hours it is a door left standing on a mailbox that may be shared."
            )
        return v

    @field_validator("confirm_code_minutes")
    @classmethod
    def _confirmation_life(cls, v: int) -> int:
        if not 5 <= v <= 1440:
            raise ValueError(
                f"CONFIRM_CODE_MINUTES={v} is outside 5..1440. Under five minutes a code is refused "
                "before a person has read it off one screen and typed it into another; past a day "
                "it is no longer an answer to «I registered just now»."
            )
        return v

    @field_validator("invite_link_base")
    @classmethod
    def _invite_base(cls, v: str) -> str:
        cleaned = v.strip().rstrip("/")
        if not (cleaned.startswith("befos://") or cleaned.startswith("https://")):
            raise ValueError(
                "INVITE_LINK_BASE must name a scheme the client can open: `befos://invite` on the "
                "stand, or an https:// prefix once the owner has a web front door."
            )
        return cleaned

    @model_validator(mode="after")
    def _mail_channel_is_consistent(self) -> "Settings":
        """The channel a letter leaves by is named here, and in production it must really leave.

        Two rules, because they fail in different ways. The name is checked in every environment:
        `services/mail.py` raises when it is handed anything else, and a start that waits for the
        first recovery request to discover the typo is a start that already promised somebody a
        letter. Production then refuses `outbox` outright — writing a letter into a directory on the
        host while the door answers that a code is on its way is precisely the kind of capability
        this project has been told not to claim — and holds the SMTP branch to the settings that make
        it a session rather than a guess.
        """
        name = (self.mail_transport or "").strip().lower()
        if name not in {"outbox", "smtp"}:
            raise ValueError(
                f"MAIL_TRANSPORT={self.mail_transport!r} names no channel this build has; expected "
                "`outbox` (a directory on this host) or `smtp` (a real protocol session)."
            )
        if not self.is_production:
            return self
        if name == "outbox":
            raise ValueError(
                "MAIL_TRANSPORT must be `smtp` in production: `outbox` keeps the letter in a "
                "directory on this host while the door answers that a code is on its way, and that is "
                "a claim about delivery this build cannot support."
            )
        if not self.mail_smtp_host:
            raise ValueError(
                "MAIL_SMTP_HOST must name a peer in production, otherwise the channel the deployment "
                "chose has nowhere to connect to and every recovery request fails at the first byte."
            )
        if bool(self.mail_smtp_username) != bool(self.mail_smtp_password):
            raise ValueError(
                "MAIL_SMTP_USERNAME and MAIL_SMTP_PASSWORD come as a pair: one without the other is a "
                "peer this server cannot authenticate against, and the person waiting for a code will "
                "be told about mail rather than about a half-configured credential."
            )
        if self.mail_from == _INSECURE_MAIL_FROM:
            raise ValueError(
                "MAIL_FROM is still the shipped development address. It names a domain nobody owns, "
                "so a production deployment that kept it is mailing as somebody else — and the value "
                "is printed in this repository, which makes it a public choice rather than a default."
            )
        if not self.mail_smtp_starttls:
            raise ValueError(
                "MAIL_SMTP_STARTTLS must be true in production. This build speaks SMTP with the "
                "standard library and knows only STARTTLS, so with it off the recovery code — and the "
                "credential, since AUTH is sent after the greeting — crosses the network in the clear."
            )
        if self.mail_link_base and not self.mail_link_base.startswith("https://"):
            raise ValueError(
                "MAIL_LINK_BASE, when a deployment sets it, must be an https:// address: the link a "
                "letter prints is the shortest path from somebody else's mail client to a door on "
                "this account."
            )
        return self

    @model_validator(mode="after")
    def _reject_insecure_production_secrets(self) -> "Settings":
        """Fail fast if production runs with placeholder/short JWT secrets.

        Forgery of access/refresh tokens is trivial with the shipped defaults, so
        a production deployment must override them with strong values.
        """
        if not self.is_production:
            return self
        for name, value in (
            ("JWT_SECRET", self.jwt_secret),
            ("JWT_REFRESH_SECRET", self.jwt_refresh_secret),
        ):
            if value in _INSECURE_DEFAULTS or len(value) < _MIN_SECRET_LEN:
                raise ValueError(
                    f"{name} must be a strong secret (>= {_MIN_SECRET_LEN} chars, not the "
                    "development placeholder) when ENVIRONMENT=production."
                )
        if self.jwt_secret == self.jwt_refresh_secret:
            raise ValueError("JWT_SECRET and JWT_REFRESH_SECRET must differ in production.")
        if self.cursor_secret == _INSECURE_CURSOR_DEFAULT or len(self.cursor_secret) < _MIN_SECRET_LEN:
            raise ValueError(
                f"CURSOR_SECRET must be a strong secret (>= {_MIN_SECRET_LEN} chars, not the "
                "development placeholder) when ENVIRONMENT=production: an unsigned link is a "
                "claim the client makes, and a link sealed with a secret printed in this "
                "repository is the same claim wearing a signature nobody has to have."
            )
        for name, value in (
            ("JWT_SECRET", self.jwt_secret),
            ("JWT_REFRESH_SECRET", self.jwt_refresh_secret),
        ):
            if self.cursor_secret == value:
                raise ValueError(
                    f"CURSOR_SECRET may not equal {name} in production. The two keys answer "
                    "different questions — one opens an account, the other names a place in one "
                    "reader's list — so sharing them would make the secret that rotates with a "
                    "session compromise rotate the page links with it, and a leaked link-signing "
                    "key a token-forgery key."
                )
        if self.cursor_secret_previous and len(self.cursor_secret_previous) < _MIN_SECRET_LEN:
            raise ValueError(
                f"CURSOR_SECRET_PREVIOUS is shorter than {_MIN_SECRET_LEN} characters: a retired "
                "key is still a key the server accepts, so it is held to the same strength as the "
                "current one."
            )
        if "*" in self.cors_origin_list:
            raise ValueError("CORS_ORIGINS must not contain '*' in production.")
        if any(o.startswith("http://") for o in self.cors_origin_list):
            raise ValueError("CORS_ORIGINS must use https:// in production.")
        if self.database_url == _DEFAULT_DATABASE_URL:
            raise ValueError(
                "DATABASE_URL still points at the development database shipped in this "
                "repository; production must name its own."
            )
        db_password = _database_password(self.database_url)
        if db_password in _INSECURE_DB_PASSWORDS:
            # Comparing the whole URL, as the check above does, is not enough: the URL
            # docker-compose.yml assembles is `...@postgres:5432/befos`, which differs from
            # the literal in this file while carrying the same shipped password.
            raise ValueError(
                "DATABASE_URL still carries the development database password this "
                "repository ships ('befos_password'). docker-compose.yml builds the URL from "
                "${POSTGRES_PASSWORD:-befos_password}, so a stand started from that file as "
                "is gives a production app a database password anybody who read the "
                "repository can use."
            )
        if self.debug:
            raise ValueError(
                "DEBUG must be false in production. It drops the root log level to DEBUG, "
                "and third-party loggers then write their own internals into the same "
                "stream (asyncio's transport setup, httpx's per-request lines — both visible "
                "in the development stand's logs)."
            )
        if self.demo_enabled:
            raise ValueError(
                "DEMO_ENABLED must be false in production. The demo account's password is "
                "printed in README.md and DEMO.md, so a seeded demo login is a shared "
                "credential anybody with the repository can use."
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cursor_keys(self) -> dict[str, bytes]:
        """The ring a page link may have been sealed by, newest first.

        Keyed by id rather than tried in order: a link names the key it came from, so the server looks
        the secret up instead of guessing which of the two to test. That is also what lets a rotation be
        visible in a log line — the id says which key the walk was standing on.
        """
        ring = {self.cursor_key_id: self.cursor_secret.encode()}
        if self.cursor_secret_previous and self.cursor_key_id_previous:
            ring[self.cursor_key_id_previous] = self.cursor_secret_previous.encode()
        return ring

    @property
    def cursor_signing_key(self) -> tuple[str, bytes]:
        """The one key new links are sealed with."""
        return self.cursor_key_id, self.cursor_secret.encode()

    @property
    def cursor_link_seconds(self) -> int:
        return self.cursor_link_minutes * 60

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
