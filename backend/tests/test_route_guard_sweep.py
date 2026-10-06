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
    "activity_id": lambda: "999999",
}

_HTTP_METHODS = ("GET", "POST", "PATCH", "PUT", "DELETE")


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
    Measured on this tree: 12 calls — 5 routes under ``/users/{user_id}`` and 7 under
    ``/matches/{match_id}``, one of which also names an ``activity_id``.
    """
    calls = _identifier_calls()
    paths = {path for _, path in calls}
    assert len(calls) >= 12, f"only {len(calls)} identifier calls found: {sorted(paths)}"

    for fragment in (
        "/like", "/pass", "/block", "/report", "/messages", "/read",
        "/compatibility", "/recommendations", "/select",
    ):
        assert any(fragment in path for path in paths), f"{fragment} is not in the swept set"


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
        ("GET", f"/api/v1/matches/{match_id}/messages", {}),
        # A well-formed body here, because the request model is checked before the service
        # is entered: an empty one is refused as invalid input, and that answer says nothing
        # about the row. This test is about the answer that does.
        ("POST", f"/api/v1/matches/{match_id}/messages", {"body": "sweep"}),
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
