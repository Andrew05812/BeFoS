"""Getting back into an account whose word was lost, through a letter that says how long it works.

Why a service of its own rather than three more methods on `AuthService`: everything that class does
rests on the caller already knowing the word — register, authenticate, rotate, change, revoke. This
is the one auth path whose premise is the opposite, and it therefore needs something no other auth
path touches: a channel that leaves this process. Keeping it apart is also what keeps the honesty
rules visible in one file instead of smeared across eight doors.

Two of those rules, stated because the audit (P0-1) and README («Чего в проекте нет») both hang on
them:

* an accepted request means a letter was written or handed to a peer. It does not mean a mailbox
  received anything, and nothing in this file says it does;
* the answer never depends on whether the address holds an account, so the door cannot be used as an
  enumeration service. The code is minted and hashed on both branches, and the branch that has nobody
  to write to writes nothing — the alternative, sending a letter to an address that holds no account,
  would confirm the same fact in a place the server cannot take back.

The word is changed in one commit with the sessions it invalidates: `revoke_all_for_user` and the
password write are in the same transaction, so there is no moment where the old word works and the
new one does too (`docs/API.md` says which sessions this ends).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import UnauthorizedError, ValidationError
from app.core.logging import get_logger
from app.core.security import (
    generate_recovery_code,
    generate_token_hash,
    hash_password_async,
    normalise_recovery_code,
)
from app.models import ChallengePurpose, User
from app.repositories.challenge_repo import ChallengeRepository
from app.repositories.token_repo import TokenRepository
from app.repositories.user_repo import UserRepository
from app.services.mail import current_transport, password_reset_letter

logger = get_logger(__name__)

# One sentence for every refusal this door can give. Naming the reason — expired, used, unknown —
# would tell a caller how far a guess got, which is the same argument `page_cursor.py:25-28` makes
# about a broken page link and `auth_service.py:69-84` makes about sign-in timing.
REFUSED = "The code did not work. Ask for a new letter."


class RecoveryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.tokens = TokenRepository(session)
        self.challenges = ChallengeRepository(session)

    async def request_reset(self, email: str) -> int:
        """Mint a code, hand the letter to the configured channel, and report the window in seconds.

        Returns the window because it is a product constant, not a fact about the caller: the door
        needs the number for its answer body and the number must be the same one whether or not this
        address is anybody.
        """
        minutes = settings.reset_code_minutes
        window = minutes * 60

        user = await self.users.get_by_email(email)
        code = generate_recovery_code()
        digest = generate_token_hash(code)

        if user is None or user.is_deleted or not user.is_active:
            # Nothing was written and nothing was sent. The log line is for the operator, who
            # otherwise reads a silent 202 as a delivery; it names no address and no code.
            logger.info("Recovery asked for an address with no live account")
            return window

        live = await self.challenges.live_for(user.id, ChallengePurpose.PASSWORD_RESET)
        if live is not None:
            # One live code per account. The second request gets the same answer and no second
            # letter, because the letter is the abuse surface of this design: without this branch a
            # script with one address can make the mail channel emit a message per request.
            return window

        await self.challenges.issue(
            user.id, ChallengePurpose.PASSWORD_RESET, digest, minutes
        )
        letter = password_reset_letter(
            to=user.email,
            code=code,
            minutes=minutes,
            link_base=settings.mail_link_base,
        )
        # Handed over before the commit on purpose. A transport that raises leaves the flushed row
        # uncommitted, so a failed send cannot strand a live code that no letter ever carried; the
        # caller hears a 500 and the next request starts clean.
        where = await current_transport().send(letter)
        await self.session.commit()
        logger.info("Recovery letter handed to the channel destination=%s", where)
        return window

    async def complete_reset(self, code: str, new_password: str, password_confirm: str) -> None:
        """Spend a code on a word the caller says twice, and end every session the account held.

        The order is the one `change_password` argues for (`auth_service.py:137-149`): the two formal
        rules are answered before any bcrypt is paid, so an opt-in refusal on a mistyped confirmation
        costs the same as any other refusal and does not warm the CPU for an attacker.
        """
        if new_password != password_confirm:
            raise ValidationError("Passwords do not match.")

        owner = await self.challenges.redeem(
            generate_token_hash(normalise_recovery_code(code)), ChallengePurpose.PASSWORD_RESET
        )
        if owner is None:
            raise UnauthorizedError(REFUSED)

        user = await self.session.get(User, owner)
        if user is None or user.is_deleted or not user.is_active:
            # Unreachable while the foreign key cascades, and still answered as a refusal rather than
            # as a 500: the code was spent, and a person who is told «the server broke» will ask for
            # another letter while the account they mean is gone.
            raise UnauthorizedError(REFUSED)

        user.password_hash = await hash_password_async(new_password)
        await self.tokens.revoke_all_for_user(user.id)
        # Any other letter still lying around for this account stops being a door the moment the word
        # behind it changes — the person who asked for a new word has just said something was wrong.
        await self.challenges.expire_live_for(user.id, ChallengePurpose.PASSWORD_RESET)
        await self.session.commit()
        logger.info("Recovered the word of an account user_id=%s", user.id)
