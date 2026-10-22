"""Stage 117 left the price of its own instrument as an open end and named the pair of runs that
would answer it.

`docs/SCALE_PLAN.md` wrote, at the close of stage 117: «Не снят прогон, где подготовка касаний
идемпотентна: вторая десятая строк под рядом отзыва — следствие порядка путей, и без пары прогонов
«с нею и без неё» этот документ не может сказать, насколько подорожала от неё страница вдвое
большего списка». The doubling is not a state a user reaches. `_seed_own_taps` sizes its batch as a
tenth of the candidates *left after* its own exclusions, so when one scale calls it a second time —
through `unlike`, whose setup reuses it — the denominator has already shrunk by the first batch and
a fresh batch lands on top of it. `s117_tap_counts.json`, shot on the faithful replay of the path
order, measured what that costs the table: 90 / 897 / 4 497 taps under the row for the list against
169 / 1 701 / 8 541 under the row for withdrawing one of them. Two rows of one door pair priced two
pages of different length, and no reader can say how much of the withdrawal's price is the
withdrawal.

The target rule closes it without moving the read row: the seed counts its tenth over the crowd as
it stands before the viewer's own taps are removed, then subtracts the taps the viewer already
holds. A prototype of exactly that rule — the harness's own seeding, one throwaway database, one
scale (`s118_proto_seed.json`, 2026-10-22) — wrote 196 taps on its first call and still 196 after
its second, while the seed in the tree wrote 196 and then 372.

Seven checks, in the order the risk sits:

* the second own-taps seed of one scale writes no new taps, and clears no `passes` row;
* a tap the viewer already holds counts toward the target, so the list under the row is the target
  rather than the target plus whatever the timed `like` path left behind;
* once the crowd is large enough for its tenth to pass the floor, the tenth is the target — the
  divisor still decides, the floor only lifts a small stand;
* the withdrawal still receives its rotation pool from the shared seed, and that pool is made of
  the viewer's own taps;
* the withdrawal setup run alone (a stand shot with `--paths unlike`) still seeds a page instead of
  pricing an empty one;
* the seed's own text names the crowd as its denominator and subtracts the held taps, because a rule
  that lives only in a measurement is a rule the next edit can quietly drop;
* and the document carries the stage that shot the pair of runs the open end asked for.
"""

from __future__ import annotations

import importlib.util
import inspect
import pathlib
import re
import uuid

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.discovery_service import LIKED_SHOWN

_PROBE_PATH = pathlib.Path(__file__).resolve().parents[1] / "ops" / "scale_probe.py"
_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCALE_DOC = _ROOT / "docs" / "SCALE_PLAN.md"
CROWD_PATTERN = "s118_crowd_%@befos.test"
VIEWER_EMAIL = "s118_viewer@befos.test"
FLOOR = LIKED_SHOWN + 1


def _probe():
    """Load the stand as a module: it is a script, so it is not on the import path."""
    spec = importlib.util.spec_from_file_location("scale_probe", _PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _target(crowd: int, divisor: int) -> int:
    """The list size a seed is meant to bring the viewer's taps up to: the tenth, or the floor."""
    return max(crowd // divisor, FLOOR)


async def _crowd(session: AsyncSession, accounts: int) -> uuid.UUID:
    """Bulk-write `accounts` onboarded profiles, one viewer, and a pass row for every pair.

    The column shape is the stand's own — `_seed` writes these same ones — and the crowd is written
    here rather than borrowed because the seed under test reads nothing but `users`, `profiles`,
    `matches` and `likes`. Four accounts off the API would put every number under the floor and the
    tenth would never become visible. The pass rows are the other half of the promise: a real tap
    clears them (stage 26), so a seed that writes no new taps must also clear nothing.
    """
    await session.execute(
        text(
            """
            INSERT INTO users (id, email, password_hash, is_active, is_verified, is_deleted,
                               is_moderator, created_at, updated_at)
            SELECT gen_random_uuid(), 's118_crowd_' || g || '@befos.test', 'x',
                   true, true, false, false,
                   now() - make_interval(mins => g), now() - make_interval(mins => g)
            FROM generate_series(1, CAST(:accounts AS integer)) g
            ON CONFLICT (email) DO NOTHING
            """
        ),
        {"accounts": accounts},
    )
    await session.execute(
        text(
            """
            INSERT INTO users (id, email, password_hash, is_active, is_verified, is_deleted,
                               is_moderator, created_at, updated_at)
            VALUES (gen_random_uuid(), :email, 'x', true, true, false, false, now(), now())
            ON CONFLICT (email) DO NOTHING
            """
        ),
        {"email": VIEWER_EMAIL},
    )
    await session.execute(
        text(
            """
            INSERT INTO profiles (id, user_id, name, birth_date, gender, city, about, dating_goal,
                                  age_min, age_max, gender_preference, city_preference, lifestyle,
                                  is_hidden, created_at, updated_at, onboarding_completed_at)
            SELECT gen_random_uuid(), u.id, 'Crowd ' || split_part(u.email, '@', 1),
                   DATE '1990-01-01', 'female', 'Almaty', NULL, 'relationship',
                   18, 60, ARRAY['female', 'male'], NULL, '{}'::jsonb,
                   false, u.created_at, u.created_at, u.created_at
            FROM users u
            WHERE u.email LIKE :pattern
              AND NOT EXISTS (SELECT 1 FROM profiles p WHERE p.user_id = u.id)
            """
        ),
        {"pattern": CROWD_PATTERN},
    )
    await session.execute(
        text(
            """
            INSERT INTO profiles (id, user_id, name, birth_date, gender, city, about, dating_goal,
                                  age_min, age_max, gender_preference, city_preference, lifestyle,
                                  is_hidden, created_at, updated_at, onboarding_completed_at)
            SELECT gen_random_uuid(), u.id, 'Probe viewer', DATE '1990-04-01', 'male', 'Almaty',
                   NULL, 'relationship', 18, 60, ARRAY['female', 'male'], NULL, '{}'::jsonb,
                   false, now(), now(), now()
            FROM users u
            WHERE u.email = :email
              AND NOT EXISTS (SELECT 1 FROM profiles p WHERE p.user_id = u.id)
            """
        ),
        {"email": VIEWER_EMAIL},
    )
    viewer = uuid.UUID(
        str(
            await session.scalar(
                text("SELECT id FROM users WHERE email = :email"), {"email": VIEWER_EMAIL}
            )
        )
    )
    await session.execute(
        text(
            """
            INSERT INTO passes (id, from_user_id, to_user_id, created_at, updated_at)
            SELECT gen_random_uuid(), :viewer, u.id, now(), now()
            FROM users u WHERE u.email LIKE :pattern
            ON CONFLICT (from_user_id, to_user_id) DO NOTHING
            """
        ),
        {"viewer": viewer, "pattern": CROWD_PATTERN},
    )
    await session.commit()
    return viewer


async def _taps(session: AsyncSession, viewer: uuid.UUID) -> int:
    return await session.scalar(
        text("SELECT count(*) FROM likes WHERE from_user_id = :v"), {"v": viewer}
    )


async def _pass_rows(session: AsyncSession, viewer: uuid.UUID) -> int:
    return await session.scalar(
        text("SELECT count(*) FROM passes WHERE from_user_id = :v"), {"v": viewer}
    )


async def _tap_targets(session: AsyncSession, viewer: uuid.UUID) -> set[str]:
    rows = (
        await session.execute(
            text("SELECT to_user_id FROM likes WHERE from_user_id = :v"), {"v": viewer}
        )
    ).scalars().all()
    return {str(row) for row in rows}


async def _hold_taps(session: AsyncSession, viewer: uuid.UUID, how_many: int) -> None:
    """Taps the viewer holds before the seed runs — what the timed `like` path leaves behind."""
    await session.execute(
        text(
            """
            INSERT INTO likes (id, from_user_id, to_user_id, compatibility_score,
                               created_at, updated_at)
            SELECT gen_random_uuid(), :viewer, u.id, 0.71, now(), now()
            FROM users u WHERE u.email LIKE :pattern ORDER BY u.email LIMIT CAST(:n AS integer)
            """
        ),
        {"viewer": viewer, "pattern": CROWD_PATTERN, "n": how_many},
    )
    await session.commit()


async def test_the_second_own_taps_seed_writes_no_new_taps(
    client: AsyncClient, session: AsyncSession
) -> None:
    probe = _probe()
    viewer = await _crowd(session, 200)
    ctx: dict = {"viewer_id": viewer}

    await probe._build_setups()["liked"](session, ctx)
    after_read = await _taps(session, viewer)
    await probe._build_setups()["unlike"](session, ctx)
    after_return = await _taps(session, viewer)

    assert after_return == after_read, (
        "the second own-taps seed of one scale wrote more taps, so the row for the withdrawal is "
        "priced on a longer page than the row for the list: stage 117 measured that gap on the "
        "replayed path order — 90 taps against 169 at 1 000, 897 against 1 701 at 10 000, 4 497 "
        f"against 8 541 at 50 000 (`s117_tap_counts.json`). This fixture: {after_read} then "
        f"{after_return}"
    )


async def test_the_second_own_taps_seed_clears_no_pass_rows(
    client: AsyncClient, session: AsyncSession
) -> None:
    probe = _probe()
    viewer = await _crowd(session, 200)
    ctx: dict = {"viewer_id": viewer}

    await probe._build_setups()["liked"](session, ctx)
    after_read = await _pass_rows(session, viewer)
    await probe._build_setups()["unlike"](session, ctx)
    after_return = await _pass_rows(session, viewer)

    assert after_return == after_read, (
        "the seed behind the withdrawal cleared pass rows for taps it should never have written: "
        "each of them takes a row away from the `passed` and `unpass` rows of the same table, and "
        "that is how 400 seeded passes came to price those rows at 234. Here: "
        f"{after_read} then {after_return}"
    )


async def test_a_tap_the_viewer_already_holds_counts_toward_the_target(
    client: AsyncClient, session: AsyncSession
) -> None:
    probe = _probe()
    viewer = await _crowd(session, 200)
    await _hold_taps(session, viewer, 3)
    ctx: dict = {"viewer_id": viewer}

    await probe._build_setups()["liked"](session, ctx)
    held = await _taps(session, viewer)

    assert held == _target(200, probe.LIKED_TAPS_DIVISOR), (
        "the list under the read row is the target plus the taps the viewer came in with: the timed "
        "`like` path writes rows in the same direction the seed fills, so a seed that ignores them "
        f"prices a page longer than any account of this size holds. Target "
        f"{_target(200, probe.LIKED_TAPS_DIVISOR)}, 3 held before, {held} after the seed"
    )


async def test_the_tenth_of_the_crowd_is_the_target_once_the_floor_is_behind_it(
    client: AsyncClient, session: AsyncSession
) -> None:
    probe = _probe()
    viewer = await _crowd(session, 700)
    ctx: dict = {"viewer_id": viewer}

    await probe._build_setups()["liked"](session, ctx)
    after_read = await _taps(session, viewer)
    await probe._build_setups()["unlike"](session, ctx)
    after_return = await _taps(session, viewer)

    assert after_read == _target(700, probe.LIKED_TAPS_DIVISOR), (
        "the seed no longer sizes the list by the tenth of the crowd: `LIKED_TAPS_DIVISOR` is the "
        f"knob that keeps the priced page proportional to the stand, and the floor of {FLOOR} only "
        f"lifts stands below it. First call left {after_read} taps"
    )
    assert after_return == after_read, (
        "the second call wrote a fresh tenth over the crowd the first call had already tapped away: "
        "at 700 accounts the row for the withdrawal prices "
        f"{after_return} taps while the row for the list prices {after_read}"
    )


async def test_the_withdrawal_still_gets_its_pool_from_the_shared_seed(
    client: AsyncClient, session: AsyncSession
) -> None:
    probe = _probe()
    setups = probe._build_setups()
    viewer = await _crowd(session, 200)
    ctx: dict = {"viewer_id": viewer}

    await setups["liked"](session, ctx)
    await setups["unlike"](session, ctx)

    pool = [str(peer) for peer in ctx["unlike_peers"]]
    assert pool, (
        "the withdrawal arrived with no target: an empty pool turns every timed call into the 404 "
        "the door answers for a tap it does not hold, and the row would publish that refusal as the "
        "price of the gesture"
    )
    assert set(pool) <= await _tap_targets(session, viewer), (
        "the withdrawal rotates over targets that are not the viewer's own taps — undoing somebody "
        f"else's tap prices a refusal, not the button: {pool[:3]}"
    )


async def test_the_withdrawal_setup_alone_still_seeds_the_page_it_prices(
    client: AsyncClient, session: AsyncSession
) -> None:
    probe = _probe()
    viewer = await _crowd(session, 200)
    ctx: dict = {"viewer_id": viewer}

    await probe._build_setups()["unlike"](session, ctx)
    seeded = await _taps(session, viewer)

    assert seeded == _target(200, probe.LIKED_TAPS_DIVISOR), (
        "the withdrawal setup stopped seeding for a reader that never ran: a stand shot with "
        f"`--paths unlike` has no earlier own-taps setup, and an empty list under that row prices a "
        f"refusal again. Seeded {seeded}, target {_target(200, probe.LIKED_TAPS_DIVISOR)}"
    )
    assert ctx["unlike_peers"], "the stand shot alone left the withdrawal without a target"


def test_the_seed_names_its_denominator_before_the_exclusions() -> None:
    source = inspect.getsource(_probe()._build_setups()["liked"])
    assert re.search(r"WITH crowd AS", source), (
        "the seed lost the crowd whose tenth it fills: sized against the candidates left after the "
        "viewer's own taps are removed, every call writes a tenth of what remains on top of the "
        f"batch before it: {source[:300]}"
    )
    assert re.search(r"already AS", source) and re.search(
        r"GREATEST\(\s*pool\.total / :divisor,\s*:floor\s*\)\s*-\s*already\.n", source
    ), (
        "the seed no longer subtracts the taps the viewer already holds, so its second call of a "
        "scale writes a fresh batch and the two rows of one door pair price two page lengths: "
        f"{source[:300]}"
    )


def test_the_scale_document_carries_the_pair_of_runs_the_open_end_asked_for() -> None:
    doc = _SCALE_DOC.read_text(encoding="utf-8")
    assert re.search(r"^### Стадия 118[^\n]*$", doc, re.MULTILINE), (
        "docs/SCALE_PLAN.md has no section for the stage that re-shot the table on an idempotent "
        "tap seed: the open end stage 117 named — «без пары прогонов «с нею и без неё» этот "
        "документ не может сказать, насколько подорожала от неё страница вдвое большего списка» — "
        "stays open while both rows of the door pair sit in the live table"
    )
    live = doc.split("## Задержки горячих путей", 1)[1].split("\n### ", 1)[0]
    rows = re.findall(r"^\|\s*`([a-z_]+)`\s*\|(.+)$", live, re.MULTILINE)
    assert len(rows) == 21, (
        f"the live table carries {len(rows)} rows; the harness prices 21 paths, and a table "
        "re-shot for an idempotent seed owes every one of them a fresh number"
    )
    for name, cells in rows:
        if name in ("liked", "unlike"):
            for cell in (c.strip() for c in cells.split("|") if c.strip()):
                assert re.fullmatch(
                    r"\d+(?:[.,]\d+)? / \d+(?:[.,]\d+)? / \d+(?:\.\d+)?", cell
                ), (
                    f"`{cell}` in the `{name}` row is not the published shape медиана / максимум / "
                    "число запросов"
                )
