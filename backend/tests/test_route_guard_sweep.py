"""The guard set read off the routes the application exports, not off a list of them.

A checklist of "routes that must refuse a stranger" decays the moment an eleventh route is
added to the ten someone wrote down: the new one is unguarded and the suite stays green,
because the list is prose and prose is not executed. This walks the real route table instead,
so a route that takes an object identifier is covered from the commit that mounts it.

Two things are asserted for every such route: an anonymous caller is not served, and a
caller holding a valid token of its own is not served someone else's object. "Not served"
means a refusal the client can act on — never a 2xx, never a 5xx.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.main import create_app

from .conftest import auth_headers, register_and_auth

# A well-formed value that no row carries. Written per parameter because the identifiers are
# not one type: `activity_id` is an INTEGER from the catalogue, the rest are UUIDs, and a
# sweep that sent a UUID where an int is expected would be asserting on a 422 from the
# request model rather than on the guard it is here to look at.
_UNKNOWN_VALUES = {
    "user_id": lambda: str(uuid.uuid4()),
    "match_id": lambda: str(uuid.uuid4()),
    "plan_id": lambda: str(uuid.uuid4()),
    "activity_id": lambda: "999999",
    "photo_id": lambda: str(uuid.uuid4()),
    "report_id": lambda: str(uuid.uuid4()),
    # The number a person gives to end one of their own sessions. It is an object identifier in the
    # same sense as the rest: it names a row, and the row belongs to whoever signed in.
    "session_id": lambda: str(uuid.uuid4()),
    # The number a person gives to take back a line they typed. Same sense again: it names one row
    # of one pair, and only the half that typed it owns the write.
    "message_id": lambda: str(uuid.uuid4()),
}

_HTTP_METHODS = ("GET", "POST", "PATCH", "PUT", "DELETE")


def _a_future_instant() -> str:
    """A moment the route would accept on its merits, so the refusal it gives is about the row."""
    return (datetime.now(timezone.utc) + timedelta(days=2)).replace(
        minute=0, second=0, microsecond=0
    ).isoformat()


def _identifier_calls() -> list[tuple[str, str]]:
    """Every (method, concrete path) pair in the route table that names an object id.

    Enumerated from ``create_app()`` — the same factory the ``client`` fixture serves — so the
    sweep walks what the product actually mounts, including a route nobody has added yet.
    """
    calls: list[tuple[str, str]] = []
    for route in create_app().routes:
        if not isinstance(route, APIRoute):
            continue
        names = re.findall(r"\{(\w+)}", route.path)
        if not names:
            continue
        if not all(name in _UNKNOWN_VALUES for name in names):
            raise AssertionError(
                f"{route.path} takes {names}, which the sweep has no unknown value for. Add "
                "one, or say here why this parameter is not an object identifier."
            )
        path = route.path
        for name in names:
            path = path.replace(f"{{{name}}}", _UNKNOWN_VALUES[name]())
        for method in sorted(route.methods & set(_HTTP_METHODS)):
            calls.append((method, path))
    return calls


def test_the_sweep_walks_the_whole_identifier_surface() -> None:
    """A sweep that walks nothing is a green decoration; this is the assertion on its reach.

    The floor is not a target — it fails when a route drops out of the table (a rename, a
    removal, a parameter the mapping no longer knows), which is how a hand-written list goes
    quietly stale and how an automated one would too if nobody read the set it produced.
    Measured on this tree: 38 calls — 6 under ``/users/{user_id}`` (both halves of the block pair
    among them: a route that lets one of a write and its undo through is exactly what this floor is
    here to catch), 2 under ``/users/me/photo/{photo_id}``, 1 under ``/auth/sessions/{session_id}/revoke``
    (the door stage 110 gives a person to end one session of their own), 2 under ``/reports/{report_id}``
    (the moderation read and the decision write stage 102 mounts), 15 under ``/matches/{match_id}`` (five
    of which also name an ``activity_id``, one of which is the ``DELETE`` stage 105 mounts to end
    a pair without a block, and one of which is the ``DELETE`` stage 111 mounts to take back a line the
    person typed) and 12 under ``/plans/{plan_id}``.
    """
    calls = _identifier_calls()
    paths = {path for _, path in calls}
    assert len(calls) >= 25, f"only {len(calls)} identifier calls found: {sorted(paths)}"

    for fragment in (
        "/like", "/pass", "/block", "/report", "/messages", "/read",
        "/compatibility", "/recommendations", "/select", "/time", "/time/accept",
        "/plans", "/accept", "/hour", "/hour/confirm", "/cancel", "/complete", "/note",
        # The two writes that name a photograph: a route that stops taking the number, or a number
        # that stops being swept, takes one of these out of the set. ``/photo/`` alone would not —
        # both of them carry it, and only ``/primary`` says which of the two is which.
        "/photo/", "/primary",
        # The decision route. ``/report`` above would not catch it disappearing: that fragment is a
        # substring of ``/reports``, so the complaint a person files and the queue a moderator reads
        # would answer for one another. ``/review`` names only the write that closes one.
        "/review",
    ):
        assert any(fragment in path for path in paths), f"{fragment} is not in the swept set"

    # The route that ends a pair takes the bare path, so no fragment above names it — only its method
    # does, and a fragment test cannot see a verb disappear. Without this line the pair's own door can
    # leave the table, the count can fall to 35, and the floor above still reads green.
    pair_endings = [(method, path) for method, path in calls if re.fullmatch(r"/api/v1/matches/[^/]+", path)]
    assert pair_endings, "no bare /matches/{match_id} call is in the swept set"
    assert any(method == "DELETE" for method, _ in pair_endings), (
        f"nothing in {sorted(pair_endings)} ends a pair: the route that ends one left the table"
    )

    # The same reason, one level deeper: ``/messages`` is a substring of the read and the write beside
    # it, so no fragment test would notice the door that takes a line back leaving the table while both
    # of its neighbours stay. Only the verb says which of the three this is.
    line_endings = [
        (method, path)
        for method, path in calls
        if re.fullmatch(r"/api/v1/matches/[^/]+/messages/[^/]+", path)
    ]
    assert line_endings, "no /matches/{match_id}/messages/{message_id} call is in the swept set"
    assert any(method == "DELETE" for method, _ in line_endings), (
        f"nothing in {sorted(line_endings)} takes a typed line back: the door that erases one left "
        "the table"
    )


async def test_an_anonymous_caller_is_not_served_any_identifier_route(
    client: AsyncClient
) -> None:
    """No route that names an object belongs to the public, whatever else it does."""
    failures: list[str] = []
    for method, path in _identifier_calls():
        response = await client.request(method, path, json={})
        if response.status_code != 401:
            failures.append(f"{method} {path} -> {response.status_code}")
    assert not failures, "anonymous callers should be refused before anything else: " + "; ".join(failures)


async def test_a_stranger_with_a_valid_token_is_never_served_another_users_object(
    client: AsyncClient
) -> None:
    """A real token plus a guessed id must not be a read of, or a write into, somebody's row.

    Absent ids are indistinguishable from foreign ones here, which is the point: the answer
    a stranger gets may not depend on whether the row exists.
    """
    account = await register_and_auth(client, "sweep_stranger@befos.app")
    headers = auth_headers(account["token"])
    failures: list[str] = []
    for method, path in _identifier_calls():
        response = await client.request(method, path, json={}, headers=headers)
        if response.status_code >= 500 or response.status_code in (200, 201, 202, 204):
            failures.append(f"{method} {path} -> {response.status_code} {response.text[:120]}")
    assert not failures, "identifier routes answered a stranger: " + "; ".join(failures)


async def test_every_route_naming_a_match_refuses_an_outsider_the_same_way(
    client: AsyncClient
) -> None:
    """One row, one answer.

    ``GET /matches/{id}`` said 404 while the chat and recommendation routes on the very same
    row said 403. The difference is not a courtesy: it tells the caller which pairing is real
    without returning a byte of it, and it is exactly the oracle the block/visibility work set
    out to close. Every match route now answers the way `GET /matches/{id}` did.
    """
    from .test_idor_authorization import _matched_pair, _ready

    a, b, match_id = await _matched_pair(client)
    c = await _ready(client, "sweep_c@befos.app", "Вика", "female")
    headers = auth_headers(c["token"])

    calls = [
        ("GET", f"/api/v1/matches/{match_id}", {}),
        ("GET", f"/api/v1/matches/{match_id}/compatibility", {}),
        ("GET", f"/api/v1/matches/{match_id}/recommendations", {}),
        ("POST", f"/api/v1/matches/{match_id}/recommendations/1/select", {}),
        # Both halves of one decision the pair owns: a refusal writes a row and takes it back,
        # and neither may answer an outsider differently from the route beside it.
        ("POST", f"/api/v1/matches/{match_id}/recommendations/1/decline", {}),
        ("DELETE", f"/api/v1/matches/{match_id}/recommendations/1/decline", {}),
        # Both time taps carry a well-formed instant for the same reason as the message body:
        # the request model is checked before the service, and a 422 from an empty body says
        # nothing about the row. A named moment is a write into this pair's card.
        (
            "PUT",
            f"/api/v1/matches/{match_id}/recommendations/1/time",
            {"when": _a_future_instant()},
        ),
        (
            "POST",
            f"/api/v1/matches/{match_id}/recommendations/1/time/accept",
            {"when": _a_future_instant()},
        ),
        ("GET", f"/api/v1/matches/{match_id}/messages", {}),
        # A well-formed body here, because the request model is checked before the service
        # is entered: an empty one is refused as invalid input, and that answer says nothing
        # about the row. This test is about the answer that does.
        ("POST", f"/api/v1/matches/{match_id}/messages", {"body": "sweep"}),
        # The door that takes a line back, swept with an invented line number: the outsider must not
        # learn from this answer whether the row it names exists, so the row is not created here.
        ("DELETE", f"/api/v1/matches/{match_id}/messages/{uuid.uuid4()}", {}),
        ("POST", f"/api/v1/matches/{match_id}/read", {}),
    ]
    for method, path, payload in calls:
        response = await client.request(method, path, json=payload, headers=headers)
        assert response.status_code == 404, f"{method} {path} -> {response.status_code}: {response.text}"
        assert response.json()["error"]["code"] == "not_found", path

    # And the pair's own member still gets their answer, so the uniform refusal was not
    # achieved by shutting the routes.
    ok = await client.get(f"/api/v1/matches/{match_id}", headers=auth_headers(a["token"]))
    assert ok.status_code == 200, ok.text
