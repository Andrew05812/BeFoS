"""The account can take back its own word, and every session that carried the old one falls.

Nothing on the surface could change a password. `AuthService.change_password` has been in the tree
since the session routes were written — it checks the old word, demands eight characters of the new
one, rehashes and calls `revoke_all_for_user` — and no route has ever called it, so the rule existed
as a method no door reached and no test ever ran. A person who had typed their password into another
device, or who simply wanted a word nobody else knew, had exactly one door: delete the account. The
live probe against `523003d` measured that (`s109_red_pre.log`): the door answered 404, while the
service it should have used stayed reachable only from Python.

What this file pins is the shape the door must have, held by the mechanism the sessions already have
rather than by a second one:

The old word is asked for, and a wrong answer changes nothing — not the hash, not the sessions. The
person who guesses at a keyboard must not be able to lock the owner out of their own account by
half-writing a new password.

Eight characters is the same bar registration sets, and the new word must be said twice. A rule about
a password lives in the service that writes passwords, next to the rule register already keeps there,
so one edit cannot leave the two doors asking different questions.

A changed password is not a note next to the old one. The old word stops being a key the moment the
new one is written, and every living refresh token of that person is taken down — including the one
the caller is standing on, which is why the answer is an empty 204 rather than a fresh pair of
tokens: the client that asked has to go back through the login screen and be told so.

The access token that was already handed out lives out the minutes it was given for, because it is a
signed word the server checks without asking anyone. This stage does not pretend otherwise, and
measures the window instead of hiding it: a session that is already open keeps working for the rest of
`ACCESS_TOKEN_EXPIRE_MINUTES`, and after that it has no refresh token to reach for.

One person's word is their own. A second account cannot move this account's password by asking, and
changing one account's password leaves the other account's key exactly as it was.

The door is a guessing surface, so it is mounted on the same `/auth` router the sign-in doors use and
answers to the same 20-a-minute window per address. The row counts that shipped ceiling, not a patched
one, and checks that when the change door stops answering, signing in from the same address has stopped
answering with it.
"""
from __future__ import annotations

import json

from httpx import AsyncClient

from .conftest import auth_headers, register_and_auth

OLD_WORD = "Test12345"
NEW_WORD = "FreshWOrd987"
DOOR = "/api/v1/auth/change-password"
# app/core/rate_limit.py: _auth_limiter holds 20 auth calls per 60 s per address.
AUTH_WINDOW = 20


async def _change(client: AsyncClient, token: str, **words) -> tuple[int, str]:
    resp = await client.post(DOOR, json=words, headers=auth_headers(token))
    return resp.status_code, resp.text


async def _login(client: AsyncClient, email: str, password: str) -> int:
    return (
        await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    ).status_code


async def _account(client: AsyncClient, email: str = "rotate_a@befos.app") -> dict:
    return await register_and_auth(client, email, OLD_WORD)


async def test_the_door_of_a_password_answers_to_its_owner(client: AsyncClient) -> None:
    """The account has a door for its own word, and it opens on nothing but a 204.

    Before this row the door did not exist: `AuthService.change_password` was reachable only from
    Python, and a person who needed a new password had the delete-account screen as their only
    answer. The empty body is deliberate — the caller's session is one of the ones being taken down,
    so the server must not hand out a token pair it has just made meaningless.
    """
    account = await _account(client)
    code, body = await _change(
        client,
        account["token"],
        old_password=OLD_WORD,
        new_password=NEW_WORD,
        password_confirm=NEW_WORD,
    )
    assert code == 204, body
    assert await _login(client, account["email"], OLD_WORD) == 401, "the old word still opens the account"
    assert await _login(client, account["email"], NEW_WORD) == 200


async def test_an_anonymous_request_has_no_password_to_change(client: AsyncClient) -> None:
    """The door names no account, because it belongs to whoever is standing in front of it.

    There is no user id in the body for an attacker to try, which is also why this route cannot have
    an IDOR case: the only account it can reach is the one the bearer token already resolved.
    """
    resp = await client.post(
        DOOR,
        json={"old_password": OLD_WORD, "new_password": NEW_WORD, "password_confirm": NEW_WORD},
    )
    assert resp.status_code == 401, resp.text


async def test_a_wrong_old_word_changes_nothing_it_can_touch(client: AsyncClient) -> None:
    """Guessing at the old word is refused, and the refusal is not half a change.

    The hash stays where it was and the sessions stay alive: the person who mistypes their password
    must still be able to use it, and must not find themselves logged out of every device by a failed
    attempt.
    """
    account = await _account(client)
    code, body = await _change(
        client,
        account["token"],
        old_password="NotTheirWord1",
        new_password=NEW_WORD,
        password_confirm=NEW_WORD,
    )
    assert code == 401, body
    assert await _login(client, account["email"], OLD_WORD) == 200
    assert await _login(client, account["email"], NEW_WORD) == 401
    still_alive = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": account["refresh"]}
    )
    assert still_alive.status_code == 200, "a refused change took down a session it was not asked to"


async def test_the_new_word_is_held_to_the_bar_the_first_one_was(client: AsyncClient) -> None:
    """Seven characters is not a password here, exactly as it is not one at registration.

    The service already carried this rule (`auth_service.py:140`) and was never asked it; the door is
    where the rule becomes the product's answer.
    """
    account = await _account(client)
    code, body = await _change(
        client,
        account["token"],
        old_password=OLD_WORD,
        new_password="shortie",
        password_confirm="shortie",
    )
    assert code == 422, body
    assert await _login(client, account["email"], OLD_WORD) == 200


async def test_the_new_word_must_be_said_twice(client: AsyncClient) -> None:
    """A confirmation that differs from the new word is refused as one sentence, not two.

    Register answers this with «Passwords do not match.» through `ValidationError`; the change door
    answers with the same words from the same place, so a later edit cannot make the two doors ask
    different questions about one rule.
    """
    account = await _account(client)
    code, body = await _change(
        client,
        account["token"],
        old_password=OLD_WORD,
        new_password=NEW_WORD,
        password_confirm="FreshWOrd988",
    )
    assert code == 422, body
    assert "match" in body.lower(), body
    assert await _login(client, account["email"], OLD_WORD) == 200


async def test_a_changed_password_takes_down_every_living_session(client: AsyncClient) -> None:
    """The word was the key to all of them, so all of them go.

    Two logins from two devices make two refresh tokens. Changing the password revokes both, the
    caller's own included — that is `revoke_all_for_user`, the same statement account deletion
    already uses, so a rotated password does not leave a second revocation path behind.
    """
    account = await _account(client)
    second = await client.post(
        "/api/v1/auth/login", json={"email": account["email"], "password": OLD_WORD}
    )
    assert second.status_code == 200, second.text
    other_refresh = second.json()["tokens"]["refresh_token"]

    code, body = await _change(
        client,
        account["token"],
        old_password=OLD_WORD,
        new_password=NEW_WORD,
        password_confirm=NEW_WORD,
    )
    assert code == 204, body

    for token in (account["refresh"], other_refresh):
        refused = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        assert refused.status_code == 401, "a session survived the password it was signed with"


async def test_the_access_token_already_handed_out_lives_its_minutes(client: AsyncClient) -> None:
    """The window a changed password does not close is measured, not described.

    An access token is a signed word the server checks without a read, so the one this call was made
    with keeps working until its own `exp`. The stage writes that as a named boundary: the exposure
    after a rotation is at most `ACCESS_TOKEN_EXPIRE_MINUTES`, and there is no way through that window
    to a new session, because every refresh token is already dead.
    """
    from app.core.config import settings

    account = await _account(client)
    code, body = await _change(
        client,
        account["token"],
        old_password=OLD_WORD,
        new_password=NEW_WORD,
        password_confirm=NEW_WORD,
    )
    assert code == 204, body

    surviving = await client.get("/api/v1/users/me", headers=auth_headers(account["token"]))
    assert surviving.status_code == 200, (
        "the access token died earlier than the settings promise — the window this row names is now "
        "wrong and must be re-measured"
    )
    assert settings.access_token_expire_minutes == 30, settings.access_token_expire_minutes


async def test_guessing_at_the_old_word_runs_into_the_same_ceiling_as_signing_in(
    client: AsyncClient,
) -> None:
    """A door that asks for a secret is a guessing surface, and it shares the auth window.

    The route is mounted under the `/auth` router, so it inherits the 20-a-minute ceiling that slows
    credential stuffing against login — the same address spends one budget on both doors, which is
    what stops the new route from being a second, unlimited oracle for the old word. The row counts
    the shipped ceiling rather than a patched one: every attempt inside the window is answered on its
    merits (401, nothing written), and the attempts stop being answered at all once the window is
    spent. Signing in from the same address is refused in that same moment, which is the proof the
    budget is shared and not a per-route one.

    The window belongs to the auth doors only: an ordinary authenticated read keeps working while
    login is being refused.
    """
    from app.core.rate_limit import _auth_limiter

    account = await _account(client)
    assert _auth_limiter.limit == AUTH_WINDOW, _auth_limiter.limit

    refused_as_wrong_word = 0
    blocked_at: int | None = None
    for attempt in range(1, AUTH_WINDOW + 6):
        code, body = await _change(
            client,
            account["token"],
            old_password=f"NotTheirWord{attempt}",
            new_password=NEW_WORD,
            password_confirm=NEW_WORD,
        )
        if code == 429:
            assert json.loads(body)["error"]["code"] == "rate_limited", body
            blocked_at = attempt
            break
        assert code == 401, (attempt, code, body)
        refused_as_wrong_word += 1

    assert blocked_at is not None, "the change door answered an unlimited number of guesses"
    assert refused_as_wrong_word + 1 == blocked_at
    assert blocked_at <= AUTH_WINDOW + 1, f"the door outlived the auth window: {blocked_at}"

    still_guessable = await _login(client, account["email"], OLD_WORD)
    assert still_guessable == 429, (
        f"login still answers for this address at attempt {blocked_at}; "
        "the two doors no longer share one window"
    )

    untouched = await client.get("/api/v1/users/me", headers=auth_headers(account["token"]))
    assert untouched.status_code == 200, untouched.text


async def test_one_accounts_word_is_not_another_accounts_door(client: AsyncClient) -> None:
    """Rotating this password leaves the neighbour's key exactly as it was.

    `revoke_all_for_user` is keyed on the owner, and a change asked by B must not be a way to log A
    out of their own phone.
    """
    a = await _account(client, "rotate_a@befos.app")
    b = await register_and_auth(client, "rotate_b@befos.app", OLD_WORD)

    code, body = await _change(
        client,
        b["token"],
        old_password=OLD_WORD,
        new_password=NEW_WORD,
        password_confirm=NEW_WORD,
    )
    assert code == 204, body

    assert await _login(client, b["email"], NEW_WORD) == 200
    assert await _login(client, a["email"], OLD_WORD) == 200, (
        "a change by one account locked another one out"
    )
    still = await client.get("/api/v1/users/me", headers=auth_headers(a["token"]))
    assert still.status_code == 200, still.text
