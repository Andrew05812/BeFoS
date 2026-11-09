"""An account is not a person in the deck until it has read a letter sent to its own address.

Stage 131 closes the second of the audit's two P0 blockers (`docs/PRODUCT_TECHNICAL_AUDIT.md` §11,
P0-2). The first — no way back into a lost word — is covered by
`test_the_lost_word_comes_back_through_a_letter_that_dies.py`. This file is the contract of the other
half:

* registration cannot happen without the text the product publishes, and the row carries which
  version was accepted and when (`users.consent_version`, `users.consent_accepted_at`);
* the text is readable before there is an account, and an account that accepted an older draft can
  accept the current one — the stamp moves, and `/users/me` says so;
* registration itself writes the confirmation letter into the configured channel, addressed to the
  address that was typed;
* only the code printed in that letter flips `is_verified` — no request body sets the flag, and the
  row stores the digest, not the code;
* an unconfirmed account is invisible to the deck and to `POST /users/{id}/like`, and becomes visible
  the moment the letter is answered;
* resending is silent while a live letter exists, silent for a confirmed address, and requires the
  session of the account it would write to.

The letter channel is the development `outbox`: this file reads `*.eml` files out of a directory the
test owns, the same way `services/mail.py` writes them. No external service is contacted; connecting
one is the operator's decision (`docs/RELEASE.md` §11).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.consent import CONSENT_VERSION
from app.models import AuthChallenge, User
from app.services.mail import CONFIRM_SUBJECT

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth

REGISTER = "/api/v1/auth/register"
CONFIRM = "/api/v1/auth/email-confirmation/confirm"
RESEND = "/api/v1/auth/email-confirmation/resend"
CONSENT = "/api/v1/auth/consent"
ME = "/api/v1/users/me"
DISCOVER = "/api/v1/discover"

_GROUPED = re.compile(r"\b[0-9A-HJ-NP-Z]{4}(?:-[0-9A-HJ-NP-Z]{4}){2}\b")
PASSWORD = "Test12345"


@pytest.fixture
def outbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A mailbox this test owns: the channel writes here and nobody else reads it."""
    monkeypatch.setattr(settings, "mail_transport", "outbox")
    monkeypatch.setattr(settings, "mail_outbox_dir", str(tmp_path))
    return tmp_path


def _letters(directory: Path, subject: str) -> list[Path]:
    return sorted(
        letter
        for letter in directory.glob("*.eml")
        if subject in letter.read_text(encoding="utf-8")
    )


def _code(directory: Path, email: str) -> str:
    """The one code printed in the newest letter addressed to this mailbox."""
    address = email.lower()
    for letter in reversed(_letters(directory, CONFIRM_SUBJECT)):
        body = letter.read_text(encoding="utf-8")
        if f"to: {address}" not in body.lower():
            continue
        found = _GROUPED.search(body)
        assert found, f"the letter to {address} prints no readable code"
        return found.group(0).replace("-", "")
    raise AssertionError(f"no confirmation letter for {email!r} in {directory}")


async def _register(client: AsyncClient, email: str, *, consent: str = CONSENT_VERSION):
    return await client.post(
        REGISTER,
        json={
            "email": email,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "consent_version": consent,
        },
    )


async def _me(client: AsyncClient, token: str) -> dict:
    resp = await client.get(ME, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _challenge(session: AsyncSession, user_id: uuid.UUID) -> AuthChallenge:
    return (
        await session.execute(
            select(AuthChallenge).where(
                AuthChallenge.user_id == user_id,
                AuthChallenge.purpose == "email_confirmation",
            )
        )
    ).scalars().one()


# ------------------------------------------------------------------- the text and its stamp


async def test_registration_without_the_text_is_refused_and_writes_no_account(
    client: AsyncClient,
):
    """A body that names no text cannot make an account: silence is not a signature."""
    missing = await client.post(
        REGISTER,
        json={"email": "no-text@befos.app", "password": PASSWORD, "password_confirm": PASSWORD},
    )
    assert missing.status_code == 422, missing.text

    stale = await _register(client, "stale-text@befos.app", consent="0")
    assert stale.status_code == 422, stale.text

    login = await client.post(
        "/api/v1/auth/login", json={"email": "no-text@befos.app", "password": PASSWORD}
    )
    assert login.status_code == 401, "the door refused, and the account appeared anyway"

    login_stale = await client.post(
        "/api/v1/auth/login", json={"email": "stale-text@befos.app", "password": PASSWORD}
    )
    assert login_stale.status_code == 401


async def test_the_document_is_public_and_is_the_one_registration_checks(client: AsyncClient):
    """The client must be able to read the text before it has a session; the version is the bridge."""
    document = await client.get(CONSENT)
    assert document.status_code == 200, document.text
    body = document.json()
    assert body["version"] == CONSENT_VERSION
    assert body["effective_date"], "the text has no effective date"
    assert len(body["text"]) > 400, "the consent is shorter than one paragraph"
    assert "18" in body["text"], "the age boundary is not named in the text"
    assert "@befos" not in body["text"], "the document names somebody's address"

    accepted = await _register(client, "document-readable@befos.app")
    assert accepted.status_code == 201, accepted.text


async def test_the_row_names_the_version_and_the_moment(
    client: AsyncClient, session: AsyncSession
):
    accepted = await _register(client, "stamped@befos.app")
    assert accepted.status_code == 201, accepted.text

    user = (
        await session.execute(select(User).where(User.email == "stamped@befos.app"))
    ).scalar_one()
    assert user.consent_version == CONSENT_VERSION
    assert user.consent_accepted_at is not None
    assert user.consent_accepted_at.tzinfo is not None, "the consent moment is stored without a zone"


async def test_an_older_stamp_is_renewed_by_the_consent_door(
    client: AsyncClient, session: AsyncSession
):
    accepted = await _register(client, "renewal@befos.app")
    assert accepted.status_code == 201, accepted.text
    token = accepted.json()["tokens"]["access_token"]
    user_id = uuid.UUID(accepted.json()["user"]["id"])

    # The row as an account from before this stage looks: no text on file.
    await session.execute(
        update(User).where(User.id == user_id).values(consent_version=None, consent_accepted_at=None)
    )
    await session.commit()
    assert (await _me(client, token))["consent_up_to_date"] is False

    stale = await client.post(CONSENT, json={"consent_version": "0"}, headers=auth_headers(token))
    assert stale.status_code == 422, stale.text

    renewed = await client.post(
        CONSENT, json={"consent_version": CONSENT_VERSION}, headers=auth_headers(token)
    )
    assert renewed.status_code == 204, renewed.text
    assert (await _me(client, token))["consent_up_to_date"] is True
    assert (await session.get(User, user_id)).consent_version == CONSENT_VERSION


async def test_the_renewal_door_needs_the_account_it_writes_to(client: AsyncClient):
    anonymous = await client.post(CONSENT, json={"consent_version": CONSENT_VERSION})
    assert anonymous.status_code == 401, anonymous.text


# ----------------------------------------------------------------------- the letter and the code


async def test_registration_writes_the_letter_and_me_does_not_believe_it_yet(
    client: AsyncClient, outbox: Path
):
    email = "letter-first@befos.app"
    accepted = await _register(client, email)
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["user"]["is_verified"] is False

    letters = _letters(outbox, CONFIRM_SUBJECT)
    assert len(letters) == 1, f"confirmation letters: {len(letters)} for one registration"
    body = letters[0].read_text(encoding="utf-8")
    assert f"To: {email}" in body, body[:200]
    code = _code(outbox, email)
    assert len(code) == 12 and code.isalnum()

    token = accepted.json()["tokens"]["access_token"]
    assert (await _me(client, token))["email_verified"] is False


async def test_the_code_from_the_letter_is_the_only_thing_that_confirms(
    client: AsyncClient, session: AsyncSession, outbox: Path
):
    email = "only-the-code@befos.app"
    accepted = await _register(client, email)
    token = accepted.json()["tokens"]["access_token"]
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()

    row = await _challenge(session, user.id)
    assert row.consumed_at is None
    code = _code(outbox, email)
    assert len(row.token_hash) == 64 and row.token_hash != code
    assert row.expires_at > datetime.now(timezone.utc) + timedelta(
        minutes=settings.confirm_code_minutes - 2
    )

    # No body writes the flag on the client's word: the profile update has no such field.
    write = await client.patch(
        ME,
        json={"email_verified": True, "is_verified": True},
        headers=auth_headers(token),
    )
    assert write.status_code == 200, write.text
    assert (await _me(client, token))["email_verified"] is False

    confirmed = await client.post(CONFIRM, json={"code": code})
    assert confirmed.status_code == 204, confirmed.text
    assert (await _me(client, token))["email_verified"] is True

    await session.refresh(row)
    assert row.consumed_at is not None, "the redemption was not written to the row"


async def test_an_unknown_a_spent_and_an_expired_code_answer_one_way(
    client: AsyncClient, session: AsyncSession, outbox: Path
):
    email = "three-refusals@befos.app"
    await _register(client, email)
    code = _code(outbox, email)

    unknown = await client.post(CONFIRM, json={"code": "ZZZZ-ZZZZ-ZZZZ"})
    assert unknown.status_code == 401, unknown.text
    sentence = unknown.json()["error"]["message"]

    spent_ok = await client.post(CONFIRM, json={"code": code})
    assert spent_ok.status_code == 204, spent_ok.text
    spent = await client.post(CONFIRM, json={"code": code})
    assert spent.status_code == 401, spent.text
    assert spent.json()["error"]["message"] == sentence, "the door named a spent code"

    other = "expired-alone@befos.app"
    await _register(client, other)
    other_user = (await session.execute(select(User).where(User.email == other))).scalar_one()
    await session.execute(
        update(AuthChallenge)
        .where(AuthChallenge.user_id == other_user.id)
        .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await session.commit()
    expired = await client.post(CONFIRM, json={"code": _code(outbox, other)})
    assert expired.status_code == 401, expired.text
    assert expired.json()["error"]["message"] == sentence, "the door named an expired code"

    login = await client.post("/api/v1/auth/login", json={"email": other, "password": PASSWORD})
    assert (await _me(client, login.json()["tokens"]["access_token"]))["email_verified"] is False


async def test_resending_is_silent_while_a_live_letter_exists(
    client: AsyncClient, session: AsyncSession, outbox: Path
):
    email = "resend-throttle@befos.app"
    accepted = await _register(client, email)
    token = accepted.json()["tokens"]["access_token"]
    user_id = uuid.UUID(accepted.json()["user"]["id"])
    first = _code(outbox, email)

    answer = await client.post(RESEND, headers=auth_headers(token))
    assert answer.status_code == 204, answer.text
    assert len(_letters(outbox, CONFIRM_SUBJECT)) == 1, "a second letter without a second door"

    # Once the first letter's window has passed, the resend door is the retry it promises to be.
    await session.execute(
        update(AuthChallenge)
        .where(AuthChallenge.user_id == user_id, AuthChallenge.purpose == "email_confirmation")
        .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await session.commit()
    again = await client.post(RESEND, headers=auth_headers(token))
    assert again.status_code == 204, again.text
    assert len(_letters(outbox, CONFIRM_SUBJECT)) == 2, "an expired letter was not resent"
    second = _code(outbox, email)
    assert second != first

    stale = await client.post(CONFIRM, json={"code": first})
    assert stale.status_code == 401, "the old code woke up beside the new letter"
    fresh = await client.post(CONFIRM, json={"code": second})
    assert fresh.status_code == 204, fresh.text


async def test_resending_after_confirmation_is_a_silent_no_op(
    client: AsyncClient, outbox: Path
):
    email = "nothing-more-to-send@befos.app"
    accepted = await _register(client, email)
    token = accepted.json()["tokens"]["access_token"]
    await client.post(CONFIRM, json={"code": _code(outbox, email)})

    answer = await client.post(RESEND, headers=auth_headers(token))
    assert answer.status_code == 204, answer.text
    assert len(_letters(outbox, CONFIRM_SUBJECT)) == 1, "a confirmed address needs no letter"


async def test_resending_is_not_a_public_mail_relay(client: AsyncClient, outbox: Path):
    anonymous = await client.post(RESEND)
    assert anonymous.status_code == 401, anonymous.text
    assert len(_letters(outbox, CONFIRM_SUBJECT)) == 0


# ------------------------------------------------------------------------------ the deck gate


async def _ready(client: AsyncClient, email: str, *, confirm: bool) -> dict:
    """A person the deck could show: onboarded, questionnaire answered, address proved or not."""
    account = await register_and_auth(client, email, verify=confirm)
    await complete_onboarding(client, account["token"], name=email.split("@")[0][:12])
    await answer_all_questions(client, account["token"])
    return account


async def _deck(client: AsyncClient, token: str) -> set[str]:
    response = await client.get(DISCOVER, params={"limit": 50}, headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return {card["user_id"] for card in response.json()["items"]}


async def test_an_unconfirmed_account_is_not_in_the_deck_and_cannot_be_liked(
    client: AsyncClient, outbox: Path
):
    viewer = await _ready(client, "gate-viewer@befos.app", confirm=True)
    unseen = await _ready(client, "gate-unseen@befos.app", confirm=False)
    seen = await _ready(client, "gate-seen@befos.app", confirm=True)

    cards = await _deck(client, viewer["token"])
    assert unseen["user_id"] not in cards, "an unconfirmed address entered the deck"
    assert seen["user_id"] in cards, "a confirmed address stayed out of the deck"

    refused = await client.post(
        f"/api/v1/users/{unseen['user_id']}/like", headers=auth_headers(viewer["token"])
    )
    assert refused.status_code == 404, refused.text

    # The letter is answered by whoever holds the mailbox; the viewer's screen is not involved.
    confirmed = await client.post(CONFIRM, json={"code": _code(outbox, unseen["email"])})
    assert confirmed.status_code == 204, confirmed.text
    cards = await _deck(client, viewer["token"])
    assert unseen["user_id"] in cards, "a confirmed account did not appear in the deck"


# ------------------------------------------------------------------------------ the export


async def test_the_export_carries_the_text_and_the_address_proof(client: AsyncClient):
    accepted = await _register(client, "in-the-export@befos.app")
    token = accepted.json()["tokens"]["access_token"]

    document = await client.get(f"{ME}/export", headers=auth_headers(token))
    assert document.status_code == 200, document.text
    account = document.json()["account"]
    assert account["consent_version"] == CONSENT_VERSION
    assert account["consent_accepted_at"] is not None
    assert account["is_verified"] is False
    assert account["email"] == "in-the-export@befos.app"
