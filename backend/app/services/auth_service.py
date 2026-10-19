from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError, ValidationError
from app.core.logging import get_logger
from app.core.security import (
    TIMING_FILLER_HASH,
    create_token,
    decode_token,
    generate_token_hash,
    hash_password_async,
    verify_password_async,
)
from app.models import Profile, User
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository

logger = get_logger(__name__)


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.tokens = TokenRepository(session)

    async def register(self, email: str, password: str, password_confirm: str) -> User:
        if password != password_confirm:
            raise ValidationError("Passwords do not match.")
        if await self.users.email_exists(email):
            raise ConflictError("An account with this email already exists.")
        # A double tap posts the same email twice before either insert has committed, so the
        # read above cannot be the only gate: the unique index decides, and the loser hears
        # the same answer it would have heard from a serial retry.
        try:
            user = User(
                email=email.lower(),
                password_hash=await hash_password_async(password),
                is_active=True,
            )
            await self.users.create(user)
        except IntegrityError:
            await self.session.rollback()
            raise ConflictError("An account with this email already exists.")
        # Create an empty profile shell so downstream code always has one. It stays out of
        # everybody's deck until onboarding stamps it: this row has a name copied from an
        # email and a birth date copied from a constant, and a card is supposed to be a
        # person who answered.
        profile = Profile(
            user_id=user.id,
            name=email.split("@")[0][:80],
            birth_date=_default_birth_date(),
            city="",
            gender="other",
            dating_goal="relationship",
            gender_preference=[],
            lifestyle={},
        )
        self.session.add(profile)
        await self.session.flush()
        logger.info("Registered new user id=%s", user.id)
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.users.get_by_email(email)
        # Constant-ish behaviour: do not reveal whether the email exists. The check below used to be
        # skipped for an address that has no account, which answered the two refusals 451 ms apart;
        # now both of them pay for one bcrypt, the unknown one against a filler hash that guards no
        # account. See `TIMING_FILLER_HASH`.
        password_hash = user.password_hash if user is not None else TIMING_FILLER_HASH
        password_ok = await verify_password_async(password, password_hash)
        if user is None or not password_ok:
            raise UnauthorizedError("Invalid email or password.")
        if user.is_deleted:
            raise UnauthorizedError("Account is deactivated.")
        if not user.is_active:
            raise UnauthorizedError("Account is disabled.")
        return user

    async def issue_tokens(self, user: User, user_agent: str | None = None) -> dict:
        refresh, expires = create_token(user.id, "refresh")
        row = await self.tokens.add(user.id, generate_token_hash(refresh), expires, user_agent)
        # The access token names the session row its pair just opened. Without that link an account
        # can be told which devices hold it but cannot be told which of them it is standing on, and a
        # list of sessions that cannot point at itself invites the person to end the one they are
        # reading it with. The row is written first so its id is known before the token is signed.
        access, _ = create_token(user.id, "access", {"sid": str(row.id)})
        await self.session.commit()
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
        }

    async def refresh(self, refresh_token: str, user_agent: str | None = None) -> dict:
        import jwt as _jwt

        try:
            payload = decode_token(refresh_token, "refresh")
        except _jwt.PyJWTError:
            raise UnauthorizedError("Invalid or expired refresh token.")

        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid token type.")

        user = await self.users.get_by_id(uuid.UUID(payload["sub"]))
        if user is None or not user.is_active or user.is_deleted:
            raise UnauthorizedError("User no longer active.")

        # Rotate: redeem the old token and issue a new pair in one transaction. The stored row is
        # not raised first — ``consume`` is an ``UPDATE … WHERE revoked = false``, so its row count
        # already says whether a live token with this hash was there, and both fates (never stored,
        # or already redeemed) answer the same one thing. Reading the row beforehand decided
        # nothing: it only opened a window in which two requests could each see the token active.
        # That window is what made ``consume`` the arbiter of the rotation — a token that arrives
        # twice at the same instant is turned into a session by exactly one request, because the
        # loser re-evaluates the predicate only after the winner commits and matches no row.
        if not await self.tokens.consume(generate_token_hash(refresh_token)):
            raise UnauthorizedError("Refresh token has been revoked.")
        return await self.issue_tokens(user, user_agent)

    async def logout(self, user_id: uuid.UUID, refresh_token: str | None) -> None:
        if refresh_token:
            # One statement: the same guard the read applied in Python — this caller owns the row
            # and the row is still live — now sits in the WHERE clause of the write.
            await self.tokens.revoke_for_owner(generate_token_hash(refresh_token), user_id)
        await self.session.commit()

    async def change_password(
        self, user: User, old_password: str, new_password: str, password_confirm: str
    ) -> None:
        # The same two questions register asks, kept in the one place a password is written: the new
        # word said twice, and long enough. A rule split between a route and a service is a rule that
        # drifts the first time one of them is edited.
        if new_password != password_confirm:
            raise ValidationError("Passwords do not match.")
        if len(new_password) < 8:
            raise ValidationError("Password must be at least 8 characters.")
        if not await verify_password_async(old_password, user.password_hash):
            raise UnauthorizedError("Current password is incorrect.")
        user.password_hash = await hash_password_async(new_password)
        await self.tokens.revoke_all_for_user(user.id)
        await self.session.commit()

    # How many of the account's own sessions one read is allowed to name. A client that refreshes its
    # pair on every launch for a month would otherwise hand a screen a list nobody can finish, and a
    # list that runs out says so instead of looking complete.
    SESSIONS_SHOWN = 50

    async def own_sessions(
        self, user: User, current_session_id: uuid.UUID | None
    ) -> dict:
        """The devices this account can still be standing on, newest first.

        `current_session_id` is the row the bearer's own access token names, so exactly one row can
        carry `current: true` — and none does when the token was minted before the claim existed.
        Guessing the badge (the newest row, the largest one) would put a lie on the screen that tells
        a person which device to cut off, so the absence is left visible.
        """
        rows = await self.tokens.live_for_owner(user.id, self.SESSIONS_SHOWN + 1)
        shown = rows[: self.SESSIONS_SHOWN]
        return {
            "sessions": [self._session_dto(row, current_session_id) for row in shown],
            "has_more": len(rows) > self.SESSIONS_SHOWN,
        }

    @staticmethod
    def _session_dto(row, current_session_id: uuid.UUID | None) -> dict:
        return {
            "id": str(row.id),
            # What the device called itself in the header it signed in with. Nothing here rewrites
            # it into a friendly name: a browser's string and a phone's string are both what the
            # person has to recognise, and an interpretation of them would be the server's guess.
            "device": row.user_agent,
            "signed_in_at": row.created_at,
            "expires_at": row.expires_at,
            "current": current_session_id is not None and row.id == current_session_id,
        }

    async def end_session(self, user: User, session_id: uuid.UUID) -> None:
        """End the one live session this account owns that carries that id.

        A row that was already ended, one that belongs to somebody else, and one that no row at all
        answers the same refusal: the id space is not a place to learn which sessions existed.
        """
        if not await self.tokens.revoke_one_live_for_owner(session_id, user.id):
            raise NotFoundError("No live session with this id for this account.")
        await self.session.commit()

    async def end_all_sessions(self, user: User) -> None:
        """Every live session of the account, the caller's own among them.

        This is the door for a lost phone, and it is deliberately not a door that leaves the caller
        comfortable: the row the request stands on is revoked with the rest, so the device reading the
        answer is signed out at its next refresh like every other. The answer carries no new token pair
        for the same reason `change-password` carries none.
        """
        await self.tokens.revoke_all_for_user(user.id)
        await self.session.commit()


def _default_birth_date():
    from datetime import date

    return date(2000, 1, 1)
