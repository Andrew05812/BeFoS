from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.database import get_session
from app.core.rate_limit import auth_rate_limit_dependency
from app.models import User
from app.schemas.schemas import (
    DiscoveryResponse,
    LikedMeResponse,
    LikedUsersResponse,
    LikeResponse,
    PassedUsersResponse,
    PassResponse,
    WaitlistJoinRequest,
    WaitlistStatusOut,
)
from app.services.discovery_service import (
    LIKED_ME_SHOWN,
    LIKED_SHOWN,
    PASSED_SHOWN,
    DiscoveryService,
)
from app.services.match_service import MatchService
from app.services.waitlist_service import WaitlistService

router = APIRouter(tags=["discovery"])


@router.get("/discover", response_model=DiscoveryResponse)
async def discover(
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """One page of the viewer's deck, and the cursor for the next one.

    No offset: the deck is ranked once and paging moves by rank, so liking or passing
    between requests cannot shift a card into or out of the page being asked for.
    """
    service = DiscoveryService(session)
    data = await service.feed(
        current_user.id, limit=limit, cursor=cursor, viewer_is_verified=current_user.is_verified
    )
    return DiscoveryResponse(**data)


@router.get("/discover/liked-me", response_model=LikedMeResponse)
async def liked_me(
    limit: int = Query(default=LIKED_ME_SHOWN, ge=1, le=LIKED_ME_SHOWN),
    cursor: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Who tapped the account, newest tap first, one page of them and the link to the next.

    The tap is written by the route below and, until this one existed, could be read back only as
    a yes-or-no about one named stranger. This answers the account's own question — «кто меня
    выбрал» — and says with it whether more taps stand behind the page.

    Stage 126 put the boundary here. The door used to answer fifty taps and stop, and `has_more`
    named a rest no request could reach; the key is the pair `(created_at, id)` the read is ordered
    by, and it is sealed by the server, so a resumed page continues the reader's own walk rather than
    repeating somebody's claim about where it stood.
    """
    service = DiscoveryService(session)
    data = await service.liked_me(current_user.id, cursor=cursor, limit=limit)
    return LikedMeResponse(**data)


@router.get("/discover/liked", response_model=LikedUsersResponse)
async def liked_users(
    limit: int = Query(default=LIKED_SHOWN, ge=1, le=LIKED_SHOWN),
    cursor: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Whom the account tapped, newest tap first, one page of them and the link to the next.

    The mirror of the inbox: stage 112 opened the door that reads the taps pointing at the account,
    and this one reads the taps the account's own card wrote outward. Each card carries the number
    that card was shown when it tapped, not a fresh guess about whether the two still fit.

    Paging is a keyset over `(created_at, id)` rather than an offset, for the two reasons the deck and
    the pair's history each learned: an offset moves under a withdrawal, so the page a reader asked for
    second is not the page that follows the one they were shown, and a boundary drawn through the
    timestamp alone cuts between taps made in the same microsecond. The cursor is opaque and carries no
    account — the token still decides whose taps these are.
    """
    service = DiscoveryService(session)
    data = await service.liked(current_user.id, cursor=cursor, limit=limit)
    return LikedUsersResponse(**data)


@router.get("/discover/passed", response_model=PassedUsersResponse)
async def passed_users(
    limit: int = Query(default=PASSED_SHOWN, ge=1, le=PASSED_SHOWN),
    cursor: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Whom the account dismissed, newest answer first, one page of them and the link to the next.

    The deck answers «show me people I have not decided about», so a pass could only be read back as
    an absence — and the row that stores it had no door of its own. This is that door, and the row
    beside it says when the card was swiped past.

    The page boundary arrived with stage 126, for the reason it arrived at the inbox: the answer could
    already say more dismissals stood behind the fifty it named, and the person reading it held no way
    to ask — while the same screen offers a verb that takes any one of those answers back.
    """
    service = DiscoveryService(session)
    data = await service.passed(current_user.id, cursor=cursor, limit=limit)
    return PassedUsersResponse(**data)


@router.get("/discover/waitlist", response_model=WaitlistStatusOut)
async def read_waitlist(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """The account's own waiting mark — the one row this door can read, and it is the reader's."""
    return WaitlistStatusOut(**await WaitlistService(session).status(current_user))


@router.post("/discover/waitlist", response_model=WaitlistStatusOut)
async def join_waitlist(
    payload: WaitlistJoinRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Leave a mark: «скажите мне, когда рядом появятся люди».

    The city is optional and defaults to the one in the profile; no coordinates are accepted or
    stored. The mark is a request the account can read back and withdraw, not a subscription — and
    it is not a promise of a letter, because no product-notice channel exists in this build. When one
    does, `waitlist_entries.notified_at` is the field it will write (see `docs/OPERATIONS.md`).
    """
    return WaitlistStatusOut(**await WaitlistService(session).join(current_user, payload.city))


@router.delete("/discover/waitlist", status_code=204)
async def leave_waitlist(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Withdraw the mark. Idempotent, like every «take my answer back» door here."""
    await WaitlistService(session).leave(current_user)
    return None


@router.post("/users/{user_id}/like", response_model=LikeResponse)
async def like_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = MatchService(session)
    result = await service.like(current_user.id, user_id)
    return LikeResponse(**result)


@router.delete("/users/{user_id}/like", response_model=LikedUsersResponse)
async def undo_like(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Take one's own tap back, and answer with the list that is left.

    Only the requester's half of the pair is cleared: a tap says nothing about the tap the other
    person may have made, and it leaves a formed pair standing — un-pairing is the match list's own
    door, not something a "withdraw my tap" button should silently do to a conversation.

    The page that comes back is the newest one and carries its own link forward, so a screen that
    withdrew a row from page one is not left holding a list it can no longer turn through.
    """
    service = DiscoveryService(session)
    data = await service.undo_like(current_user.id, user_id)
    return LikedUsersResponse(**data)


@router.post("/users/{user_id}/pass", response_model=PassResponse)
async def pass_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = MatchService(session)
    result = await service.pass_user(current_user.id, user_id)
    return PassResponse(**result)


@router.delete("/users/{user_id}/pass", response_model=PassedUsersResponse)
async def undo_pass(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Take one's own pass back, and answer with the list that is left.

    A swipe past a card is an answer about the deck, not a seal on the pair: this clears both records
    the answer left — the row the deck's rule reads, and the row that remembers the card was already
    shown — so the person comes back through the same door that hid them, at the end of the deck
    rather than in front of cards still waiting.
    """
    service = DiscoveryService(session)
    data = await service.unpass(current_user.id, user_id)
    return PassedUsersResponse(**data)
