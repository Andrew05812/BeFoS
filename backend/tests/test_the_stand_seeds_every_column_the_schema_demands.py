"""The stand seeds its crowd with plain SQL, and the schema has been allowed to grow under it.

Every row of the stand's population arrives through `INSERT INTO … SELECT` statements written out
in `backend/ops/scale_probe.py`, not through the ORM. A ORM insert carries the model's Python
defaults, so a stage that adds a required column and gives it a default in the model can merge with
green CI, a green suite and a stand that no longer builds its own database: the migration adds the
column NOT NULL, drops the `server_default` it needed to backfill, and the seed's column list stays
behind. Nothing runs the seed in CI, so nothing notices until somebody actually shoots the table.

Measured, not inherited: `--sizes 1000 --runs 2 --paths liked_me` on 2026-10-20 at 08:19:34…08:19:42
UTC died inside `_seed` with `asyncpg.exceptions.NotNullViolationError: null value in column
"is_moderator" of relation "users" violates not-null constraint` — the column stage 103 added and
whose `server_default` its own migration drops at `b4e7d3a8c619`. The last published table was shot
before that, so the instrument had carried the defect for ten stages and had simply not been used.

Three checks: the parse finds the statements the stand really sends (a guard that reads nothing
passes on everything), every column the schema demands is named by the seed of its table, and the
demanding itself is proven on a column list held back to the shape stage 102 left.
"""

from __future__ import annotations

import pathlib
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_PROBE_PATH = pathlib.Path(__file__).resolve().parents[1] / "ops" / "scale_probe.py"

# A table the stand writes is only half-seeded if its statement never reached the parse, so the
# list below is what the next check is trusted over: the tables the harness actually populates.
SEEDED_TABLES = (
    "interests",
    "users",
    "profiles",
    "compatibility_profiles",
    "user_interests",
    "passes",
    "matches",
    "messages",
    "discovery_queue",
    "likes",
)


def _columns_written_by_the_seed() -> dict[str, set[str]]:
    """Every ``INSERT INTO <table> (<columns>)`` the harness text contains, by table.

    The scan is deliberately loose: two of the statements are built from adjacent string literals,
    so the text between the table name and its column list carries quote characters and newlines.
    Anything inside the first parentheses is then read back as identifiers only.
    """
    source = _PROBE_PATH.read_text(encoding="utf-8")
    written: dict[str, set[str]] = {}
    for match in re.finditer(r"INSERT INTO ([a-z_]+).*?\((.*?)\)", source, re.DOTALL):
        columns = set(re.findall(r"[a-z_][a-z0-9_]*", match.group(2)))
        written.setdefault(match.group(1), set()).update(columns)
    return written


async def _columns_the_schema_demands(session: AsyncSession, tables: list[str]) -> dict[str, set[str]]:
    """NOT NULL columns of these tables that the database cannot fill by itself.

    Read from the live schema rather than from the models, because the mismatch this guard exists
    for is between the seed's text and the table the stand is built to: a Python-side default is
    invisible to a raw INSERT, and an empty `column_default` is exactly what makes a column
    demanded.
    """
    rows = (
        await session.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = ANY(:tables) "
                "  AND is_nullable = 'NO' AND column_default IS NULL AND is_generated = 'NEVER'"
            ),
            {"tables": tables},
        )
    ).all()
    demanded: dict[str, set[str]] = {}
    for table, column in rows:
        demanded.setdefault(table, set()).add(column)
    return demanded


def _unnamed(demanded: dict[str, set[str]], written: dict[str, set[str]]) -> dict[str, set[str]]:
    return {
        table: sorted(columns - written.get(table, set()))
        for table, columns in demanded.items()
        if columns - written.get(table, set())
    }


def test_the_scan_finds_the_statements_the_stand_actually_sends() -> None:
    written = _columns_written_by_the_seed()
    assert set(written) >= set(SEEDED_TABLES), (
        f"the scan reads {sorted(written)} while the harness populates {list(SEEDED_TABLES)}: a "
        "table the scan misses is a table this guard would pass without ever looking at it"
    )
    assert "password_hash" in written["users"], (
        f"the users statement parsed to {sorted(written['users'])}, which is a column list and not "
        "the statement's tail — the scan would then be comparing the wrong text to the schema"
    )


async def test_the_seed_names_every_column_the_schema_demands(session: AsyncSession) -> None:
    written = _columns_written_by_the_seed()
    demanded = await _columns_the_schema_demands(session, sorted(written))
    gaps = _unnamed(demanded, written)
    assert not gaps, (
        f"the stand cannot seed its own schema: {gaps} are NOT NULL with no database default and "
        "no raw INSERT names them. The suite hides this because it builds rows through the ORM, "
        "which applies the model's Python default; the harness writes SQL, and the migration that "
        "dropped the server_default left nothing behind for it to fall back on."
    )


async def test_the_guard_fires_on_a_column_list_held_back_to_the_previous_shape(
    session: AsyncSession,
) -> None:
    """The check is not decorative: it names `users.is_moderator` for the seed as stage 102 wrote it."""
    demanded = await _columns_the_schema_demands(session, ["users"])
    as_of_stage_102 = {
        "users": {"id", "email", "password_hash", "is_active", "is_verified", "is_deleted",
                  "created_at", "updated_at"}
    }
    gaps = _unnamed(demanded, as_of_stage_102)
    assert gaps.get("users", []) == ["is_moderator"], (
        f"held back to the pre-stage-103 column list, the guard answers {gaps} — the run must catch "
        "the column that actually broke the stand, or it catches nothing"
    )
