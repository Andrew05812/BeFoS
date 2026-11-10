"""The personal door: preview it, mint it, read what became of it, take it back.

Four verbs and one rule — none of them names the invited person. `POST /invites/preview` is the only
anonymous one: the holder of a link is asking whether it opens, which they must be able to ask
without an account, and the answer is a bool plus the moment the link closes. It never carries the
inviter's name, id or address, because a link forwarded through a chat is not a profile handed out.

The three signed doors all read the inviter from the bearer. An id in a path names an invitation
that belongs to the caller, and `revoke` answers the same `404` for a stranger's row and a row
that does not exist — the id space is not a place to learn which invitations are live.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.database import get_session
from app.core.rate_limit import auth_rate_limit_dependency
from app.models import User
from app.schemas.schemas import (
    InviteListOut,
    InviteOut,
    InvitePreview,
    InvitePreviewRequest,
)
from app.services.referral_service import ReferralService

router = APIRouter(
    tags=["referrals"], dependencies=[Depends(auth_rate_limit_dependency)]
)


@router.post("/invites/preview", response_model=InvitePreview)
async def preview_invite(
    payload: InvitePreviewRequest,
    session: AsyncSession = Depends(get_session),
):
    """Does this code open a door, and until when. Whose door it is stays outside the answer.

    Mounted on the same `/auth` window as registration and recovery on purpose: the code is a
    bearer secret and this is the one route where a stranger may present guesses. The window
    bounds guesses to twenty a minute per address — a search of a 144-bit code at that speed is
    not a threat, and the preview is also the one place an expired link is told apart from a
    revoked one without either answer naming a person.
    """
    return InvitePreview(**await ReferralService(session).preview(payload.code))


@router.post("/referrals", response_model=InviteOut)
async def create_invite(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """This account's live link, or a new one when none is live.

    Idempotent: a second tap on «Пригласить друга» answers with the door that is already open rather
    than minting another, so a link that was copied and shared keeps working. A new door is
    minted only after the old one is accepted, revoked or past its month — and at most twenty a
    day, which is the shape of consequence the endpoint has.
    """
    return InviteOut(**await ReferralService(session).create_or_get(current_user))


@router.get("/referrals", response_model=InviteListOut)
async def list_invites(
    response: Response,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """The account's own doors, newest first, and how many of them somebody walked through.

    No invited account appears here: `accepted_total` is a count of this account's own rows, the
    same fact the list carries, and the row stops at the moment it was spent. The answer carries
    live bearer codes, so no cache between the server and the screen may keep it.
    """
    response.headers["Cache-Control"] = "no-store"
    return InviteListOut(**await ReferralService(session).list_for(current_user))


@router.delete("/referrals/{invitation_id}", status_code=204)
async def revoke_invite(
    invitation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Close one of this account's own live doors. A spent door is not withdrawable: the account
    behind it exists, and un-spending the link would not erase that fact.
    """
    await ReferralService(session).revoke(current_user, invitation_id)
    return None
