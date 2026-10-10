from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, UnauthorizedError, ValidationError
from app.core.logging import get_logger
from app.core.security import (
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
        # Constant-ish behaviour: do not reveal whether the email exists.
        if user is None or not await verify_password_async(password, user.password_hash):
            raise UnauthorizedError("Invalid email or password.")
        if user.is_deleted:
            raise UnauthorizedError("Account is deactivated.")
        if not user.is_active:
            raise UnauthorizedError("Account is disabled.")
        return user

    async def issue_tokens(self, user: User, user_agent: str | None = None) -> dict:
        access, _ = create_token(user.id, "access")
        refresh, expires = create_token(user.id, "refresh")
        await self.tokens.add(user.id, generate_token_hash(refresh), expires, user_agent)
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

    async def change_password(self, user: User, old_password: str, new_password: str) -> None:
        if not await verify_password_async(old_password, user.password_hash):
            raise UnauthorizedError("Current password is incorrect.")
        if len(new_password) < 8:
            raise ValidationError("Password must be at least 8 characters.")
        user.password_hash = await hash_password_async(new_password)
        await self.tokens.revoke_all_for_user(user.id)
        await self.session.commit()


def _default_birth_date():
    from datetime import date

    return date(2000, 1, 1)
