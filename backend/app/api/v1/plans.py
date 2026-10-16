from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.database import get_session
from app.models import User
from app.schemas.schemas import (
    MeetingTimeIn,
    PlanDetailResponse,
    PlanEditIn,
    PlanListResponse,
    PlanOut,
    PlanPersonalNoteIn,
)
from app.services.chat_service import message_frame
from app.services.plan_service import PlanService
from app.websocket.manager import manager

router = APIRouter(prefix="/plans", tags=["plans"])
pair_router = APIRouter(prefix="/matches", tags=["plans"])


async def _broadcast(match_id: uuid.UUID, events: list[dict]) -> None:
    """Tell the pair's open chats about the lines this tap wrote, after the write committed.

    The rule the card doors already follow: a broadcast of a row that was rolled back would put an
    arrangement in front of a pair whose database holds none. Each line carries its plan id, which is
    what makes a card in the chat tappable into the arrangement it records.
    """
    for event in events:
        await manager.broadcast_to_match(match_id, message_frame(event))


@router.get("", response_model=PlanListResponse)
async def list_plans(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Every arrangement this person is in, across all their pairs — the screen of «Наши планы».

    Projected from the pair's rows on read rather than served as the plan table last wrote it: an hour
    the other half moved since this screen was opened is shown as the rows say it now, so the list
    cannot offer an agreement nobody holds.
    """
    service = PlanService(session)
    return PlanListResponse(plans=[PlanOut(**p) for p in await service.list_for_viewer(current_user.id)])


@pair_router.get("/{match_id}/plans", response_model=PlanListResponse)
async def list_match_plans(
    match_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """One pair's plans. Somebody outside the pair is answered 404, the refusal every route of this
    family gives — telling an outsider «not yours» would confirm the arrangement is real.
    """
    service = PlanService(session)
    return PlanListResponse(
        plans=[PlanOut(**p) for p in await service.list_for_match(match_id, current_user.id)]
    )


@router.get("/{plan_id}", response_model=PlanDetailResponse)
async def get_plan(
    plan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """The plan, this person's own remark on it, and the history their chat holds about it.

    The history is read out of `messages` rather than from a second journal table, so the plan's detail
    screen and the conversation cannot tell two stories about one tap.
    """
    service = PlanService(session)
    return PlanDetailResponse(**await service.detail(plan_id, current_user.id))


@router.patch("/{plan_id}", response_model=PlanOut)
async def edit_plan(
    plan_id: uuid.UUID,
    payload: PlanEditIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Change the place or the pair's note, or clear one of them; `my_note` is this person's own.

    A field left out of the body is left alone, and clearing is said by its own flag rather than by an
    empty string: a plan whose place was never written and one whose pair erased it read the same on
    screen, but only the second of them had a change to report to the chat.

    The answer is the plan as it now stands, so the detail screen can repaint its own card instead of
    asking for it again.
    """
    service = PlanService(session)
    match_id = await service.match_of(plan_id, current_user.id)
    events = await service.edit(
        plan_id,
        current_user.id,
        place=payload.place,
        note=payload.note,
        my_note=payload.my_note,
        clear_place=payload.clear_place,
        clear_note=payload.clear_note,
    )
    await _broadcast(match_id, events)
    detail = await service.detail(plan_id, current_user.id)
    return PlanOut(**detail["plan"])


@router.post("/{plan_id}/accept", status_code=204)
async def accept_plan(
    plan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Stand behind the idea the plan is about — the same act as tapping «выбрать» on the card.

    One verb serves both doors on purpose: the pair's rows, their chat and the plan's status have to
    read the same answer whichever screen the tap came from.
    """
    service = PlanService(session)
    match_id = await service.match_of(plan_id, current_user.id)
    events = await service.accept_by_id(plan_id, current_user.id)
    await _broadcast(match_id, events)
    return None


@router.post("/{plan_id}/decline", status_code=204)
async def decline_plan(
    plan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Answer the plan with a refusal — the plan screen's word for pushing the card away.

    An idea the pair was told about and then told no is said in their chat once, from either door.
    """
    service = PlanService(session)
    match_id = await service.match_of(plan_id, current_user.id)
    events = await service.decline_by_id(plan_id, current_user.id, True)
    await _broadcast(match_id, events)
    return None


@router.delete("/{plan_id}/decline", status_code=204)
async def restore_decline(
    plan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Take the refusal back, which puts the idea where the pair's page shows it again."""
    service = PlanService(session)
    match_id = await service.match_of(plan_id, current_user.id)
    events = await service.decline_by_id(plan_id, current_user.id, False)
    await _broadcast(match_id, events)
    return None


@router.post("/{plan_id}/hour", status_code=204)
async def offer_hour(
    plan_id: uuid.UUID,
    payload: MeetingTimeIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Name the moment this person would meet, or move the one they named, and wait for the answer.

    The hour stays a projection of the pair's two rows: this route asks those rows to be written, it
    does not keep a third statement of the agreement anywhere.
    """
    service = PlanService(session)
    match_id = await service.match_of(plan_id, current_user.id)
    events = await service.offer_by_id(plan_id, current_user.id, payload.when)
    await _broadcast(match_id, events)
    return None


@router.post("/{plan_id}/hour/confirm", status_code=204)
async def confirm_hour(
    plan_id: uuid.UUID,
    payload: MeetingTimeIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Agree to the moment the other half named. The instant is sent back rather than read off the row
    here, because the value the person saw is the value they answered; if it moved since, this answers
    409 instead of agreeing to something nobody offered.
    """
    service = PlanService(session)
    match_id = await service.match_of(plan_id, current_user.id)
    events = await service.confirm_by_id(plan_id, current_user.id, payload.when)
    await _broadcast(match_id, events)
    return None


@router.post("/{plan_id}/cancel", status_code=204)
async def cancel_plan(
    plan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Call the plan off. Either half may, and a second tap says it once rather than twice.

    After this the hour doors answer 409: a called-off arrangement that gained a new hour would leave
    the pair's list saying «отменённые» while their chat says «вы договорились».
    """
    service = PlanService(session)
    match_id = await service.match_of(plan_id, current_user.id)
    events = await service.cancel(plan_id, current_user.id)
    await _broadcast(match_id, events)
    return None


@router.delete("/{plan_id}/cancel", status_code=204)
async def restore_plan(
    plan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Take a cancellation back — by the half that called it off, and by nobody else."""
    service = PlanService(session)
    match_id = await service.match_of(plan_id, current_user.id)
    events = await service.restore(plan_id, current_user.id)
    await _broadcast(match_id, events)
    return None


@router.post("/{plan_id}/complete", status_code=204)
async def complete_plan(
    plan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """This person's own word that the meeting happened.

    Nothing here is inferred from the clock: an hour passing is not evidence about the physical world,
    and the plan reads «состоялось» only once both halves have said so — which is why a single tap can
    answer 204 and still leave the plan planned.
    """
    service = PlanService(session)
    match_id = await service.match_of(plan_id, current_user.id)
    events = await service.set_attended(plan_id, current_user.id, True)
    await _broadcast(match_id, events)
    return None


@router.delete("/{plan_id}/complete", status_code=204)
async def undo_complete_plan(
    plan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Withdraw this person's word that the meeting happened, which takes the plan out of
    «завершённые» without claiming the hour itself went anywhere.
    """
    service = PlanService(session)
    match_id = await service.match_of(plan_id, current_user.id)
    events = await service.set_attended(plan_id, current_user.id, False)
    await _broadcast(match_id, events)
    return None


@router.put("/{plan_id}/note", status_code=204)
async def set_personal_note(
    plan_id: uuid.UUID,
    payload: PlanPersonalNoteIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """This person's own remark about their own plan, read back only to them.

    It lives on their member row, so the pair's shared card cannot carry it and nothing goes into the
    chat: a note about one's own plan is not a statement about the other half.
    """
    service = PlanService(session)
    await service.set_personal_note(plan_id, current_user.id, payload.note)
    return None
