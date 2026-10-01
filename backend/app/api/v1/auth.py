from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.rate_limit import auth_rate_limit_dependency
from app.core.security import decode_token
from app.schemas.schemas import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserBrief,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(auth_rate_limit_dependency)])


def _user_brief(user) -> UserBrief:
    return UserBrief(id=str(user.id), email=user.email, is_active=user.is_active, created_at=user.created_at)


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(payload: RegisterRequest, request: Request, session: AsyncSession = Depends(get_session)):
    service = AuthService(session)
    user = await service.register(payload.email, payload.password, payload.password_confirm)
    tokens = await service.issue_tokens(user, request.headers.get("user-agent"))
    return AuthResponse(user=_user_brief(user), tokens=TokenPair(**tokens))


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, request: Request, session: AsyncSession = Depends(get_session)):
    service = AuthService(session)
    user = await service.authenticate(payload.email, payload.password)
    tokens = await service.issue_tokens(user, request.headers.get("user-agent"))
    return AuthResponse(user=_user_brief(user), tokens=TokenPair(**tokens))


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, request: Request, session: AsyncSession = Depends(get_session)):
    service = AuthService(session)
    tokens = await service.refresh(payload.refresh_token, request.headers.get("user-agent"))
    return TokenPair(**tokens)


@router.post("/logout", status_code=204)
async def logout(payload: RefreshRequest, session: AsyncSession = Depends(get_session)):
    """Revoke a refresh token. Idempotent: invalid tokens succeed silently."""
    service = AuthService(session)
    try:
        data = decode_token(payload.refresh_token, "refresh")
        user_id = uuid.UUID(data["sub"])
        await service.logout(user_id, payload.refresh_token)
    except Exception:
        pass
    return None
