"""The pair of doors stage 114 opened left the stand without a price, and its open end said so.

`CHANGELOG.md` recorded the gap in stage 114's own open end: the latency table of
`docs/SCALE_PLAN.md` names seventeen paths, and neither `GET /api/v1/discover/passed` nor
`DELETE /api/v1/users/{id}/pass` is among them — the newest reversible gesture of the app carries
no number the way the tap that sits beside it on the same card has carried one since stage 26.
The instrument cannot simply be pointed at the two doors: the pass read needs the viewer's own
`passes` rows, which `_seed_activity` has been writing since stage 20 (40 % of the stand is passed
on), while the return consumes what it prices — the second undo of one pass answers 404 and writes
nothing — so the return path has to rotate over fresh targets the way the `like` path does, and
that pool has to be addressed from the context, outside every measured window.

Nine checks, in the order the risk sits:

* the harness has a path for the pass list and for its return;
* the pass list reads rows the stand already writes and builds no crowd inside the timed call —
  the promise stage 42 made for the deck;
* both wrappers call the handlers the API dispatches, the rule stage 76 and stage 77 each had to
  re-learn, and take the reader from the context the way the auth dependency hands it over;
* the return rotates a pool the context built from the viewer's own passes, so no repeat times a
  refusal the first call left behind;
* the priced pass list reads exactly the viewer's own gestures;
* the return takes back both records — the answer the deck's rule reads and the row that remembers
  the card was shown — and answers with the list that is left;
* a second return of the same pass refuses, and the refusal is not what the row prices;
* the measured window of the return carries its two `DELETE`s and the page reads, and writes
  nothing else;
* and the published table carries both rows, because a document reporting a number the instrument
  cannot reproduce is the defect stage 72-9 already caught in the release checklist.
"""

from __future__ import annotations

import importlib.util
import inspect
import pathlib
import re
import uuid

from httpx import AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.exceptions import NotFoundError
from app.models import User

from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)

_PROBE_PATH = pathlib.Path(__file__).resolve().parents[1] / "ops" / "scale_probe.py"
_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCALE_DOC = _ROOT / "docs" / "SCALE_PLAN.md"


def _probe():
    """Load the stand as a module: it is a script, so it is not on the import path."""
    spec = importlib.util.spec_from_file_location("scale_probe", _PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _account(client: AsyncClient, tag: str, *, name: str = "Вера") -> dict:
    creds = await register_and_auth(client, f"s115_{tag}@befos.app")
    await complete_onboarding(client, creds["token"], name=name)
    await answer_all_questions(client, creds["token"])
    return creds


async def _pass(client: AsyncClient, creds: dict, target_id: str) -> None:
    resp = await client.post(
        f"/api/v1/users/{target_id}/pass", headers=auth_headers(creds["token"])
    )
    assert resp.status_code == 200, resp.text


async def _viewer_row(user_id) -> "User":
    """The viewer as `_context()` holds it: read once, outside the measured window."""
    row = None
    async with AsyncSessionLocal() as fresh:
        row = await fresh.get(User, uuid.UUID(str(user_id)))
    assert row is not None, f"no account {user_id} to price the pass doors for"
    return row


def test_the_stand_carries_a_path_for_the_pass_list_and_its_return() -> None:
    paths = _probe()._build_paths()
    assert "passed" in paths, (
        "the hot-path harness has no row for `GET /discover/passed`, so the list stage 114 opened "
        "is priced by nobody while its neighbour in the same flow — the inbox — has carried a row "
        "in the same table since stage 113"
    )
    assert "unpass" in paths, (
        "the harness has no row for `DELETE /users/{id}/pass`: the return is the only gesture in "
        "the app that releases the deck's memory, and its price at 50 000 is exactly the number "
        "the open end of stage 114 left unmeasured"
    )


def test_the_pass_list_reads_rows_the_stand_already_writes_and_seeds_nothing_in_its_window() -> None:
    body = inspect.getsource(_probe()._build_paths()["passed"]).lower()
    assert "insert into" not in body, (
        "the pass-list path builds its own crowd inside the timed call: stage 42 already caught "
        f"this for the deck, and at 50 000 a seed dwarfs everything the page itself does: {body}"
    )
    seed = inspect.getsource(_probe()._seed_activity)
    assert "INSERT INTO passes" in seed, (
        "the premise of pricing the pass list without a setup is that `_seed_activity` writes the "
        "viewer's own passes (40 % of the stand); if that ever stops being true, the row must "
        "gain a setup like the inbox did, not silently price an empty list"
    )


def test_the_pass_path_calls_the_handler_the_api_dispatches() -> None:
    from app.api.v1 import discover as discover_module
    from app.main import app

    mounted = [
        route.endpoint
        for route in app.routes
        if getattr(route, "path", "").endswith("/discover/passed")
    ]
    assert mounted, "the pass-list route is not mounted, so there is nothing for the harness to price"
    assert mounted[0] is discover_module.passed_users, (
        "the mounted endpoint is not the function the harness calls: the published number would "
        "belong to a different handler than the one the app answers with"
    )

    body = inspect.getsource(_probe()._build_paths()["passed"])
    assert (
        "passed_users_route(" in body
        and "from app.api.v1.discover import passed_users" in body
    ), (
        "the harness prices a copy of the route's steps rather than the route, so a change inside "
        f"the handler moves the product without moving the number: {body}"
    )
    assert 'ctx["viewer_user"]' in body, (
        "the wrapper resolves the reader inside its own window: stage 78 moved this read out — "
        "the dependency hands the row over before the handler runs, and pricing the token's "
        f"owner as part of the screen repeats that mistake: {body}"
    )


def test_the_return_path_calls_the_handler_and_never_undoes_the_same_pass_twice() -> None:
    from app.api.v1 import discover as discover_module
    from app.main import app

    # The same URL carries the deck's gesture (POST) and this one's return (DELETE): only the
    # method tells them apart, so a path-only filter would price the wrong handler.
    mounted = [
        route.endpoint
        for route in app.routes
        if getattr(route, "path", "").endswith("/users/{user_id}/pass")
        and "DELETE" in getattr(route, "methods", set())
    ]
    assert mounted, "the return route is not mounted, so there is nothing for the harness to price"
    assert mounted[0] is discover_module.undo_pass, (
        "the mounted DELETE endpoint is not the function the harness calls"
    )

    body = inspect.getsource(_probe()._build_paths()["unpass"])
    assert "undo_pass_route(" in body and "from app.api.v1.discover import undo_pass" in body, (
        "the harness prices a copy of the route's steps rather than the route: " + body
    )
    assert 'ctx["unpass_peers"]' in body and "unpass_turn" in body, (
        "the return repeats its target: the second undo of one pass answers 404 and writes "
        f"nothing, so a static target would time a refusal after the first call — rotate fresh "
        f"targets the way the `like` path does: {body}"
    )
    assert 'ctx["viewer_user"]' in body, (
        "the wrapper resolves the reader inside its own window: " + body
    )


def test_the_context_addresses_the_pool_from_the_viewers_own_passes() -> None:
    source = inspect.getsource(_probe()._context)
    assert "FROM passes" in source and "unpass_peers" in source, (
        "the context builds no pool of the viewer's own passes: the return path would have to "
        "address its target from inside the measured window, and stage 42 named where that road "
        f"leads: {source}"
    )


async def test_the_priced_pass_list_reads_the_viewers_own_passes(client: AsyncClient) -> None:
    viewer = await _account(client, "s115_viewer", name="Женя")
    passed_one = await _account(client, "s115_pass1", name="Аня")
    passed_two = await _account(client, "s115_pass2", name="Боря")
    untouched = await _account(client, "s115_free", name="Вера")

    await _pass(client, viewer, passed_one["user_id"])
    await _pass(client, viewer, passed_two["user_id"])

    async with AsyncSessionLocal() as session:
        out = await _probe()._build_paths()["passed"](
            session, {"viewer_user": await _viewer_row(viewer["user_id"])}
        )
    named = {card.user_id for card in out.passed}
    assert named == {passed_one["user_id"], passed_two["user_id"]}, (
        "the priced page is not the door's page: it must carry exactly the viewer's own gestures, "
        f"and nobody who was never passed on: {named}"
    )
    assert untouched["user_id"] not in named
    assert out.has_more is False


async def test_the_return_takes_back_both_records_and_answers_with_the_list_left(
    client: AsyncClient,
) -> None:
    viewer = await _account(client, "s115_undo_viewer", name="Женя")
    target = await _account(client, "s115_undo_target", name="Аня")
    await _pass(client, viewer, target["user_id"])

    ctx = {
        "viewer_user": await _viewer_row(viewer["user_id"]),
        "unpass_peers": [uuid.UUID(target["user_id"])],
        "unpass_turn": 0,
    }
    async with AsyncSessionLocal() as session:
        out = await _probe()._build_paths()["unpass"](session, ctx)
    assert [card.user_id for card in out.passed] == [], (
        "the return answered with the pass still on its list: the page it publishes is the list "
        f"the server actually holds: {out.passed}"
    )

    async with AsyncSessionLocal() as session:
        left = await session.scalar(
            text("SELECT count(*) FROM passes WHERE from_user_id = :v AND to_user_id = :t"),
            {"v": uuid.UUID(viewer["user_id"]), "t": uuid.UUID(target["user_id"])},
        )
    assert left == 0, "the answer the deck's rule reads survived its own undo"

    # The same gesture again must refuse — this is precisely why the path rotates targets.
    import pytest

    with pytest.raises(NotFoundError):
        async with AsyncSessionLocal() as session:
            await _probe()._build_paths()["unpass"](session, ctx)


async def test_the_return_window_carries_its_two_deletes_and_the_page_it_answers(
    client: AsyncClient, session: AsyncSession
) -> None:
    viewer = await _account(client, "s115_window_viewer", name="Женя")
    target = await _account(client, "s115_window_target", name="Аня")
    kept = await _account(client, "s115_window_kept", name="Боря")
    await _pass(client, viewer, target["user_id"])
    # A second pass stays: undoing the only one would answer an empty page, whose card and photo
    # reads never run — the window would price a cheaper page than the stand's viewer ever sees.
    await _pass(client, viewer, kept["user_id"])

    statements: list[str] = []

    def before(conn, cursor, stmt, parameters, context, executemany):
        statements.append(" ".join(stmt.lower().split()))

    engine = session.sync_session.get_bind()
    event.listen(engine, "before_cursor_execute", before)
    try:
        out = await _probe()._build_paths()["unpass"](
            session,
            {
                "viewer_user": await _viewer_row(viewer["user_id"]),
                "unpass_peers": [uuid.UUID(target["user_id"]), uuid.UUID(kept["user_id"])],
                "unpass_turn": 0,
            },
        )
    finally:
        event.remove(engine, "before_cursor_execute", before)

    assert [card.user_id for card in out.passed] == [kept["user_id"]]
    joined = "\n".join(statements)
    for marker in (
        "delete from passes",
        "delete from discovery_queue",
        "from profiles",
        "from photos",
    ):
        assert marker in joined, (
            f"the measured return never paid `{marker}`, so the published row would price a "
            f"different gesture than the route performs. Statements in the window:\n{joined}"
        )
    inserts = [s for s in statements if s.lstrip().startswith("insert")]
    assert not inserts, (
        f"the return invented rows inside its own window: {inserts}"
    )


def test_the_published_latency_table_carries_rows_for_both_doors() -> None:
    doc = _SCALE_DOC.read_text(encoding="utf-8")
    parts = doc.split("## Задержки горячих путей", 1)
    assert len(parts) == 2, "docs/SCALE_PLAN.md no longer carries the hot-path table"
    table = parts[1].split("\n### ", 1)[0]
    for name in ("passed", "unpass"):
        row = re.search(rf"^\|\s*`{name}`\s*\|(.+)$", table, re.MULTILINE)
        assert row, (
            f"the harness prices `{name}` but the published table has no row for it: the document "
            "is the half of the rule that turns a run into a claim, and without the row the open "
            "end of stage 114 — «Цена passed/unpass прибором не меряна» — stays open"
        )
        cells = [cell.strip() for cell in row.group(1).split("|") if cell.strip()]
        assert len(cells) == 3, f"a latency row carries one cell per scale, this one carries {cells}"
        for cell in cells:
            assert re.fullmatch(r"\d+(?:[.,]\d+)? / \d+(?:[.,]\d+)? / \d+(?:\.\d+)?", cell), (
                f"`{cell}` is not the published shape медиана / максимум / число запросов"
            )
