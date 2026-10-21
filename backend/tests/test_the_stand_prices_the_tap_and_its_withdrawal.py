"""The two doors stage 116 opened left the stand without a price, and its own open end said so.

`CHANGELOG.md` and `docs/API.md` recorded the gap at the closing of stage 116: the latency table of
`docs/SCALE_PLAN.md` names nineteen paths, and neither `GET /api/v1/discover/liked` nor
`DELETE /api/v1/users/{id}/like` is among them — the tap that sits on the deck has carried a row
since stage 26, its read carries one since stage 28, yet the account's own list of taps and the
withdrawal of one of them are priced by nobody.

The instrument cannot simply be pointed at the two doors, for the same two reasons stage 113 and
stage 115 each had to learn: the read needs the viewer's own `likes` rows, and every social row the
stand writes about the viewer points outward only through the timed `like` path — so a path without
a setup would publish the price of an empty list as the price of the page. And the withdrawal
consumes what it prices: the second undo of one tap answers 404 and writes nothing, so the target
must rotate over a pool of the viewer's own taps addressed outside every measured window, the way
`unpass` rotates over the viewer's own passes.

Eleven checks, in the order the risk sits:

* the harness has a path for the list of one's own taps and for its withdrawal, and both doors own
  a setup besides their row;
* the read path builds no crowd inside the timed call — the promise stage 42 made for the deck;
* the setup writes the viewer's direction (`from_user_id`), deletes the pass row a real tap deletes
  (stage 26), and addresses the withdrawal pool outside the window from the rows it just wrote;
* both wrappers call the handlers the API dispatches, the rule stages 76 and 77 each had to
  re-learn, and take the reader from the context the way the auth dependency hands it over;
* the withdrawal rotates a fresh target per run, so no repeat times a refusal the first call left;
* the priced list carries exactly the viewer's own taps — an incoming tap stays out of it;
* the withdrawal answers with the list the server actually holds, removes only the author's half,
  and leaves the tap the other person made standing;
* a second withdrawal of the same tap refuses, and the refusal is not what the row prices;
* the measured window of the withdrawal carries its one `DELETE`, the pair lock and the page reads,
  writes no rows, and touches no second direction;
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
    creds = await register_and_auth(client, f"s117_{tag}@befos.app")
    await complete_onboarding(client, creds["token"], name=name)
    await answer_all_questions(client, creds["token"])
    return creds


async def _tap(client: AsyncClient, creds: dict, target_id: str) -> None:
    resp = await client.post(
        f"/api/v1/users/{target_id}/like", headers=auth_headers(creds["token"])
    )
    assert resp.status_code == 200, resp.text


async def _viewer_row(user_id) -> "User":
    """The viewer as `_context()` holds it: read once, outside the measured window."""
    row = None
    async with AsyncSessionLocal() as fresh:
        row = await fresh.get(User, uuid.UUID(str(user_id)))
    assert row is not None, f"no account {user_id} to price the tap doors for"
    return row


def test_the_stand_carries_a_path_for_the_tap_list_and_its_withdrawal() -> None:
    paths = _probe()._build_paths()
    assert "liked" in paths, (
        "the hot-path harness has no row for `GET /discover/liked`, so the list stage 116 opened "
        "is priced by nobody while its mirror — the inbox — has carried a row since stage 113"
    )
    assert "unlike" in paths, (
        "the harness has no row for `DELETE /users/{id}/like`: the withdrawal is the answer the "
        "stage 115 open end named — «обратный ход у касания остаётся пробелом» — and at 50 000 "
        "its price is still the number the document owes its reader"
    )
    setups = _probe()._build_setups()
    assert "liked" in setups and "unlike" in setups, (
        "one of the two doors has no setup: unlike `passed`, whose rows `_seed_activity` has written "
        "since stage 20, the viewer's own taps are written by nobody outside the timed `like` path, "
        "so a path shot as-is would price an empty list"
    )


def test_the_tap_list_reads_rows_the_stand_writes_outside_its_window() -> None:
    body = inspect.getsource(_probe()._build_paths()["liked"]).lower()
    assert "insert into" not in body, (
        "the tap-list path builds its own crowd inside the timed call: stage 42 already caught this "
        f"for the deck, and at 50 000 a seed dwarfs everything the page itself does: {body}"
    )


def test_the_own_taps_seed_writes_the_viewers_direction_and_keeps_the_pairs_state_true() -> None:
    seed = inspect.getsource(_probe()._build_setups()["liked"])
    assert "INSERT INTO likes" in seed, (
        "the setup behind the tap list writes no likes rows, so the priced page would be an empty "
        f"box: {seed}"
    )
    assert re.search(r"from_user_id[^:]*:\s*viewer|:viewer\s+AS\s+from_user_id|from_user_id,\s*to_user_id[^;]*\n?\s*SELECT[^;]*:viewer", seed, re.IGNORECASE), (
        "the seed points the taps the wrong way: the door reads `from_user_id == viewer`, an "
        f"incoming seed would price the mirror page instead: {seed}"
    )
    assert "DELETE FROM passes" in seed, (
        "the seed taps without clearing a pass row the way stage 26 makes a real tap do, so the "
        "priced state would hold a pair that both passed and tapped — a state no screen can reach: "
        f"{seed}"
    )


def test_the_withdrawal_pool_is_addressed_outside_the_window() -> None:
    seed = inspect.getsource(_probe()._build_setups()["unlike"])
    assert "unlike_peers" in seed and "FROM likes" in seed, (
        "the withdrawal pool is not built from the viewer's own taps before the first timed call: "
        "stage 42 named where in-window pool hunting leads, and an empty pool would silently time "
        f"a refusal: {seed}"
    )


def test_the_tap_path_calls_the_handler_the_api_dispatches() -> None:
    source = inspect.getsource(_probe()._build_paths()["liked"])
    assert "from app.api.v1.discover import liked_users as liked_users_route" in source, (
        "the `liked` row re-assembles the handler's steps instead of calling the handler the route "
        f"dispatches — the exact drift stages 76 and 77 each published as yesterday's number: {source}"
    )
    assert 'current_user=ctx["viewer_user"]' in source, (
        "the priced read fetches its own reader inside the window, pricing `get_current_user` as "
        "part of the page: the context already holds the row the dependency would hand over"
    )


def test_the_withdrawal_path_calls_the_handler_and_rotates_its_targets() -> None:
    source = inspect.getsource(_probe()._build_paths()["unlike"])
    assert "from app.api.v1.discover import undo_like as undo_like_route" in source, (
        "the `unlike` row prices a private re-assembly instead of the dispatched handler: "
        f"{source}"
    )
    assert 'ctx["unlike_peers"]' in source and 'ctx["unlike_turn"]' in source, (
        "the withdrawal takes a static target: the second undo of one tap answers 404 and writes "
        "nothing, so a fixed target would time a refusal after the first call and publish it as "
        f"the price of the gesture: {source}"
    )


async def test_the_priced_tap_list_reads_the_viewers_own_taps(client: AsyncClient) -> None:
    viewer = await _account(client, "s117_viewer", name="Женя")
    tapped_one = await _account(client, "s117_tap1", name="Аня")
    tapped_two = await _account(client, "s117_tap2", name="Боря")
    admirer = await _account(client, "s117_admirer", name="Вера")

    await _tap(client, viewer, tapped_one["user_id"])
    await _tap(client, viewer, tapped_two["user_id"])
    await _tap(client, admirer, viewer["user_id"])  # incoming — must stay out of the page

    async with AsyncSessionLocal() as session:
        out = await _probe()._build_paths()["liked"](
            session, {"viewer_user": await _viewer_row(viewer["user_id"])}
        )
    named = {card.user_id for card in out.likes}
    assert named == {tapped_one["user_id"], tapped_two["user_id"]}, (
        "the priced page is not the door's page: it must carry exactly the taps the viewer made, "
        f"and nobody who merely tapped at them: {named}"
    )
    assert admirer["user_id"] not in named
    assert out.has_more is False


async def test_the_withdrawal_removes_one_direction_and_answers_with_the_list_left(
    client: AsyncClient,
) -> None:
    viewer = await _account(client, "s117_undo_viewer", name="Женя")
    target = await _account(client, "s117_undo_target", name="Аня")
    kept = await _account(client, "s117_undo_kept", name="Боря")
    await _tap(client, viewer, target["user_id"])
    await _tap(client, viewer, kept["user_id"])
    # The tapped person's own tap at the viewer: the withdrawal has no say over it.
    await _tap(client, target, viewer["user_id"])

    ctx = {
        "viewer_user": await _viewer_row(viewer["user_id"]),
        "unlike_peers": [uuid.UUID(target["user_id"])],
        "unlike_turn": 0,
    }
    async with AsyncSessionLocal() as session:
        out = await _probe()._build_paths()["unlike"](session, ctx)
    assert [card.user_id for card in out.likes] == [kept["user_id"]], (
        "the withdrawal did not answer with the list the server holds after it: "
        f"{[card.user_id for card in out.likes]}"
    )

    async with AsyncSessionLocal() as session:
        own_left = await session.scalar(
            text("SELECT count(*) FROM likes WHERE from_user_id = :v AND to_user_id = :t"),
            {"v": uuid.UUID(viewer["user_id"]), "t": uuid.UUID(target["user_id"])},
        )
        theirs_left = await session.scalar(
            text("SELECT count(*) FROM likes WHERE from_user_id = :t AND to_user_id = :v"),
            {"t": uuid.UUID(target["user_id"]), "v": uuid.UUID(viewer["user_id"])},
        )
    assert own_left == 0, "the author's half of the pair survived its own withdrawal"
    assert theirs_left == 1, (
        "the withdrawal cleared the tap the other person made: a tap says nothing about the "
        "other half, and deleting it here would be a heavier action than the button promises"
    )

    import pytest

    with pytest.raises(NotFoundError):
        async with AsyncSessionLocal() as session:
            await _probe()._build_paths()["unlike"](session, ctx)


async def test_the_withdrawal_window_carries_its_one_delete_the_lock_and_the_page(
    client: AsyncClient, session: AsyncSession
) -> None:
    viewer = await _account(client, "s117_window_viewer", name="Женя")
    target = await _account(client, "s117_window_target", name="Аня")
    kept = await _account(client, "s117_window_kept", name="Боря")
    await _tap(client, viewer, target["user_id"])
    await _tap(client, viewer, kept["user_id"])

    statements: list[str] = []

    def before(conn, cursor, stmt, parameters, context, executemany):
        statements.append(" ".join(stmt.lower().split()))

    engine = session.sync_session.get_bind()
    event.listen(engine, "before_cursor_execute", before)
    try:
        out = await _probe()._build_paths()["unlike"](
            session,
            {
                "viewer_user": await _viewer_row(viewer["user_id"]),
                "unlike_peers": [uuid.UUID(target["user_id"]), uuid.UUID(kept["user_id"])],
                "unlike_turn": 0,
            },
        )
    finally:
        event.remove(engine, "before_cursor_execute", before)

    assert [card.user_id for card in out.likes] == [kept["user_id"]]
    joined = "\n".join(statements)
    for marker in (
        "delete from likes",
        "pg_advisory_xact_lock",
        "from profiles",
        "from photos",
    ):
        assert marker in joined, (
            f"the measured withdrawal never paid `{marker}`, so the published row would price a "
            f"different gesture than the route performs. Statements in the window:\n{joined}"
        )
    deletes = [s for s in statements if s.lstrip().startswith("delete from likes")]
    assert len(deletes) == 1, (
        "the withdrawal cleared more than one likes row — only the author's direction is its to "
        f"take: {deletes}"
    )
    assert not [s for s in statements if s.lstrip().startswith("insert")], (
        "the withdrawal invented rows inside its own window"
    )


def test_the_published_latency_table_carries_rows_for_both_doors() -> None:
    doc = _SCALE_DOC.read_text(encoding="utf-8")
    parts = doc.split("## Задержки горячих путей", 1)
    assert len(parts) == 2, "docs/SCALE_PLAN.md no longer carries the hot-path table"
    table = parts[1].split("\n### ", 1)[0]
    for name in ("liked", "unlike"):
        row = re.search(rf"^\|\s*`{name}`\s*\|(.+)$", table, re.MULTILINE)
        assert row, (
            f"the harness prices `{name}` but the published table has no row for it: the document "
            "is the half of the rule that turns a run into a claim, and without the row the open "
            f"end of stage 116 — «цена liked/unlike прибором не меряна» — stays open"
        )
        cells = [cell.strip() for cell in row.group(1).split("|") if cell.strip()]
        assert len(cells) == 3, f"a latency row carries one cell per scale, this one carries {cells}"
        for cell in cells:
            assert re.fullmatch(r"\d+(?:[.,]\d+)? / \d+(?:[.,]\d+)? / \d+(?:\.\d+)?", cell), (
                f"`{cell}` is not the published shape медиана / максимум / число запросов"
            )
