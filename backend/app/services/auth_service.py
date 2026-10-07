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
    hash_password,
    verify_password,
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
            user = User(email=email.lower(), password_hash=hash_password(password), is_active=True)
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
        if user is None or not verify_password(password, user.password_hash):
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

        token_hash = generate_token_hash(refresh_token)
        stored = await self.tokens.get_by_hash(token_hash)
        if stored is None:
            raise UnauthorizedError("Refresh token has been revoked.")

        user = await self.users.get_by_id(uuid.UUID(payload["sub"]))
        if user is None or not user.is_active or user.is_deleted:
            raise UnauthorizedError("User no longer active.")

        # Rotate: redeem the old token and issue a new pair in one transaction. consume() revokes
        # only a token that is still active, so a token that arrives twice at the same instant is
        # turned into a session by exactly one request — the loser finds the row already revoked
        # and is refused, the same answer a serial retry would get. Reading stored.revoked here
        # would not do: both racing requests read it while it is still active.
        if not await self.tokens.consume(token_hash):
            raise UnauthorizedError("Refresh token has been revoked.")
        return await self.issue_tokens(user, user_agent)

    async def logout(self, user_id: uuid.UUID, refresh_token: str | None) -> None:
        if refresh_token:
            stored = await self.tokens.get_by_hash(generate_token_hash(refresh_token))
            if stored and stored.user_id == user_id and not stored.revoked:
                await self.tokens.revoke(stored)
        await self.session.commit()

    async def change_password(self, user: User, old_password: str, new_password: str) -> None:
        if not verify_password(old_password, user.password_hash):
            raise UnauthorizedError("Current password is incorrect.")
        if len(new_password) < 8:
            raise ValidationError("Password must be at least 8 characters.")
        user.password_hash = hash_password(new_password)
        await self.tokens.revoke_all_for_user(user.id)
        await self.session.commit()


def _default_birth_date():
    from datetime import date

    return date(2000, 1, 1)
