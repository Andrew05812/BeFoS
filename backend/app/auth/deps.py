from __future__ import annotations

import uuid

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import decode_token
from app.repositories.user_repo import UserRepository

logger = get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
):
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Missing authentication token.")

    try:
        payload = decode_token(credentials.credentials, "access")
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Token has expired.")
    except jwt.PyJWTError:
        raise UnauthorizedError("Invalid authentication token.")

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type.")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError):
        raise UnauthorizedError("Invalid token subject.")

    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise UnauthorizedError("User no longer exists.")
    if not user.is_active or user.is_deleted:
        raise ForbiddenError("Account is disabled.")
    return user


async def require_current_user(user=Depends(get_current_user)):
    return user
