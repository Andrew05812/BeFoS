from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_session_id, get_current_user
from app.core.consent import CONSENT_VERSION, consent_document
from app.core.database import get_session
from app.core.exceptions import ValidationError
from app.core.rate_limit import auth_rate_limit_dependency
from app.core.security import decode_token
from app.models import User
from app.schemas.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    ConsentAccept,
    ConsentOut,
    EmailConfirmationRequest,
    LoginRequest,
    PasswordResetAccepted,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    SessionCard,
    SessionsPage,
    TokenPair,
    UserBrief,
)
from app.services.auth_service import AuthService
from app.services.recovery_service import RecoveryService
from app.services.verification_service import VerificationService

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(auth_rate_limit_dependency)])


def _user_brief(user) -> UserBrief:
    return UserBrief(
        id=str(user.id),
        email=user.email,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
    )


@router.get("/consent", response_model=ConsentOut)
async def read_consent():
    """The text registration asks a person to accept, as the server holds it today.

    Public on purpose: the document has to be readable before there is an account to read it with,
    and it carries no fact about anybody. A client that caches it is welcome to, as long as it sends
    back the version it showed — that is what the register door checks.
    """
    return ConsentOut(**consent_document())


@router.post("/consent", status_code=204)
async def accept_consent(
    payload: ConsentAccept,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Record that the account has read the current text, and when.

    The door exists for a text that changes after somebody registered: the client reads the version
    on `/users/me`, sees it is not the current one, shows the document and comes back here. A stale
    version is refused rather than recorded — «accepted» has to mean the words that are published
    now, not the words the build remembers.
    """
    if payload.consent_version != CONSENT_VERSION:
        raise ValidationError(
            "The consent text has changed. Reload it, read it, and accept it again."
        )
    current_user.consent_version = CONSENT_VERSION
    current_user.consent_accepted_at = datetime.now(timezone.utc)
    await session.commit()
    return None


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(payload: RegisterRequest, request: Request, session: AsyncSession = Depends(get_session)):
    service = AuthService(session)
    user = await service.register(
        payload.email, payload.password, payload.password_confirm, payload.consent_version
    )
    tokens = await service.issue_tokens(user, request.headers.get("user-agent"))
    return AuthResponse(user=_user_brief(user), tokens=TokenPair(**tokens))


@router.post("/email-confirmation/confirm", status_code=204)
async def confirm_email(payload: EmailConfirmationRequest, session: AsyncSession = Depends(get_session)):
    """Spend the code from the confirmation letter. Empty, like the reset door, and for a reason.

    The answer is a fact about a mailbox, not about a session: the code is the whole proof, and the
    caller may be standing on another device than the one that registered. A refusal names nothing —
    unknown, spent, expired and erased all read as the same sentence — because this door must not help
    a stranger learn which addresses hold accounts either.
    """
    await VerificationService(session).confirm(payload.code)
    return None


@router.post("/email-confirmation/resend", status_code=204)
async def resend_confirmation(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Ask for another letter, for the account the bearer names and for no other.

    No address in the body: the session already says whose mailbox is being written to, so this door
    cannot be turned into a mail relay by a stranger. An account that is already confirmed, or one
    whose letter still works, gets the same empty answer and no second letter.
    """
    await VerificationService(session).send_letter(current_user)
    return None


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


@router.post("/change-password", status_code=204)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Replace the account's word with one the caller says twice, and drop every session it opens.

    No body names an account: the only one this can reach is the bearer's own. The answer is empty on
    purpose — the token pair the caller is standing on is among the ones revoked, so a fresh pair
    would be a promise the server has just broken.
    """
    service = AuthService(session)
    await service.change_password(
        current_user, payload.old_password, payload.new_password, payload.password_confirm
    )
    return None


@router.get("/sessions", response_model=SessionsPage)
async def read_sessions(
    current_user: User = Depends(get_current_user),
    current_session_id: uuid.UUID | None = Depends(get_current_session_id),
    session: AsyncSession = Depends(get_session),
):
    """The devices this account can still open a token pair on, the newest one first.

    Three of the app's routes already write a row here — registration, sign-in and refresh each hand
    their `user-agent` to `issue_tokens` — and none of them ever gave the row back: the account could
    learn that it holds a session it does not recognise only by changing its word, which ends every
    session at once, including the one it is reading the answer with. Nothing in the body names an
    account, and no other account's row can reach this list whatever its id.
    """
    service = AuthService(session)
    data = await service.own_sessions(current_user, current_session_id)
    return SessionsPage(
        sessions=[SessionCard(**card) for card in data["sessions"]],
        has_more=data["has_more"],
    )


@router.post("/sessions/revoke-all", status_code=204)
async def revoke_all_sessions(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """End every session the account holds, the caller's own among them, and keep no door.

    The answer is empty for the same reason `change-password`'s is: the row this request stands on is
    among the ones ended, so handing back a fresh pair would be the server un-revoking its own write.
    The access token in hand stays usable until it expires on its own — the product revokes sessions,
    not tokens it has already signed — and `docs/API.md` says which of the two this route ends.
    """
    service = AuthService(session)
    await service.end_all_sessions(current_user)
    return None


@router.post("/sessions/{session_id}/revoke", status_code=204)
async def revoke_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """End the one live session of this account that carries that id; nothing else moves.

    An id that is foreign, already ended, or past its expiry answers the same refusal as an id that
    was never written: this route is not a place to find out which sessions existed.
    """
    service = AuthService(session)
    await service.end_session(current_user, session_id)
    return None


@router.post("/password-reset/request", status_code=202, response_model=PasswordResetAccepted)
async def request_password_reset(
    payload: PasswordResetRequest, session: AsyncSession = Depends(get_session)
):
    """Open the door that does not need the word: the word is exactly what the caller has lost.

    Answers the same 202 with the same body whether or not the address holds an account, for the
    reason stage 52 gave for sign-in (`auth_service.py:69-84`): a recovery door that distinguishes
    the two is a subscription list for whoever asks. Nothing in this body names a person.
    """
    service = RecoveryService(session)
    window = await service.request_reset(payload.email)
    return PasswordResetAccepted(accepted=True, expires_in_seconds=window)


@router.post("/password-reset/confirm", status_code=204)
async def confirm_password_reset(
    payload: PasswordResetConfirm, session: AsyncSession = Depends(get_session)
):
    """Trade a code read off a letter for a word the caller chooses, and end every older session.

    Empty on purpose, like `change-password`: the sessions this write ends include any the caller
    might still be standing on, and a token pair handed back here would be the server un-revoking
    its own write. The three refusals — no such code, already used, too late — are one answer, so
    the door cannot be probed to learn which of them happened.
    """
    service = RecoveryService(session)
    await service.complete_reset(payload.code, payload.new_password, payload.password_confirm)
    return None
