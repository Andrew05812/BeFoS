"""The deck that runs out has to say which of seven worlds the reader is standing in.

«Анкеты закончились» was one sentence for everything: a product with nobody in it yet, a city with
nobody in it, a filter that excluded the street the person lives on, a deck they had already walked,
an address they never confirmed, and a page that simply failed. Stage 132 gives the empty answer a
reason and a next step, under two rules this file holds:

* the reason is the server's, computed from rows it already owns — the client never guesses it from
  a count of cards it happened to receive;
* the reason never becomes a directory. It is a bucket (`none / few / some / many`) or a boolean,
  never a number sharp enough to watch one person arrive, never an id, name or address of anybody
  else — the one exact number in the payload is `accepted_total`, and it counts the reader's own
  invitations.

It also pins the personal door itself: a link is minted by a signed account, opens exactly one new
account, survives a double tap without minting a second, can be revoked by its owner and nobody
else, and an expired, spent or foreign code is refused without turning registration into a way to
ask which codes exist.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy import func, select, update

from app.core.consent import CONSENT_VERSION
from app.models import Invitation, WaitlistEntry

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

DISCOVER = "/api/v1/discover"
WAITLIST = "/api/v1/discover/waitlist"
REFERRALS = "/api/v1/referrals"
REGISTER = "/api/v1/auth/register"
PASSWORD = "Test12345"


async def _ready(
    client: AsyncClient, email: str, *, verify: bool = True, city: str = "Москва"
) -> dict:
    """An account the deck could show: address confirmed, onboarding done, questionnaire answered."""
    account = await register_and_auth(client, email, verify=verify)
    await complete_onboarding(client, account["token"], name=email.split("@")[0][:12], city=city)
    await answer_all_questions(client, account["token"])
    return account


async def _patch_me(client: AsyncClient, token: str, **fields) -> None:
    response = await client.patch("/api/v1/users/me", json=fields, headers=auth_headers(token))
    assert response.status_code == 200, response.text


async def _feed(client: AsyncClient, token: str) -> dict:
    response = await client.get(DISCOVER, params={"limit": 50}, headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()


def _empty_of(page: dict) -> dict:
    assert page["items"] == [], page
    assert page["empty"] is not None, (
        "an empty page without a reason is the dead end this stage removes"
    )
    return page["empty"]


# ------------------------------------------------------------------ the seven reasons


async def test_a_product_with_nobody_else_says_so_and_offers_a_link(
    client: AsyncClient, caplog
):
    viewer = await _ready(client, "why_empty_nobody@befos.app")

    # The first empty page is the visit the journal counts: reason and buckets, never the address
    # that made the request, the city it was narrowed to, or the invitation code that brought it.
    with caplog.at_level(logging.INFO, logger="analytics"):
        empty = _empty_of(await _feed(client, viewer["token"]))
    assert empty["reason"] == "no_one_yet", empty
    assert empty["audience"] == "none" and empty["nearby"] == "none", empty
    assert empty["someone_preparing_here"] is False
    assert empty["can_widen_filters"] is False
    assert empty["waitlist_joined"] is False
    assert "discovery_empty" in caplog.text
    assert "no_one_yet" in caplog.text
    assert viewer["email"] not in caplog.text, "the address reached the analytics journal"


async def test_an_unconfirmed_address_is_named_before_any_audience(client: AsyncClient):
    # A viewer whose own letter was never answered can still read other cards; the gate withholds
    # them from everybody else's deck, not from their own. The diagnosis names whose row is
    # unfinished without counting a single other person.
    viewer = await register_and_auth(client, "why_empty_unverified@befos.app", verify=False)
    await complete_onboarding(client, viewer["token"], name="НеОтветила")
    await answer_all_questions(client, viewer["token"])

    empty = _empty_of(await _feed(client, viewer["token"]))
    assert empty["reason"] == "email_unconfirmed"
    assert empty["audience"] == "none" and empty["nearby"] == "none"
    assert empty["can_widen_filters"] is False


async def test_a_shell_that_never_finished_the_questionnaire_is_named_as_such(
    client: AsyncClient,
):
    viewer = await register_and_auth(client, "why_empty_shell@befos.app")

    empty = _empty_of(await _feed(client, viewer["token"]))
    assert empty["reason"] == "onboarding_incomplete"
    assert empty["audience"] == "none"


async def test_people_behind_the_letter_are_preparing_not_absent(client: AsyncClient):
    viewer = await _ready(client, "why_empty_waiting@befos.app")
    # Registered, onboarded into the same city, questionnaire answered — and the address unconfirmed,
    # which is exactly the state the deck hides from the viewer.
    preparer = await _ready(client, "why_empty_preparing@befos.app", verify=False)

    empty = _empty_of(await _feed(client, viewer["token"]))
    assert empty["reason"] == "audience_preparing", empty
    assert empty["someone_preparing_here"] is True
    assert empty["audience"] == "none" and empty["nearby"] == "none"
    assert empty["can_widen_filters"] is False

    # A person the viewer blocked is not part of "рядом": the bucket and the boolean are computed
    # under the same block filter the deck uses, so the explanation cannot confirm that an account
    # the viewer chose not to see is still there.
    blocked = await client.post(
        f"/api/v1/users/{preparer['user_id']}/block", headers=auth_headers(viewer["token"])
    )
    assert blocked.status_code == 200, blocked.text
    after = _empty_of(await _feed(client, viewer["token"]))
    assert after["reason"] == "no_one_yet", after
    assert after["someone_preparing_here"] is False
    assert after["audience"] == "none" and after["nearby"] == "none"


async def test_a_person_outside_the_age_band_is_named_as_filters_not_as_emptiness(
    client: AsyncClient,
):
    viewer = await _ready(client, "why_empty_filters_v@befos.app")
    await _patch_me(client, viewer["token"], age_min=18, age_max=25)
    # In the same city, showable, outside the age band the viewer just narrowed.
    await _ready(client, "why_empty_filters_c@befos.app")

    empty = _empty_of(await _feed(client, viewer["token"]))
    assert empty["reason"] == "filters_too_narrow", empty
    assert empty["audience"] == "few", empty
    assert empty["nearby"] == "few", empty
    assert empty["can_widen_filters"] is True


async def test_a_search_city_without_people_names_the_city_and_not_the_filters(
    client: AsyncClient,
):
    viewer = await _ready(client, "why_empty_city_v@befos.app")
    await _patch_me(client, viewer["token"], city_preference="Краснодар")
    await _ready(client, "why_empty_city_c@befos.app")

    empty = _empty_of(await _feed(client, viewer["token"]))
    assert empty["reason"] == "city_filter_empty", empty
    assert empty["can_widen_filters"] is True
    assert empty["nearby"] == "few", "the viewer's own city holds a person the filter hides"


async def test_after_the_reader_answered_everybody_the_reason_is_exhausted(client: AsyncClient):
    viewer = await _ready(client, "why_empty_seen_v@befos.app")
    other = await _ready(client, "why_empty_seen_c@befos.app")

    first = await _feed(client, viewer["token"])
    assert [card["user_id"] for card in first["items"]] == [other["user_id"]], first
    liked = await client.post(
        f"/api/v1/users/{other['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    assert liked.status_code == 200, liked.text

    empty = _empty_of(await _feed(client, viewer["token"]))
    assert empty["reason"] == "exhausted", empty
    assert empty["can_widen_filters"] is False, (
        "there is nobody left behind a wider filter either"
    )


async def test_the_buckets_widen_but_never_give_an_exact_population(client: AsyncClient):
    viewer = await _ready(client, "why_empty_bucket_v@befos.app")
    await _patch_me(client, viewer["token"], gender_preference=["female"])
    for index in range(3):
        await _ready(client, f"why_empty_bucket_c{index}@befos.app")

    empty = _empty_of(await _feed(client, viewer["token"]))
    assert empty["reason"] == "filters_too_narrow", empty
    assert empty["nearby"] == "few", "three is the few bucket, never the number three"
    assert set(empty) == {
        "reason",
        "audience",
        "nearby",
        "someone_preparing_here",
        "can_widen_filters",
        "waitlist_joined",
        "waitlist_city",
    }


# ------------------------------------------------------------------ the waiting mark


async def test_a_waiting_mark_is_one_row_the_person_can_read_and_withdraw(
    client: AsyncClient, session
):
    viewer = await _ready(client, "why_waitlist@befos.app")

    joined = await client.post(
        WAITLIST, json={"city": "Казань"}, headers=auth_headers(viewer["token"])
    )
    assert joined.status_code == 200, joined.text
    assert joined.json() == {"joined": True, "city": "Казань"}

    read = await client.get(WAITLIST, headers=auth_headers(viewer["token"]))
    assert read.json() == {"joined": True, "city": "Казань"}
    in_feed = _empty_of(await _feed(client, viewer["token"]))
    assert in_feed["waitlist_joined"] is True and in_feed["waitlist_city"] == "Казань"

    again = await client.post(
        WAITLIST, json={"city": "Москва"}, headers=auth_headers(viewer["token"])
    )
    assert again.json() == {"joined": True, "city": "Москва"}
    rows = (
        await session.execute(
            select(WaitlistEntry).where(
                WaitlistEntry.user_id == uuid.UUID(viewer["user_id"])
            )
        )
    ).scalars().all()
    assert len(rows) == 1 and rows[0].city == "Москва"

    left = await client.delete(WAITLIST, headers=auth_headers(viewer["token"]))
    assert left.status_code == 204, left.text
    assert (await client.get(WAITLIST, headers=auth_headers(viewer["token"]))).json() == {
        "joined": False,
        "city": None,
    }
    second = await client.delete(WAITLIST, headers=auth_headers(viewer["token"]))
    assert second.status_code == 204, "withdrawing the mark is idempotent"


async def test_a_waiting_mark_without_a_city_takes_the_one_from_the_profile(client: AsyncClient):
    viewer = await _ready(client, "why_waitlist_profile@befos.app", city="Самара")
    joined = await client.post(WAITLIST, json={}, headers=auth_headers(viewer["token"]))
    assert joined.json()["city"] == "Самара"


# ------------------------------------------------------------------ the personal door


async def test_a_link_is_one_door_a_second_tap_returns_the_same_one(
    client: AsyncClient, session
):
    inviter = await _ready(client, "why_inviter@befos.app")

    first = await client.post(REFERRALS, headers=auth_headers(inviter["token"]))
    second = await client.post(REFERRALS, headers=auth_headers(inviter["token"]))
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    assert first.json()["status"] == "active"
    assert first.json()["url"].startswith("befos://invite/")
    assert first.json()["url"].endswith(first.json()["code"])

    rows = (
        await session.execute(
            select(Invitation).where(
                Invitation.inviter_id == uuid.UUID(inviter["user_id"])
            )
        )
    ).scalars().all()
    assert len(rows) == 1, "a second tap minted a second door"


async def test_the_code_is_random_and_carries_no_identity(client: AsyncClient):
    inviter = await _ready(client, "why_inviter_code@befos.app")
    code = (
        await client.post(REFERRALS, headers=auth_headers(inviter["token"]))
    ).json()["code"]

    assert len(code) >= 20
    assert str(inviter["user_id"]) not in code
    assert inviter["user_id"].replace("-", "") not in code
    assert "@" not in code
    other = await _ready(client, "why_inviter_code2@befos.app")
    other_code = (
        await client.post(REFERRALS, headers=auth_headers(other["token"]))
    ).json()["code"]
    assert other_code != code


async def test_a_preview_says_whether_the_door_opens_and_nothing_about_who(
    client: AsyncClient,
):
    inviter = await _ready(client, "why_preview@befos.app")
    invite = (
        await client.post(REFERRALS, headers=auth_headers(inviter["token"]))
    ).json()

    preview = await client.post(
        "/api/v1/invites/preview", json={"code": invite["code"]}
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["valid"] is True
    assert set(body) == {"valid", "expires_at"}
    rendered = str(body)
    assert inviter["email"] not in rendered and inviter["user_id"] not in rendered

    unknown = await client.post(
        "/api/v1/invites/preview", json={"code": "does-not-exist"}
    )
    assert unknown.status_code == 200 and unknown.json()["valid"] is False


async def test_one_letter_one_account_the_code_is_spent_once(client: AsyncClient, session):
    inviter = await _ready(client, "why_accept_a@befos.app")
    invite = (
        await client.post(REFERRALS, headers=auth_headers(inviter["token"]))
    ).json()

    guest = await client.post(
        REGISTER,
        json={
            "email": "why_accept_b@befos.app",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "consent_version": CONSENT_VERSION,
            "invite_code": invite["code"],
        },
    )
    assert guest.status_code == 201, guest.text
    assert guest.json()["invite_applied"] is True

    preview_after = (await client.post(
        "/api/v1/invites/preview", json={"code": invite["code"]}
    )).json()
    assert preview_after["valid"] is False, "a spent code still opened"

    second = await client.post(
        REGISTER,
        json={
            "email": "why_accept_c@befos.app",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "consent_version": CONSENT_VERSION,
            "invite_code": invite["code"],
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["invite_applied"] is False

    listed_response = await client.get(
        REFERRALS, headers=auth_headers(inviter["token"])
    )
    assert listed_response.headers.get("cache-control") == "no-store", (
        "a live bearer code was left cacheable"
    )
    listed = listed_response.json()
    assert listed["accepted_total"] == 1
    statuses = {row["status"] for row in listed["invites"]}
    assert "accepted" in statuses
    assert guest.json()["user"]["id"] not in str(listed)

    accepted_by = (
        await session.execute(
            select(Invitation.accepted_by_user_id, Invitation.accepted_at).where(
                Invitation.code == invite["code"]
            )
        )
    ).one()
    assert accepted_by.accepted_at is not None
    assert str(accepted_by.accepted_by_user_id) == guest.json()["user"]["id"]


async def test_a_revoked_link_stops_opening_and_a_new_one_can_be_minted(
    client: AsyncClient,
):
    inviter = await _ready(client, "why_revoke@befos.app")
    invite = (
        await client.post(REFERRALS, headers=auth_headers(inviter["token"]))
    ).json()

    revoked = await client.delete(
        f"{REFERRALS}/{invite['id']}", headers=auth_headers(inviter["token"])
    )
    assert revoked.status_code == 204, revoked.text
    assert (await client.post(
        "/api/v1/invites/preview", json={"code": invite["code"]}
    )).json()["valid"] is False

    guest = await client.post(
        REGISTER,
        json={
            "email": "why_revoke_guest@befos.app",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "consent_version": CONSENT_VERSION,
            "invite_code": invite["code"],
        },
    )
    assert guest.status_code == 201
    assert guest.json()["invite_applied"] is False

    fresh = (
        await client.post(REFERRALS, headers=auth_headers(inviter["token"]))
    ).json()
    assert fresh["id"] != invite["id"] and fresh["status"] == "active"

    listed = (
        await client.get(REFERRALS, headers=auth_headers(inviter["token"]))
    ).json()
    assert {row["status"] for row in listed["invites"]} == {"revoked", "active"}


async def test_an_expired_link_is_not_a_door(client: AsyncClient, session):
    inviter = await _ready(client, "why_expired@befos.app")
    invite = (
        await client.post(REFERRALS, headers=auth_headers(inviter["token"]))
    ).json()
    await session.execute(
        update(Invitation)
        .where(Invitation.code == invite["code"])
        .values(expires_at=datetime.now(timezone.utc) - timedelta(days=1))
    )
    await session.commit()

    assert (await client.post(
        "/api/v1/invites/preview", json={"code": invite["code"]}
    )).json()["valid"] is False
    guest = await client.post(
        REGISTER,
        json={
            "email": "why_expired_guest@befos.app",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "consent_version": CONSENT_VERSION,
            "invite_code": invite["code"],
        },
    )
    assert guest.status_code == 201 and guest.json()["invite_applied"] is False
    listed = (
        await client.get(REFERRALS, headers=auth_headers(inviter["token"]))
    ).json()
    assert listed["invites"][0]["status"] == "expired"


async def test_a_stranger_cannot_revoke_somebody_elses_link(client: AsyncClient):
    owner = await _ready(client, "why_owner@befos.app")
    stranger = await _ready(client, "why_stranger@befos.app")
    invite = (await client.post(REFERRALS, headers=auth_headers(owner["token"]))).json()

    foreign = await client.delete(
        f"{REFERRALS}/{invite['id']}", headers=auth_headers(stranger["token"])
    )
    assert foreign.status_code == 404, foreign.text
    unknown = await client.delete(
        f"{REFERRALS}/{uuid.uuid4()}", headers=auth_headers(owner["token"])
    )
    assert unknown.status_code == 404, unknown.text
    assert (await client.post(
        "/api/v1/invites/preview", json={"code": invite["code"]}
    )).json()["valid"] is True

    strangers = (
        await client.get(REFERRALS, headers=auth_headers(stranger["token"]))
    ).json()
    assert strangers == {"invites": [], "accepted_total": 0}


async def test_an_invitation_cannot_invite_its_own_account(client: AsyncClient, session):
    owner = await _ready(client, "why_self@befos.app")
    invite = (await client.post(REFERRALS, headers=auth_headers(owner["token"]))).json()

    duplicate = await client.post(
        REGISTER,
        json={
            "email": owner["email"],
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "consent_version": CONSENT_VERSION,
            "invite_code": invite["code"],
        },
    )
    assert duplicate.status_code == 409, duplicate.text
    spent = (
        await session.execute(
            select(Invitation.accepted_at).where(Invitation.code == invite["code"])
        )
    ).scalar_one()
    assert spent is None
    assert (await client.post(
        "/api/v1/invites/preview", json={"code": invite["code"]}
    )).json()["valid"] is True


async def test_the_daily_mint_is_bounded(client: AsyncClient, session):
    inviter = await _ready(client, "why_daily@befos.app")
    inviter_id = uuid.UUID(inviter["user_id"])
    session.add_all(
        [
            Invitation(
                inviter_id=inviter_id,
                code=f"daily-{index}-{uuid.uuid4().hex}"[:32],
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            for index in range(20)
        ]
    )
    await session.commit()

    refused = await client.post(REFERRALS, headers=auth_headers(inviter["token"]))
    assert refused.status_code == 429, refused.text
    assert refused.json()["error"]["code"] == "rate_limited"


async def test_erasing_an_account_cuts_it_out_of_the_doors_it_walked_through(
    client: AsyncClient, session
):
    """The account row is soft-deleted, so the schema's CASCADE never fires: erasure must name
    the new rows itself. The guest's id leaves the invitation; their own waiting mark goes; and
    erasing the inviter takes the door with them, because a link has no owner left to answer for.
    """
    inviter = await _ready(client, "why_erase_inviter@befos.app")
    invite = (
        await client.post(REFERRALS, headers=auth_headers(inviter["token"]))
    ).json()

    guest = (
        await client.post(
            REGISTER,
            json={
                "email": "why_erase_guest@befos.app",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
                "consent_version": CONSENT_VERSION,
                "invite_code": invite["code"],
            },
        )
    ).json()
    guest_id = uuid.UUID(guest["user"]["id"])
    guest_token = guest["tokens"]["access_token"]

    joined = await client.post(
        WAITLIST, json={"city": "Казань"}, headers=auth_headers(guest_token)
    )
    assert joined.status_code == 200 and joined.json()["joined"] is True, joined.text

    erased_guest = await client.delete("/api/v1/users/me", headers=auth_headers(guest_token))
    assert erased_guest.status_code == 200, erased_guest.text

    session.expire_all()
    row = (
        await session.execute(select(Invitation).where(Invitation.code == invite["code"]))
    ).scalar_one()
    assert row.accepted_by_user_id is None, "the erased guest's id survived in somebody's link"
    assert row.accepted_at is not None, "erasure reopened a spent door"

    waiting = (
        await session.execute(
            select(func.count()).select_from(WaitlistEntry).where(WaitlistEntry.user_id == guest_id)
        )
    ).scalar_one()
    assert waiting == 0, "the erased account still waits in a city"

    # The door belonged to the inviter, and their erasure takes it: a live code outliving the
    # person who can revoke it is a promise nobody holds.
    erased_inviter = await client.delete(
        "/api/v1/users/me", headers=auth_headers(inviter["token"])
    )
    assert erased_inviter.status_code == 200, erased_inviter.text
    session.expire_all()
    left = (
        await session.execute(
            select(func.count())
            .select_from(Invitation)
            .where(Invitation.inviter_id == uuid.UUID(inviter["user_id"]))
        )
    ).scalar_one()
    assert left == 0


async def test_the_analytics_line_names_a_reason_and_never_a_code_or_a_city(
    client: AsyncClient, caplog
):
    inviter = await _ready(client, "why_logs@befos.app")
    invite = (
        await client.post(REFERRALS, headers=auth_headers(inviter["token"]))
    ).json()
    with caplog.at_level(logging.INFO, logger="analytics"):
        preview = await client.post(
            "/api/v1/invites/preview", json={"code": invite["code"]}
        )
        assert preview.status_code == 200, preview.text
        joined = await client.post(
            WAITLIST, json={"city": "Екатеринбург"}, headers=auth_headers(inviter["token"])
        )
        assert joined.status_code == 200, joined.text
        # The funnel needs its denominator: a registration that carried no invitation is still a
        # completed registration, and the event says so without the address that made it.
        newcomer = await register_and_auth(client, "why_newcomer@befos.app", verify=True)
    assert "invite_opened" in caplog.text
    assert "waitlist_joined" in caplog.text
    assert "registration_completed" in caplog.text
    assert invite["code"] not in caplog.text, "the invitation code reached the log"
    assert "Екатеринбург" not in caplog.text, "the city reached the analytics journal"
    assert inviter["email"] not in caplog.text, "the inviter's address reached the analytics journal"
    assert newcomer["email"] not in caplog.text, "the newcomer's address reached the analytics journal"
