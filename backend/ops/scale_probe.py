"""Measure the hot read paths against a synthetic population, at several scales.

The numbers in `docs/SCALE_PLAN.md` come from this script. It creates a throwaway database
(`befos_scale`), brings it to the current schema with Alembic, fills it with a generated
population, and then drives the *real* service objects — the same classes the API calls, and for the
screens whose price lives in the route layer the handlers themselves — while timing each call. The
first call of a path is published as its own number and stays out of the median and the maximum: it
pays a warming that no repeat of the same path pays again. Every statement the path sent — reads and
writes alike — is counted into the row, and the reads among them are then replayed under
`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`, so a latency number arrives with the plan behind it.

Run from `backend/`, with the Docker Postgres of `docker-compose.yml` reachable:

    DATABASE_URL=postgresql+asyncpg://befos:befos_password@127.0.0.1:5432/befos \\
        .venv/Scripts/python.exe ops/scale_probe.py --sizes 1000,10000,50000 --json scale.json

The target database is dropped and recreated on every run, so neither the development nor the
test database is touched. This is not a substitute for production traffic. It answers one
question: which query stops scaling first, and at roughly what row count.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
MAINTENANCE_DB = os.environ.get("SCALE_MAINT_DB", "postgres")
# Every generated-account filter is `^scale_[0-9]+@befos.test$`, not a `scale_%` prefix: the
# viewer below also starts with "scale_", and counting it as one of the crowd would quieten
# the very rows the measured paths have to exclude.
VIEWER_EMAIL = "scale_probe_viewer@befos.test"
PASSWORD = "Demo12345"
DECK_SIZE = 20
# Incoming taps the inbox setup writes: one per this many accounts on the stand, with a floor of
# `LIKED_ME_SHOWN + 1` so the measured page always has a queue behind its fifty cards. A tap is
# the one social row the stand never pointed *at* the viewer before stage 113 — passes, matches
# and the `like` path all start from the viewer — so without this knob the inbox row would price
# an empty list.
LIKED_ME_TAPS_DIVISOR = 10
# Own taps the tap-list and withdrawal setups write: one per this many accounts on the stand, with a
# floor of `LIKED_SHOWN + 1` so the measured page always has a queue behind its fifty cards. The
# mirror knob of the inbox divisor: before stage 117 the stand pointed its viewer's `likes` rows
# only outward through the timed `like` path, so both doors of the own-taps row would price an
# empty list without their own seed. A target and not a batch: the seed counts the tenth over the
# crowd before the viewer's own taps leave it and subtracts the taps the viewer already holds,
# because one scale calls this seed twice — behind the row for the list and behind the row for the
# withdrawal — and the batch rule put a fresh tenth on top each time (stage 117 measured 90 taps and
# then 169 under its two rows, `s117_tap_counts.json`).
LIKED_TAPS_DIVISOR = 10
# The string the stand writes into `refresh_tokens.user_agent`. Named because the session paths
# mint rows the crowd never had, and a reader of the table has to be able to tell a session this
# harness made from a session somebody else's run left behind.
USER_AGENT = "scale-probe"
# Sessions the logout path is allowed to end. One per repeat of that path, plus room for `--runs`
# up to this: the queue is filled once, outside the window, and running dry would price a request
# the route answers without touching the table.
LOGOUT_SESSIONS = 16
# Ideas each pair of the viewer is given an arrangement for. The screen of «Наши планы» is the one
# read of the plan family the app opens by name, and until stage 119 the stand wrote no row of it at
# all: `s119_gap.json` counts 0 rows in `shared_plans`, `shared_plan_members` and
# `activity_preferences` on a scale of 1 000 that already holds 20 pairs of the viewer, and prices
# that empty box at 150.4 мс over 41 statements. One arrangement per pair is the state a pair that
# arranged something keeps after its two taps; the axis this row moves on is the number of pairs,
# because `PlanService.list_for_viewer` walks them and no route of the family puts a ceiling on the
# walk — the same shape stage 49 measured for `GET /matches`.
PLANS_PER_PAIR = 1
# Arrangements the two writing doors of the plan family are given to work on, each. The hour door
# moves an evening the pair stands on; the answer door closes the evening the other half named. One
# scale calls this seed twice — once behind each row — and a queue drained by the first door's repeats
# would leave the second with a plan it had already moved, so the pool is split in half: the front
# half is what the move door taps, the back half is what the partner is asked about. Four per door is
# room for `--runs` up to four; the smallest scale the stand shoots holds 20 pairs of the viewer.
HOUR_ARRANGEMENTS = 4
# Rows the file of one account is priced on. The stand writes no photograph, no complaint and no
# block for the viewer — `_seed_activity` gives them passes, pairs and a chat, the tap seeds give
# likes — so the three sections of the document that read those tables would price an empty box,
# which is the mistake stage 113 met on the inbox and stage 119 met on the plans screen. The
# numbers are a rule of the harness, not of the scale: the file is measured as the account a person
# actually leaves with, and a heavy account has a handful of photographs and a complaint or two,
# while the columns that do grow with the crowd — passes, taps, pairs, the queue — grow on their own.
EXPORT_PHOTOS = 6
EXPORT_COMPLAINTS = 3
EXPORT_BLOCKS = 4

CITIES = ["Almaty", "Astana", "Shymkent", "Karaganda", "Aktau"]
GOALS = ["relationship", "marriage", "casual", "friendship", "networking"]
INTEREST_ROWS = [
    ("cinema", "Кино", "culture"),
    ("travel", "Путешествия", "lifestyle"),
    ("cooking", "Готовка", "lifestyle"),
    ("running", "Бег", "sport"),
    ("hiking", "Походы", "sport"),
    ("music", "Музыка", "culture"),
    ("games", "Игры", "home"),
    ("reading", "Книги", "culture"),
]

# The vector shape is what the engine reads, and the values stay inside 0..1 like a real
# questionnaire leaves them, but these ten keys are the instrument's own: seven of them (closeness,
# space, homebody, outdoors, health, routine, and stability hanging off personality) are not
# declared by app/compatibility/traits.py. `_trait_similarity` divides over whatever keys the two
# vectors share, so a stand pair is scored on those seven, and `_trait_label` has no Russian word
# for them — it hands back the slug. The answer-path guard of stage 69 reaches none of this: these
# rows are written by seeding, not by `POST /tests/answers`.
_VECTOR = """
    jsonb_build_object(
      'values', jsonb_build_object('family', 0.1 + (p.n % 9) / 10.0, 'career', 0.1 + ((p.n + 3) % 9) / 10.0),
      'personality', jsonb_build_object('openness', 0.1 + (p.n % 9) / 10.0, 'stability', 0.1 + ((p.n + 2) % 9) / 10.0),
      'communication', jsonb_build_object('closeness', 0.1 + (p.n % 9) / 10.0, 'space', 0.1 + ((p.n + 4) % 9) / 10.0),
      'lifestyle', jsonb_build_object('health', 0.1 + ((p.n + 1) % 9) / 10.0, 'routine', 0.1 + ((p.n + 6) % 9) / 10.0),
      'leisure', jsonb_build_object('outdoors', 0.1 + (p.n % 9) / 10.0, 'homebody', 0.1 + ((p.n + 5) % 9) / 10.0)
    )
"""


def _sqlalchemy_url(database: str) -> str:
    return urlsplit(os.environ["DATABASE_URL"])._replace(path=f"/{database}").geturl()


def _asyncpg_dsn(database: str) -> str:
    parts = urlsplit(_sqlalchemy_url(database))
    return (
        f"postgresql://{parts.username}:{parts.password}@{parts.hostname}:{parts.port}"
        f"/{parts.path.lstrip('/')}"
    )


async def _recreate_database(asyncpg, database: str) -> None:
    conn = await asyncpg.connect(dsn=_asyncpg_dsn(MAINTENANCE_DB))
    try:
        if await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", database):
            await conn.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{database}"')
    finally:
        await conn.close()


def _upgrade_schema(database: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=dict(os.environ, DATABASE_URL=_sqlalchemy_url(database)),
        check=True,
        capture_output=True,
    )


async def _seed(asyncpg, database: str, size: int, password_hash: str) -> dict:
    """Bulk-populate one viewer plus `size` onboarded accounts, all through plain SQL."""
    conn = await asyncpg.connect(dsn=_asyncpg_dsn(database))
    try:
        values = ", ".join(f"('{slug}', '{name}', '{category}')" for slug, name, category in INTEREST_ROWS)
        await conn.execute(
            f"INSERT INTO interests (slug, name, category) VALUES {values} ON CONFLICT (slug) DO NOTHING"
        )

        await conn.execute(
            """
            INSERT INTO users (id, email, password_hash, is_active, is_verified, is_deleted, is_moderator, created_at, updated_at)
            SELECT gen_random_uuid(), 'scale_' || g || '@befos.test', $1::text,
                   true, true, false, false, now() - make_interval(mins => g), now() - make_interval(mins => g)
            FROM generate_series(1, $2::int) g
            ON CONFLICT DO NOTHING
            """,
            password_hash,
            size,
        )
        await conn.execute(
            """
            INSERT INTO users (id, email, password_hash, is_active, is_verified, is_deleted, is_moderator, created_at, updated_at)
            VALUES (gen_random_uuid(), $1, $2, true, true, false, false, now(), now())
            ON CONFLICT (email) DO NOTHING
            """,
            VIEWER_EMAIL,
            password_hash,
        )

        await conn.execute(
            """
            INSERT INTO profiles (id, user_id, name, birth_date, gender, city, about, dating_goal,
                                  age_min, age_max, gender_preference, city_preference, lifestyle,
                                  is_hidden, created_at, updated_at, onboarding_completed_at)
            SELECT gen_random_uuid(), s.id, 'Scale ' || s.n,
                   DATE '1988-01-01' + ((s.n * 11) % 6570)::int,
                   CASE WHEN s.n % 2 = 0 THEN 'female' ELSE 'male' END,
                   ($1::text[])[(s.n % 5)::int + 1],
                   NULL, ($2::text[])[(s.n % 5)::int + 1],
                   18, 60, ARRAY['female', 'male'], NULL, '{}'::jsonb,
                   false, s.created_at, s.created_at, s.created_at
            FROM (
                SELECT u.id, u.created_at, row_number() OVER (ORDER BY u.email) AS n
                FROM users u
                WHERE u.email ~ '^scale_[0-9]+@befos.test$'
                  AND NOT EXISTS (SELECT 1 FROM profiles p WHERE p.user_id = u.id)
            ) s
            """,
            CITIES,
            GOALS,
        )
        await conn.execute(
            """
            INSERT INTO profiles (id, user_id, name, birth_date, gender, city, about, dating_goal,
                                  age_min, age_max, gender_preference, city_preference, lifestyle,
                                  is_hidden, created_at, updated_at, onboarding_completed_at)
            SELECT gen_random_uuid(), u.id, 'Probe viewer', DATE '1990-04-01', 'male', 'Almaty', NULL,
                   'relationship', 18, 60, ARRAY['female', 'male'], NULL, '{}'::jsonb,
                   false, now(), now(), now()
            FROM users u
            WHERE u.email = $1
              AND NOT EXISTS (SELECT 1 FROM profiles p WHERE p.user_id = u.id)
            """,
            VIEWER_EMAIL,
        )

        await conn.execute(
            """
            INSERT INTO compatibility_profiles (id, user_id, vector, version, created_at, updated_at)
            SELECT gen_random_uuid(), p.user_id,
            """
            + _VECTOR
            + """
                   , 1, now(), now()
            FROM (
                SELECT p.user_id, row_number() OVER (ORDER BY u.email) AS n
                FROM profiles p JOIN users u ON u.id = p.user_id
                WHERE u.email ~ '^scale_[0-9]+@befos.test$'
                  AND NOT EXISTS (SELECT 1 FROM compatibility_profiles cp WHERE cp.user_id = p.user_id)
            ) p
            """
        )
        await conn.execute(
            """
            INSERT INTO compatibility_profiles (id, user_id, vector, version, created_at, updated_at)
            SELECT gen_random_uuid(), u.id,
                   jsonb_build_object(
                     'values', jsonb_build_object('family', 0.4, 'career', 0.6),
                     'personality', jsonb_build_object('openness', 0.5, 'stability', 0.5),
                     'communication', jsonb_build_object('closeness', 0.5, 'space', 0.5),
                     'lifestyle', jsonb_build_object('health', 0.5, 'routine', 0.5),
                     'leisure', jsonb_build_object('outdoors', 0.5, 'homebody', 0.5)),
                   1, now(), now()
            FROM users u
            WHERE u.email = $1
              AND NOT EXISTS (SELECT 1 FROM compatibility_profiles cp WHERE cp.user_id = u.id)
            """,
            VIEWER_EMAIL,
        )

        await conn.execute(
            """
            WITH catalogue AS (SELECT array_agg(id ORDER BY id) AS ids FROM interests),
            targets AS (
                SELECT p.id AS profile_id,
                       row_number() OVER (ORDER BY u.email) AS n,
                       cardinality(c.ids) AS total
                FROM profiles p
                JOIN users u ON u.id = p.user_id
                JOIN catalogue c ON true
                WHERE u.email ~ '^scale_[0-9]+@befos.test$'
            )
            INSERT INTO user_interests (profile_id, interest_id)
            SELECT t.profile_id, c.ids[((t.n * 3 + off) % t.total) + 1]
            FROM targets t CROSS JOIN generate_series(0, 2) off JOIN catalogue c ON true
            ON CONFLICT DO NOTHING
            """
        )
        await conn.execute(
            """
            WITH catalogue AS (SELECT array_agg(id ORDER BY id) AS ids FROM interests),
            viewer AS (SELECT p.id FROM profiles p JOIN users u ON u.id = p.user_id WHERE u.email = $1)
            INSERT INTO user_interests (profile_id, interest_id)
            SELECT v.id, c.ids[off] FROM viewer v CROSS JOIN generate_series(1, 4) off JOIN catalogue c ON true
            ON CONFLICT DO NOTHING
            """,
            VIEWER_EMAIL,
        )

        summary = await conn.fetchrow(
            """
            SELECT (SELECT count(*) FROM users WHERE email ~ '^scale_[0-9]+@befos.test$') AS users,
                   (SELECT count(*) FROM profiles p JOIN users u ON u.id = p.user_id
                    WHERE u.email ~ '^scale_[0-9]+@befos.test$') AS profiles,
                   (SELECT count(*) FROM compatibility_profiles cp JOIN users u ON u.id = cp.user_id
                    WHERE u.email ~ '^scale_[0-9]+@befos.test$') AS vectors,
                   (SELECT count(*) FROM user_interests ui JOIN profiles p ON p.id = ui.profile_id
                      JOIN users u ON u.id = p.user_id
                    WHERE u.email ~ '^scale_[0-9]+@befos.test$') AS links
            """
        )
        return dict(summary or {})
    finally:
        await conn.close()


async def _seed_activity(asyncpg, database: str, acted: int, matches: int, messages: int,
                        crowd_matches: int, crowd_messages: int) -> dict:
    """Give the viewer the shape of a heavy user: `acted` passes, `matches` pairs, chat volume.

    The exclusion list is what grows with use, and the deck rebuild subtracts it on every refill;
    the match list and the chat history are read on every app start.

    `crowd_matches` pairs off people the viewer never sees, with `crowd_messages` messages each. Without
    them `messages` holds one conversation and every plan on that table reads as a sequential scan of a
    page — which says nothing about whether `ix_message_match_created` gets used once the table is large.
    """
    conn = await asyncpg.connect(dsn=_asyncpg_dsn(database))
    try:
        await conn.execute(
            """
            WITH viewer AS (SELECT id FROM users WHERE email = $1),
            targets AS (
                SELECT u.id FROM users u CROSS JOIN viewer v
                WHERE u.email ~ '^scale_[0-9]+@befos.test$'
                ORDER BY md5(u.email::text)
                LIMIT $2::int
            )
            INSERT INTO passes (id, from_user_id, to_user_id, created_at, updated_at)
            SELECT gen_random_uuid(), v.id, t.id, now(), now()
            FROM viewer v CROSS JOIN targets t
            ON CONFLICT DO NOTHING
            """,
            VIEWER_EMAIL,
            acted,
        )
        created = await conn.fetchval(
            """
            WITH viewer AS (SELECT id FROM users WHERE email = $1),
            peers AS (
                SELECT u.id, row_number() OVER () AS n FROM users u CROSS JOIN viewer v
                WHERE u.email ~ '^scale_[0-9]+@befos.test$'
                ORDER BY md5(u.email::text) DESC
                LIMIT $2::int
            ),
            ins AS (
                INSERT INTO matches (id, user_a_id, user_b_id, compatibility_score, created_at, updated_at)
                SELECT gen_random_uuid(), v.id, p.id, 0.72, now() - make_interval(mins => p.n::int), now()
                FROM viewer v CROSS JOIN peers p
                RETURNING id
            )
            SELECT count(*) FROM ins
            """,
            VIEWER_EMAIL,
            matches,
        )
        await conn.execute(
            """
            WITH newest AS (
                SELECT id, user_a_id FROM matches WHERE user_a_id = (SELECT id FROM users WHERE email = $1)
                ORDER BY created_at DESC LIMIT 1
            ),
            bodies AS (SELECT g, 'Scale message number ' || g AS body FROM generate_series(1, $2) g)
            INSERT INTO messages (id, match_id, sender_id, body, is_deleted, created_at, updated_at)
            SELECT gen_random_uuid(), m.id, m.user_a_id, b.body, false, now() - make_interval(mins => 200 - b.g), now()
            FROM newest m CROSS JOIN bodies b
            """,
            VIEWER_EMAIL,
            messages,
        )
        await conn.execute(
            """
            WITH ranked AS (
                SELECT u.id, row_number() OVER (ORDER BY md5(u.email::text)) AS n
                FROM users u
                WHERE u.email ~ '^scale_[0-9]+@befos.test$'
            ),
            picked AS (
                SELECT a.id AS a_id, b.id AS b_id
                FROM ranked a JOIN ranked b ON b.n = a.n + 1
                WHERE a.n % 2 = 1 AND a.n <= $1::int * 2
            )
            INSERT INTO matches (id, user_a_id, user_b_id, compatibility_score, created_at, updated_at)
            SELECT gen_random_uuid(), p.a_id, p.b_id, 0.55, now(), now() FROM picked p
            ON CONFLICT DO NOTHING
            """,
            crowd_matches,
        )
        await conn.execute(
            """
            WITH viewer AS (SELECT id FROM users WHERE email = $1),
            crowd AS (
                SELECT m.id, m.user_a_id, m.user_b_id
                FROM matches m JOIN users u ON u.id = m.user_a_id
                WHERE u.email ~ '^scale_[0-9]+@befos.test$' AND m.user_a_id <> (SELECT id FROM viewer)
            )
            INSERT INTO messages (id, match_id, sender_id, body, is_deleted, created_at, updated_at)
            SELECT gen_random_uuid(), c.id,
                   CASE WHEN g % 2 = 0 THEN c.user_a_id ELSE c.user_b_id END,
                   'Scale message ' || g, false,
                   now() - make_interval(mins => (600 - g)::int), now()
            FROM crowd c CROSS JOIN generate_series(1, $2::int) g
            """,
            VIEWER_EMAIL,
            crowd_messages,
        )
        return {
            "passes": acted,
            "matches": created,
            "messages": messages,
            "crowd_matches": crowd_matches,
            "crowd_messages": crowd_messages,
        }
    finally:
        await conn.close()


async def _drain_deck(session, ctx) -> None:
    """Put the viewer in the state where the deck holds nothing ready and nobody waits outside it.

    This is stand setup, not the screen's work: the queue gets a row for every account on the
    stand, marked seen. Writing it directly is what makes the last page reachable without sending
    a few thousand pages to get there — and keeping it out of the measured call is what makes the
    number of that page describe the page: at 50 000 this statement alone ran to 11 327.9 ms,
    which is the median the pre-fix harness published for the page (11 426.8 ms).
    """
    from sqlalchemy import text

    if ctx.get("deck_drained"):
        return
    ctx["deck_drained"] = True
    await session.execute(
        text(
            "INSERT INTO discovery_queue "
            "    (viewer_id, candidate_id, rank, score, status, queued_at, seen_at) "
            "SELECT :viewer, p.user_id, "
            "       (SELECT COALESCE(MAX(q.rank), -1) FROM discovery_queue q "
            "         WHERE q.viewer_id = :viewer) + row_number() OVER (ORDER BY p.user_id), "
            "       0, 'seen', now(), now() "
            "FROM profiles p JOIN users u ON u.id = p.user_id "
            "WHERE p.user_id <> :viewer AND p.onboarding_completed_at IS NOT NULL "
            "ON CONFLICT DO NOTHING"
        ),
        {"viewer": ctx["viewer_id"]},
    )
    await session.execute(
        text("UPDATE discovery_queue SET status = 'seen', seen_at = now() "
             "WHERE viewer_id = :viewer AND status = 'ready'"),
        {"viewer": ctx["viewer_id"]},
    )
    await session.commit()


async def _answer_payload(session, ctx) -> None:
    """Put the answer map a client already holds into the context, outside the measured window.

    The submission path needs a body naming every question, and the app takes that map from the
    questions screen — `GET /api/v1/tests` — one tap before it posts the answers. Reading the
    catalogue inside the timed call instead sends `SELECT test_questions …` and
    `SELECT test_options … IN ($1, …, $21)` twice in one call: once as the harness's own read and
    once as the request's, which is what made the path publish 13 запросов за вызов for a route
    that pays 11 (measured 2026-10-09 with a capture grouped by statement and parameters).
    """
    from app.repositories.test_repo import TestRepository

    if ctx.get("answer_rows") is not None:
        return
    questions = await TestRepository(session).list_active_questions()
    ctx["answer_rows"] = [
        {"question_id": q.id, "option_id": q.options[0].id} for q in questions
    ]


async def _prime_session(session, ctx) -> None:
    """Mint, outside the measured window, the one live session the rotation path redeems.

    The stand's `refresh_tokens` table was empty for every run up to stage 76: the harness wrote
    profiles, passes, matches and messages, but no session, so there was no token to present and
    the rotation could not be measured at all. One login through the service is the whole setup —
    and it has to stay outside the window, because what the screen pays is the redeem and the mint,
    not the password check that put the token there.
    """
    from app.services.auth_service import AuthService

    if ctx.get("refresh_token"):
        return
    user = await AuthService(session).authenticate(ctx["viewer_email"], PASSWORD)
    ctx["refresh_token"] = (await AuthService(session).issue_tokens(user, USER_AGENT))[
        "refresh_token"
    ]


async def _prime_sessions(session, ctx) -> None:
    """Mint the queue of sessions the logout path ends, one per repeat of that path.

    `POST /auth/logout` answers 204 whether or not the token named a session — its handler swallows
    the failure — so a queue that ran out would leave the harness timing a request the product
    answers without touching the table. The queue is filled ahead of the window for the same reason
    `_drain_deck` is: writing the sessions is stand setup, ending one is the screen's work.
    """
    from app.services.auth_service import AuthService

    if ctx.get("logout_tokens"):
        return
    user = await AuthService(session).authenticate(ctx["viewer_email"], PASSWORD)
    service = AuthService(session)
    ctx["logout_tokens"] = [
        (await service.issue_tokens(user, USER_AGENT))["refresh_token"]
        for _ in range(LOGOUT_SESSIONS)
    ]


async def _session_rows(asyncpg, database: str) -> dict:
    """How many sessions the stand actually held when these rows were shot.

    Read after the paths ran, and counted exactly rather than estimated: `pg_stat_user_tables` is
    snapshotted before the harness touches the database, so its `n_live_tup` for `refresh_tokens`
    says nothing about the rows the session paths just wrote. The number belongs in the artifact
    because the reader of a latency row for a rotation has to be able to ask how many rows the
    table held — on a stand that never minted a session, the answer used to be zero.
    """
    conn = await asyncpg.connect(dsn=_asyncpg_dsn(database))
    try:
        live = await conn.fetchval("SELECT count(*) FROM refresh_tokens WHERE revoked IS FALSE")
        total = await conn.fetchval("SELECT count(*) FROM refresh_tokens")
    finally:
        await conn.close()
    return {"total": int(total), "live": int(live), "revoked": int(total) - int(live)}


def _build_paths():
    """One wrapper per screen: each sends exactly what the mounted route sends.

    Where the route only hands the work to a service, the wrapper calls that service with the route's
    own arguments. Where the route body does something of its own — proves a membership, titles a
    slug, mints a session — the wrapper calls the handler, because stage 76 and stage 77 each found a
    re-assembled copy of a route publishing yesterday's call as today's price. The auth dependency's
    read of `users` is outside every window: the handler is what is being priced, and `ctx` carries
    the viewer the way `get_current_user` would hand it over.
    """
    from app.services.auth_service import AuthService
    from app.services.chat_service import ChatService
    from app.services.discovery_service import DiscoveryService
    from app.services.matches_service import MatchesService

    async def login(session, ctx):
        service = AuthService(session)
        user = await service.authenticate(ctx["viewer_email"], PASSWORD)
        # The mounted `POST /auth/login` answers with a session: it calls `authenticate` and then
        # `issue_tokens`, and the second of those is the INSERT into `refresh_tokens` that makes the
        # answer usable. Pricing only the first published a row of one statement per call — a
        # password check, presented as the price of signing in.
        await service.issue_tokens(user, USER_AGENT)

    async def public_profile(session, ctx):
        await DiscoveryService(session).get_public_profile(ctx["viewer_id"], ctx["peer_id"])

    async def discovery_rebuild(session, ctx):
        # `GET /discover` on a deck that holds nothing ready — the request that follows a profile
        # edit or a completed test. The edit's own `DELETE FROM discovery_queue` is not this
        # route's statement (`deck_invalidate` is called by `ProfileService` and by
        # `TestService.recompute_profile`), so it no longer sits in this window; the queue is
        # emptied between the repeats by `_empty_deck`, outside the timer, because a deck that
        # refilled on the first call would leave the second one timing a warm page.
        page = await DiscoveryService(session).feed(ctx["viewer_id"], limit=DECK_SIZE)
        ctx["cursor"] = page.get("next_cursor")

    async def discovery_page(session, ctx):
        await DiscoveryService(session).feed(ctx["viewer_id"], limit=DECK_SIZE, cursor=ctx.get("cursor"))

    async def matches_list(session, ctx):
        await MatchesService(session).list_matches(ctx["viewer_id"])

    async def match_detail(session, ctx):
        # The pair's own page, priced by the handler the route dispatches rather than by the two
        # service calls somebody believed it takes: `GET /matches/{id}` proves membership against
        # the `matches` row and derives the partner from that row, and only then asks for the card
        # `for_match_member`. Asking the deck's first letter instead published a screen of a
        # different person, in fewer statements than the screen pays.
        from app.api.v1.matches import get_match

        return await get_match(ctx["match_id"], current_user=ctx["viewer_user"], session=session)

    async def compatibility(session, ctx):
        # `GET /matches/{id}/compatibility`: the same membership proof, then the engine's answer,
        # then — only when the pair shares an interest — the read that puts Russian names on the
        # slugs the explanation carries. `explain_pair` alone leaves the last of those three out.
        from app.api.v1.matches import match_compatibility

        return await match_compatibility(
            ctx["match_id"], current_user=ctx["viewer_user"], session=session
        )

    async def chat_history(session, ctx):
        await ChatService(session).history(ctx["match_id"], ctx["viewer_id"], limit=50)

    async def recommendations(session, ctx):
        from app.services.recommendation_service import RecommendationService

        # `force` because the cached answer is one read plus one page of the catalogue, and the
        # number worth knowing is what it costs to produce the page when nothing is cached.
        await RecommendationService(session).for_match(
            ctx["match_id"], ctx["viewer_id"], force=True
        )

    async def answers_submit(session, ctx):
        from app.services.test_service import TestService

        # The whole map in one call, because that is the shape the client sends it in: the
        # app posts every answer when the last question is tapped. The map itself is filled by
        # `_answer_payload` before the window opens, because the client read it on the previous
        # screen and a second read of the catalogue here is the harness's work, not the route's.
        await TestService(session).save_answers(ctx["viewer_id"], ctx["answer_rows"])

    async def test_complete(session, ctx):
        from app.services.test_service import TestService

        # The screen after the last answer: the gate, then the same recompute the submission
        # just did. Measured on the answered-through viewer, so it costs a completion, not a
        # refusal.
        await TestService(session).complete(ctx["viewer_id"])

    async def like(session, ctx):
        from app.services.match_service import MatchService

        peers = ctx["like_peers"]
        # A fresh target per run: the tap that finds no like row yet is what a card costs the
        # first time it is swiped right, and the repeat branch skips the pass delete and the
        # match check, so measuring the same pair five times would time the second tap.
        target = peers[ctx["like_turn"] % len(peers)]
        ctx["like_turn"] += 1
        await MatchService(session).like(ctx["viewer_id"], target)

    async def deck_exhausted(session, ctx):
        from app.services.discovery_service import DiscoveryService

        await DiscoveryService(session).feed(ctx["viewer_id"], limit=DECK_SIZE)

    async def universe_map(session, ctx):
        # The pair's map is the one screen that recomputes the whole engine on every open, and it is
        # priced here by calling the handler the API dispatches rather than by re-assembling the steps
        # someone believed it takes: stage 75 changed the body of this route, and a copied harness
        # would have gone on publishing yesterday's call as today's number. The viewer comes from the
        # context, the way the auth dependency hands it over before the handler runs — reading it
        # here priced the token's owner as part of the map.
        from app.api.v1.matches import match_universe

        return await match_universe(
            ctx["match_id"], current_user=ctx["viewer_user"], session=session
        )

    async def liked_me(session, ctx):
        # The inbox stage 112 opened, priced by the handler the route dispatches: the route hands
        # the work to `DiscoveryService.liked_me` and assembles the answer into `LikedMeResponse`,
        # and re-assembling those steps here is how stage 76 and stage 77 each published yesterday's
        # call as today's number. The reader arrives the way `get_current_user` would hand it over,
        # from the context and outside the window.
        from app.api.v1.discover import liked_me as liked_me_route

        return await liked_me_route(current_user=ctx["viewer_user"], session=session)

    async def passed_list(session, ctx):
        # The list stage 114 opened, priced by the handler the route dispatches: the route hands
        # the work to `DiscoveryService.passed` and assembles the answer into
        # `PassedUsersResponse`, and re-assembling those steps here is how stage 76 and stage 77
        # each published yesterday's call as today's number. The reader comes from the context,
        # outside the window. Unlike the inbox this door needs no setup: `_seed_activity` has
        # been passing 40 % of the crowd off the viewer since stage 20, so the stand already
        # holds the page — a row shot as-is prices the real list, not an empty box.
        from app.api.v1.discover import passed_users as passed_users_route

        return await passed_users_route(current_user=ctx["viewer_user"], session=session)

    async def undo_pass(session, ctx):
        from app.api.v1.discover import undo_pass as undo_pass_route

        peers = ctx["unpass_peers"]
        # A fresh target per run, the same bargain the `like` path struck: the second return of
        # one pass answers 404 and writes nothing, so a static target would time a refusal after
        # the first call and publish it as the price of the gesture. The pool is addressed in
        # `_context`, outside every window, from the viewer's own `passes` rows; the return
        # clears them whatever the deck's filter says, so the pool needs no candidate conditions.
        target = peers[ctx["unpass_turn"] % len(peers)]
        ctx["unpass_turn"] += 1
        return await undo_pass_route(
            target, current_user=ctx["viewer_user"], session=session
        )

    async def liked_list(session, ctx):
        # The list of the viewer's own taps stage 116 opened, priced by the handler the route
        # dispatches. Unlike its mirror on the deck side this door needs a setup: every social row
        # the stand writes about the viewer points outward, so without `_seed_own_taps` the row
        # would price an empty page — stage 113 learned the same lesson on the inbox.
        #
        # `limit` and `cursor` are named here rather than left to the handler's defaults, because a
        # harness that calls a FastAPI handler directly receives the `Query(...)` descriptor instead of
        # the value it declares — and because the row the table publishes is the price of the first
        # page, which is what the device reads when it opens the screen.
        from app.api.v1.discover import liked_users as liked_users_route
        from app.services.discovery_service import LIKED_SHOWN

        return await liked_users_route(
            current_user=ctx["viewer_user"],
            session=session,
            limit=LIKED_SHOWN,
            cursor=None,
        )

    async def undo_tap(session, ctx):
        from app.api.v1.discover import undo_like as undo_like_route

        peers = ctx["unlike_peers"]
        # A fresh target per run, the bargain `unpass` struck: the second withdrawal of one tap
        # answers 404 and writes nothing, so a static target would time a refusal after the first
        # call and publish it as the price of the gesture. The pool is filled by the setup behind
        # this row — the viewer's own `likes` rows the seed just wrote — outside every window.
        target = peers[ctx["unlike_turn"] % len(peers)]
        ctx["unlike_turn"] += 1
        return await undo_like_route(
            target, current_user=ctx["viewer_user"], session=session
        )

    async def plans_screen(session, ctx):
        # The screen of «Наши планы», priced by the handler the route dispatches. The service behind
        # it walks every pair the reader is in and runs the projection once per pair, so this row is
        # a price in pairs rather than in cards shown — the shape stage 49 measured for the list of
        # pairs and for the same reason: no route of the family caps the walk. The reader arrives from
        # the context, the way `get_current_user` hands it over, and the arrangements the page shows
        # are written by `_seed_arrangements` outside the window: without that seed the row prices the
        # empty box (`s119_gap.json`: 150.4 мс, 41 statements, no plan on the stand at all).
        from app.api.v1.plans import list_plans as list_plans_route

        return await list_plans_route(current_user=ctx["viewer_user"], session=session)

    async def plan_hour_move(session, ctx):
        from app.api.v1.plans import offer_hour as offer_hour_route
        from app.schemas.schemas import MeetingTimeIn

        if not ctx.get("hour_moves"):
            raise RuntimeError(
                "the hour queue is empty: the move path needs one arrangement per repeat "
                f"(`--runs` above {HOUR_ARRANGEMENTS})"
            )
        # The pair's evening is named by whoever taps the door, and the instant comes from the queue
        # the seed filled — a tap that names the hour the plan already holds is the 18-statement,
        # writes-nothing case `s120_gap.json` measured, and it is not the door this row prices.
        plan_id, when = ctx["hour_moves"].pop(0)
        return await offer_hour_route(
            plan_id, payload=MeetingTimeIn(when=when), current_user=ctx["viewer_user"], session=session
        )

    async def plan_hour_answer(session, ctx):
        from app.api.v1.plans import confirm_hour as confirm_hour_route
        from app.schemas.schemas import MeetingTimeIn

        if not ctx.get("hour_questions"):
            raise RuntimeError(
                "the question queue is empty: the answer path needs one asked arrangement per repeat "
                f"(`--runs` above {HOUR_ARRANGEMENTS})"
            )
        # The instant the door is handed is the one the partner is asking about: this route refuses a
        # value that moved («That time is no longer the one being offered»), and the probe priced a
        # refusal at 11 statements and no writes — an answer invented here would publish that number
        # as the price of agreeing.
        plan_id, when = ctx["hour_questions"].pop(0)
        return await confirm_hour_route(
            plan_id, payload=MeetingTimeIn(when=when), current_user=ctx["viewer_user"], session=session
        )

    async def plan_card(session, ctx):
        from app.api.v1.plans import get_plan as get_plan_route

        if ctx.get("plan_id") is None:
            raise RuntimeError("no plan to open: `_seed_arrangements` did not name one")
        # The card is a door of its own rather than a second reading of the list: it answers the
        # history the pair's chat holds about this one arrangement, which the list never reads. Its
        # address is taken outside every window by the setup, and it is a plan of the reader's own
        # pairs, because a card the door refuses to open is a 404 and not a screen.
        return await get_plan_route(
            ctx["plan_id"], current_user=ctx["viewer_user"], session=session
        )

    async def account_export(session, ctx):
        from app.api.v1.users import export_account as export_account_route

        # The file a person takes out before they erase themselves, priced by the handler the route
        # dispatches: twelve sections assembled out of six services, and a re-assembled copy of those
        # steps is how stage 76 and stage 77 each published yesterday's call as today's number. The
        # reader comes from the context because `get_current_user` resolves it before the handler
        # runs, and so does the row of the session the token stands on — the document names the
        # device it was gathered from, and looking that up inside the window would price a read of
        # `refresh_tokens` as part of the file. The key is read, not fetched: a file always stands on
        # one live session, and a call that names none means the seed did not run rather than that
        # the account has no device, which are two different answers for the same published number.
        return await export_account_route(
            current_user=ctx["viewer_user"],
            current_session_id=ctx["export_session_id"],
            session=session,
        )

    async def session_refresh(session, ctx):
        # The call a client makes when its access token died: redeem the stored refresh token and
        # mint the pair that replaces it. The redeemed string is replaced in the context by the one
        # this call issued, because rotation consumes what it is given — keeping it would measure
        # one rotation and then four refusals, and a refusal writes nothing.
        token = ctx.get("refresh_token")
        if not token:
            raise RuntimeError("no live session to redeem: `_prime_session` did not run")
        tokens = await AuthService(session).refresh(token, USER_AGENT)
        ctx["refresh_token"] = tokens["refresh_token"]

    async def session_logout(session, ctx):
        queue = ctx.get("logout_tokens")
        if not queue:
            raise RuntimeError(
                f"the session queue is empty: the logout path needs one minted session per "
                f"repeat (`--runs` above {LOGOUT_SESSIONS})"
            )
        token = queue.pop(0)
        # The route reads the owner out of the token it was given before it revokes anything, so
        # the wrapper does the same; whose session it is never comes from the harness's own state.
        import uuid as uuid_module

        from app.core.security import decode_token

        user_id = uuid_module.UUID(decode_token(token, "refresh")["sub"])
        await AuthService(session).logout(user_id, token)

    return {
        "login": login,
        "public_profile": public_profile,
        "discovery_rebuild": discovery_rebuild,
        "discovery_page": discovery_page,
        "matches_list": matches_list,
        "match_detail": match_detail,
        "compatibility": compatibility,
        "chat_history": chat_history,
        "recommendations": recommendations,
        "answers_submit": answers_submit,
        "test_complete": test_complete,
        "like": like,
        "deck_exhausted": deck_exhausted,
        "universe_map": universe_map,
        "liked_me": liked_me,
        "liked": liked_list,
        "unlike": undo_tap,
        "passed": passed_list,
        "unpass": undo_pass,
        "session_refresh": session_refresh,
        "session_logout": session_logout,
        # Last on purpose. The seed of this family writes the first rows the stand has ever put into
        # `activity_preferences`, and the pair's card page and the pair's map read that table — so a
        # plan seed placed before them would move their medians, and the table would publish a page
        # length nobody shot. Running after every older path keeps those rows the same calls they were
        # measured as, and the only thing the seed can still reach is the row of its own card.
        "plans": plans_screen,
        # The two taps of one agreement, and they sit between the screen and its card on purpose. The
        # screen row of stage 119 is the steady open of a list nobody has moved, so it keeps its place
        # ahead of them; the card row was taken over a journal with nothing in it (12 statements, its
        # plan showing `Limit` over 0 rows), and these two doors are the first thing in the harness
        # that writes a line about a plan. Behind them the card is finally the read the pair makes:
        # `s120_shape2.json` counts it at 13 statements over a journal its own plan filled.
        "plan_hour": plan_hour_move,
        "plan_hour_confirm": plan_hour_answer,
        "plan_detail": plan_card,
        # Last on purpose, and the reason is the same one stage 119 wrote above the plans seed: this
        # row's preparation is the first thing on the stand that puts photographs, complaints and
        # blocks under the viewer, and every older row that reads those tables would otherwise
        # publish a page length nobody shot. Being last, the seed can only reach its own row — and
        # the page it prices is the account the whole harness has been building: the taps the tap
        # seeds wrote, the pairs `_seed_activity` paired, the arrangements the plan family agreed
        # on, the chat those arrangements filled.
        "account_export": account_export,
    }


def _select_paths(known: list[str], requested: str) -> list[str]:
    """Which paths a run measures, in the order the registry builds them.

    The order is not cosmetic: `_measure_size` runs each path's setup when its turn comes, and the
    seeds read and clear the same tables. The `likes` seeded by the tap-list setup delete the `passes`
    rows a withdrawal pool was addressed from (stage 26 makes a tap erase a pass), so a filter that
    kept the operator's order put `liked` before the inbox seed and made the `unpass` row answer
    `NotFoundError` instead of a number — `s123_scale_a.json` and `s123_scale_b.json` each show it.
    A name the registry does not know is refused rather than dropped: a silent typo publishes a
    shorter table than the document claims.

    A comma separates names and is not part of one, so each part is stripped before the registry is
    consulted — `--paths "liked, unpass"` is the same four characters of intent as `--paths liked,unpass`
    — and a value that holds no name at all, whether empty or padded or a bare separator, means the whole
    registry. That is the run the published table comes from, and it is a rule rather than what an empty
    set happens to produce: naming one path means measuring exactly that path and nothing else.
    """
    wanted = {part.strip() for part in requested.split(",") if part.strip()}
    unknown = sorted(wanted.difference(known))
    if unknown:
        raise SystemExit(
            f"прибор не знает путей: {', '.join(unknown)}; реестр держит {len(known)}: "
            f"{', '.join(known)}"
        )
    return [name for name in known if not wanted or name in wanted]


def _build_setups():
    """The state a path needs the stand in before it is timed, keyed by path name.

    Kept beside the paths and called by `_measure_size` outside the measured window: the queue of
    every account on the stand is not part of what an empty page costs, and on 50 000 it is worth
    more than everything the page itself does. The same holds for a read that only assembles a
    request body — the client took that map off the previous screen, so the screen under
    measurement never sends it.
    """
    return {
        "deck_exhausted": _drain_deck,
        "answers_submit": _answer_payload,
        "session_refresh": _prime_session,
        "session_logout": _prime_sessions,
        "liked_me": _seed_incoming_taps,
        "liked": _seed_own_taps,
        "unlike": _seed_taps_for_return,
        # The withdrawal of a pass reads no seed of its own — `_seed_activity` has been passing 40 % of
        # the crowd off the viewer since stage 20 — but its rotation pool has to be named at this path's
        # turn rather than once for the whole run: the two tap seeds above delete `passes` rows, because
        # a tap erases a pass (stage 26), and a pool addressed in `_context` goes on naming rows that
        # are gone. That is how `--paths liked,unpass,like` answered `NotFoundError` where a number
        # belongs (`s123_scale_a.json`, `s123_scale_b.json`), and the same in `unlike,unpass` after the
        # order was fixed. The address is one query, shared with `_context`, so the two cannot disagree.
        "unpass": _address_pass_pool,
        # Both doors of the plan family stand on the same seed: the screen needs the arrangements to
        # be on the page, and the card needs one of them to be addressable. `_seed_arrangements`
        # stops at what the pairs already hold, so the second call of a scale writes nothing and the
        # two rows price one page length (`_seed_own_taps` learned that rule in stage 118).
        "plans": _seed_arrangements,
        "plan_detail": _seed_arrangements,
        # Both writing doors stand on one seed and one pool of arrangements: the tap and the answer
        # are priced over the same page of the screen, which is the rule stage 118 put on the taps and
        # stage 119 on the arrangements. The seed asks the partner through their own verb, because a
        # question is a projection of two rows plus `_record_ask` and nothing else writes both.
        "plan_hour": _seed_hour_moves,
        "plan_hour_confirm": _seed_hour_moves,
        # The file's own sections: photographs, complaints with a history row, blocks, and the
        # session row the token of this run stands on. Placed with the row that reads them, which is
        # the last row of the registry.
        "account_export": _seed_own_rows,
    }


async def _seed_own_rows(session, ctx) -> None:
    """Put the rows the account's own file reads under the viewer, outside the measured window.

    A photograph is one row and no projection, so it goes in as plain SQL. A block and a complaint
    do not: a block dissolves the pair it stands on, a complaint arrives with a status and grows a
    history row when the queue moves it, so both are written through the verbs that write them — the
    rule stage 120 stated for a plan's question, which a raw `UPDATE` of the same columns broke.

    Both stop at what the viewer already holds, the way stage 118 made the tap seed stop at its
    target, so the second call of one scale writes nothing and the row prices one page length
    whatever the harness asked it for. The targets exclude the viewer's pairs on purpose: a block
    on a paired account would take the pair out from under the sections the rows above published.
    """
    from sqlalchemy import text

    from app.core.exceptions import ConflictError
    from app.services.auth_service import AuthService
    from app.services.moderation_service import ModerationService
    from app.services.safety_service import SafetyService

    viewer = ctx["viewer_id"]
    await session.execute(
        text(
            """
            INSERT INTO photos (id, user_id, url, is_primary, position, created_at, updated_at)
            SELECT gen_random_uuid(), :v, 'https://scale.invalid/photo/' || g || '.jpg',
                   g = 1, g - 1, now(), now()
            FROM generate_series(1, :want) g
            WHERE (SELECT count(*) FROM photos WHERE user_id = :v) < :want
            """
        ),
        {"v": viewer, "want": EXPORT_PHOTOS},
    )
    await session.commit()

    targets = list(
        (
            await session.execute(
                text(
                    """
                    SELECT u.id FROM users u JOIN profiles p ON p.user_id = u.id
                    WHERE u.is_active AND NOT u.is_deleted
                      AND u.id <> :v AND p.id IS NOT NULL
                      AND p.onboarding_completed_at IS NOT NULL AND p.is_hidden IS FALSE
                      AND NOT EXISTS (SELECT 1 FROM matches m
                                      WHERE (m.user_a_id = :v AND m.user_b_id = u.id)
                                         OR (m.user_b_id = :v AND m.user_a_id = u.id))
                    ORDER BY md5(u.email::text) LIMIT :n
                    """
                ),
                {"v": viewer, "n": EXPORT_BLOCKS + EXPORT_COMPLAINTS + 1},
            )
        ).scalars()
    )
    safety = SafetyService(session)
    blocked = set(
        (
            await session.execute(
                text("SELECT blocked_id FROM blocks WHERE blocker_id = :v"), {"v": viewer}
            )
        ).scalars()
    )
    for target in targets[:EXPORT_BLOCKS]:
        if target not in blocked:
            await safety.block(viewer, target)

    filed = set(
        (
            await session.execute(
                text("SELECT reported_id FROM reports WHERE reporter_id = :v"), {"v": viewer}
            )
        ).scalars()
    )
    reasons = ("spam", "harassment", "inappropriate")
    for target, reason in zip(targets[EXPORT_BLOCKS:EXPORT_BLOCKS + EXPORT_COMPLAINTS], reasons):
        if target in filed:
            continue
        try:
            await safety.report(viewer, target, reason, "Строка жалобы для файла своих строк.")
        except ConflictError:
            continue

    # One complaint of the page has been looked at, so the history the file carries is a row and not
    # a column of empty lists. The stand has no moderator until a history row needs one, and the role
    # is named here rather than left implied: stage 113 learned what an unnamed `is_moderator` does
    # to a reader of this table.
    if targets:
        moderator = targets[-1]
        # Exactly one complaint of the page is decided, and the stop rule says so rather than
        # implying it: `open` is the only status a decision may move, so a second call of one scale
        # would otherwise answer a different complaint and leave the row standing on two histories at
        # once — the same rule stage 118 put on the taps, read here off `report_reviews`. The
        # moderator is never the person the complaint is about, because the role says who may decide
        # and never whom they may decide about.
        reviewed = int(
            await session.scalar(
                text("SELECT count(*) FROM report_reviews rr JOIN reports r ON r.id = rr.report_id "
                     "WHERE r.reporter_id = :v"),
                {"v": viewer},
            )
            or 0
        )
        decided = (
            None
            if reviewed
            else await session.scalar(
                text("SELECT id FROM reports WHERE reporter_id = :v AND status = 'open' "
                     "AND reported_id <> :m ORDER BY created_at LIMIT 1"),
                {"v": viewer, "m": moderator},
            )
        )
        if decided is not None:
            await session.execute(
                text("UPDATE users SET is_moderator = true WHERE id = :m"), {"m": moderator}
            )
            await session.commit()
            await ModerationService(session).review(moderator, decided, "reviewed", None)

    live = await session.scalar(
        text("SELECT id FROM refresh_tokens WHERE user_id = :v AND revoked IS FALSE "
             "ORDER BY created_at DESC LIMIT 1"),
        {"v": viewer},
    )
    if live is None:
        # A file is always gathered from a device that is signed in, and the sweep the logout row
        # prices ends every session the viewer held — so the state is put back through the verb that
        # mints it, outside the window.
        await AuthService(session).issue_tokens(ctx["viewer_user"], USER_AGENT)
        live = await session.scalar(
            text("SELECT id FROM refresh_tokens WHERE user_id = :v AND revoked IS FALSE "
                 "ORDER BY created_at DESC LIMIT 1"),
            {"v": viewer},
        )
    if live is None:
        raise RuntimeError("no live session for the file: `AuthService.issue_tokens` gave none")
    ctx["export_session_id"] = live
    await session.commit()


async def _seed_incoming_taps(session, ctx) -> None:
    """Point taps from the crowd at the viewer, before the inbox is timed and outside its window.

    Every social row the stand writes about the viewer points outward: `_seed_activity` passes and
    pairs them with slices of the crowd, and the `like` path taps fresh peers. The rows stage 112's
    door reads — `likes` with `to_user_id` equal to the viewer — were written by nobody, so a path
    without this setup would publish the price of an empty inbox as the price of the page.

    The likers are exactly the accounts the door can name at that moment: active, not deleted,
    onboarded, not hidden, not the viewer, and not already a pair of theirs. The last condition is
    the one that decides the count: `_seed_activity` pairs the viewer with the newest 20/60/60
    accounts of the crowd, and `liked_me` drops a formed pair (`_relationship_conditions`), so
    without it the seeded rows would silently outnumber the readable ones and the document's
    «число запросов за вызов» would describe a page the screen never shows. Blocks are the other
    half of that anti-join and the stand seeds none.

    The percent is written as a number because the door answers with the stored
    `likes.compatibility_score` (defect 72-1 taught the row to keep its own number), and the taps
    step back in time by their rank, so the page's `(created_at DESC, id DESC)` order reads a real
    queue rather than one timestamp a sort resolves freely.
    """
    from sqlalchemy import text

    from app.services.discovery_service import LIKED_ME_SHOWN

    await session.execute(
        text(
            """
            WITH pool AS (
                SELECT u.id, row_number() OVER (ORDER BY md5(u.email::text)) AS n,
                       count(*) OVER () AS total
                FROM users u JOIN profiles p ON p.user_id = u.id
                WHERE u.is_active AND NOT u.is_deleted
                  AND p.is_hidden IS FALSE AND p.onboarding_completed_at IS NOT NULL
                  AND u.id <> :viewer
                  AND NOT EXISTS (
                      SELECT 1 FROM matches m
                      WHERE (m.user_a_id = :viewer AND m.user_b_id = u.id)
                         OR (m.user_b_id = :viewer AND m.user_a_id = u.id)
                  )
            )
            INSERT INTO likes (id, from_user_id, to_user_id, compatibility_score,
                               created_at, updated_at)
            SELECT gen_random_uuid(), pool.id, :viewer, 0.72,
                   now() - make_interval(mins => pool.n::int), now()
            FROM pool
            WHERE pool.n <= GREATEST(pool.total / :divisor, :floor)
            ON CONFLICT DO NOTHING
            """
        ),
        {
            "viewer": ctx["viewer_id"],
            "divisor": LIKED_ME_TAPS_DIVISOR,
            "floor": LIKED_ME_SHOWN + 1,
        },
    )
    await session.commit()


async def _seed_own_taps(session, ctx) -> None:
    """Bring the viewer's taps up to their target, before the own-taps list is timed and outside it.

    The mirror of `_seed_incoming_taps`, and it is needed for the same reason stated from the other
    end: the stand's viewer has written `likes` rows only through the timed `like` path, so the page
    behind `GET /discover/liked` would be priced empty. The candidates are the accounts the door can
    actually name at that moment — active, not deleted, onboarded, not hidden, not the viewer, not
    already a pair — and the last two clauses are new here on purpose: an account that already liked
    the viewer would turn a seeded mutual tap into a pair that never went through the match door, a
    state the product cannot reach, and the viewer's own earlier tap would make the seed a no-op
    whose page differs from the one being priced.

    The target is a rule of the scale, not of the call. A tenth of the candidates is counted over the
    crowd *before* the viewer's own taps are taken out of it, and the taps the viewer already holds
    are subtracted from that tenth — so the second call of one scale, the one behind `unlike`, writes
    nothing. Sizing the batch against what the first call left (`GREATEST(pool.total / :divisor,
    :floor)` with `total` over the filtered candidates) put a fresh tenth on top every time the scale
    asked twice, and stage 117 measured what that did to its own table: 90 taps under the row for the
    list against 169 under the row for the withdrawal at 1 000, 897 against 1 701 at 10 000, 4 497
    against 8 541 at 50 000 (`s117_tap_counts.json`). Two rows of one door pair priced pages of
    different length, and the document said so as an open end.

    The seed also clears the pass rows the tapped accounts hold behind the viewer's taps, because a
    real tap does exactly that (stage 26): leaving them would price a page whose pairs stand in a
    state no screen can hold. With the target rule that DELETE clears nothing on a second call, which
    is the other half of why the neighbours of this scale stop moving between its two rows.
    """
    from sqlalchemy import text

    from app.services.discovery_service import LIKED_SHOWN

    await session.execute(
        text(
            """
            WITH crowd AS (
                SELECT u.id
                FROM users u JOIN profiles p ON p.user_id = u.id
                WHERE u.is_active AND NOT u.is_deleted
                  AND p.is_hidden IS FALSE AND p.onboarding_completed_at IS NOT NULL
                  AND u.id <> :viewer
                  AND NOT EXISTS (
                      SELECT 1 FROM matches m
                      WHERE (m.user_a_id = :viewer AND m.user_b_id = u.id)
                         OR (m.user_b_id = :viewer AND m.user_a_id = u.id)
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM likes back
                      WHERE back.from_user_id = u.id AND back.to_user_id = :viewer
                  )
            ),
            already AS (SELECT count(*)::int AS n FROM likes WHERE from_user_id = :viewer),
            pool AS (
                SELECT c.id, row_number() OVER (ORDER BY md5(u.email::text)) AS n,
                       (SELECT count(*) FROM crowd) AS total
                FROM crowd c JOIN users u ON u.id = c.id
                WHERE NOT EXISTS (
                    SELECT 1 FROM likes mine
                    WHERE mine.from_user_id = :viewer AND mine.to_user_id = c.id
                )
            )
            INSERT INTO likes (id, from_user_id, to_user_id, compatibility_score,
                               created_at, updated_at)
            SELECT gen_random_uuid(), :viewer, pool.id, 0.72,
                   now() - make_interval(mins => pool.n::int), now()
            FROM pool, already
            WHERE pool.n <= GREATEST(pool.total / :divisor, :floor) - already.n
            ON CONFLICT DO NOTHING
            """
        ),
        {
            "viewer": ctx["viewer_id"],
            "divisor": LIKED_TAPS_DIVISOR,
            "floor": LIKED_SHOWN + 1,
        },
    )
    await session.execute(
        text(
            "DELETE FROM passes ps "
            "WHERE ps.from_user_id = :viewer AND ps.to_user_id IN ("
            "SELECT l.to_user_id FROM likes l WHERE l.from_user_id = :viewer)"
        ),
        {"viewer": ctx["viewer_id"]},
    )
    await session.commit()


async def _seed_taps_for_return(session, ctx) -> None:
    """Hand the withdrawal its rotation pool, seeding the viewer's taps only if the scale has none.

    The withdrawal consumes what it prices — the second undo of one tap answers 404 and writes
    nothing — so the target arrives from `unlike_peers`, the viewer's own tap rows, the way `unpass`
    rotates over the passes `_seed_activity` left behind. The pool is read by the harness's own
    account (the `scale_` crowd), never by another viewer's page.

    The seed call behind this setup is the second one of the scale whenever the registry ran `liked`
    first, and `_seed_own_taps` fills to a target rather than adding a batch, so nothing new is
    written here and both rows of the door pair price the same page. Called alone — a stand shot with
    `--paths unlike` — it still brings the taps up, because a withdrawal from an empty list is the 404
    the door answers, not the gesture.
    """
    from sqlalchemy import text

    await _seed_own_taps(session, ctx)
    rows = (
        await session.execute(
            text(
                "SELECT l.to_user_id FROM likes l "
                "WHERE l.from_user_id = :viewer LIMIT 64"
            ),
            {"viewer": ctx["viewer_id"]},
        )
    ).scalars().all()
    if not rows:
        raise RuntimeError(
            "the own-taps seed wrote nothing: the withdrawal path would rotate over an empty pool "
            "and time a refusal instead of the gesture"
        )
    ctx["unlike_peers"] = list(rows)
    ctx["unlike_turn"] = 0


# People the viewer has actually passed, in the order the return rotates over them. One query, used by
# `_context` for the first address and by `_address_pass_pool` at the path's own turn: two copies of the
# same text is how a pool addressed once and a pool re-addressed later start naming different rows.
_PASS_POOL_ADDRESS = (
    "SELECT ps.to_user_id FROM passes ps "
    "JOIN users u ON u.id = ps.to_user_id "
    "WHERE ps.from_user_id = :v AND u.is_active AND NOT u.is_deleted "
    "ORDER BY md5(u.email::text) LIMIT 64"
)


async def _address_pass_pool(session, ctx) -> None:
    """Name the passes the withdrawal can take back, at the turn the withdrawal is measured.

    `unpass` consumes its own row: the second return of one pass answers 404 and writes nothing, so the
    target arrives from a pool the harness rotates over — the bargain stage 115 struck with this door and
    stage 118 restated for `unlike`. What stage 115 could not see is that the pool was addressed once, in
    `_context`, before any path ran, while the tap seeds that come earlier in the registry delete
    `passes` rows: a tap erases a pass (stage 26). So whether the row got a number or an error depended
    on which other paths the operator asked for — `--paths liked,unpass,like` and `--paths unlike,unpass`
    both answered `NotFoundError: You have not passed this user.` while the full registry and
    `--paths liked,liked_me,unpass` answered 42.9 and 46.0 ms.

    Re-reading the address at the path's turn makes the gesture measurable in every subset: the pool
    holds exactly the passes that stand when the withdrawal is timed. Reading is all it does — the
    rotation index restarts at zero, so the first measured call takes the first standing row rather than
    the fourth of a list two of which no longer exist. An empty pool is refused rather than rotated
    over, because `% len(peers)` would abort the whole shooting for one row's missing state.
    """
    from sqlalchemy import text

    rows = (
        await session.execute(text(_PASS_POOL_ADDRESS), {"v": ctx["viewer_id"]})
    ).scalars().all()
    if not rows:
        raise RuntimeError(
            "the pass pool is empty: the withdrawal would rotate over nothing and time a refusal "
            "instead of the gesture"
        )
    ctx["unpass_peers"] = list(rows)
    ctx["unpass_turn"] = 0


_PLAN_CHOSEN = """
    WITH pairs AS (
        SELECT m.id AS match_id, m.user_a_id, m.user_b_id,
               row_number() OVER (ORDER BY m.created_at, m.id) AS n
        FROM matches m
        WHERE m.user_a_id = :viewer OR m.user_b_id = :viewer
    ),
    catalogue AS (SELECT array_agg(id ORDER BY id) AS ids FROM activities),
    chosen AS (
        SELECT p.match_id, p.user_a_id, p.user_b_id, p.n,
               c.ids[((p.n - 1) * CAST(:per_pair AS integer) + s.off - 1)
                     % cardinality(c.ids) + 1] AS activity_id,
               date_trunc('hour', now()) + make_interval(days => (p.n % 21 + 1)::int, hours => 19)
                   AS agreed
        FROM pairs p
        CROSS JOIN catalogue c
        CROSS JOIN generate_series(1, CAST(:per_pair AS integer)) AS s(off)
    )
"""


async def _seed_arrangements(session, ctx) -> None:
    """Give every pair of the viewer the arrangement its two taps left behind.

    The plan family is the one part of the app the stand never wrote a row for: `_seed_activity`
    fills passes, the viewer's pairs and the volume of two conversations, and the crowd's pairs carry
    their own messages, but nothing in the harness has ever touched `shared_plans`,
    `shared_plan_members` or `activity_preferences`. The probe that opened stage 119 counted the
    result — 0 / 0 / 0 rows on a scale of 1 000 that holds 20 pairs of the viewer — and measured what
    a door pointed at that state would publish: 150.4 мс and 41 statements for a screen with nothing
    on it. Stage 42 and stage 113 each learned the same lesson from the other side: a read priced
    over an empty box is not the price of the screen.

    The rows are written as a pair actually leaves them. One half names an hour and the other accepts
    exactly that instant — `agreed_instant` answers a moment only to that shape, and two rows that
    each only named one would leave the plan with a question instead of an evening. The plan then
    carries the title the catalogue holds, `starts_at` the instant both rows agree on, `was_planned`
    and the status the projection itself would compute (`planned`), and each half gets its own answer
    row saying `joined`. Written any other way, the read under measurement would arrive at a state
    the product cannot hold, or would spend its window correcting the seed.

    Which is the point of the second half of this docstring: the row the table publishes is the
    screen as the app shows it on an ordinary open, and the probe measured the other one too. Put the
    preference rows of 20 pairs in front of a plan table that holds nothing, and the first GET sends
    146 statements — `insert into shared_plans`, `insert into shared_plan_members`, `update
    shared_plans` — and costs 632.1 мс. The read is not read-only when the pair's rows have outrun
    its records, and that is the price of a first open, not the price of the screen; the seed writes
    what the first open would have written so the window measures the open that follows.

    The seed stops where the pairs already stand. Each statement is guarded by `NOT EXISTS` over the
    rows of the same pair and idea, so the second call of one scale — the one behind the row for the
    card — writes nothing, which is the rule stage 118 put on the tap seed for exactly the reason it
    carries here: two rows of one family priced over pages of different length.
    """
    from sqlalchemy import text

    params = {"viewer": ctx["viewer_id"], "per_pair": PLANS_PER_PAIR}
    await session.execute(
        text(
            _PLAN_CHOSEN
            + """
            INSERT INTO activity_preferences (id, user_id, activity_id, match_id, score, proposed,
                                              declined, meeting_time, accepted_time, created_at,
                                              updated_at)
            SELECT gen_random_uuid(), u.uid, k.activity_id, k.match_id, 0.72, true, false,
                   CASE WHEN u.uid = k.user_a_id THEN k.agreed ELSE NULL END,
                   CASE WHEN u.uid = k.user_a_id THEN NULL ELSE k.agreed END,
                   k.agreed - make_interval(days => (k.n * 3)::int, hours => 3), now()
            FROM chosen k
            CROSS JOIN LATERAL (SELECT k.user_a_id AS uid UNION ALL SELECT k.user_b_id) u
            WHERE k.activity_id IS NOT NULL
            ON CONFLICT DO NOTHING
            """
        ),
        params,
    )
    await session.execute(
        text(
            _PLAN_CHOSEN
            + """
            INSERT INTO shared_plans (id, match_id, activity_id, created_by, title, note, place,
                                      starts_at, pending_hour, pending_by, status, was_planned,
                                      cancelled_at, cancelled_by, created_at, updated_at)
            SELECT gen_random_uuid(), k.match_id, k.activity_id, k.user_a_id, a.title, NULL, NULL,
                   k.agreed, NULL, NULL, 'planned', true, NULL, NULL,
                   k.agreed - make_interval(days => (k.n * 3)::int), now()
            FROM chosen k JOIN activities a ON a.id = k.activity_id
            WHERE NOT EXISTS (SELECT 1 FROM shared_plans sp
                              WHERE sp.match_id = k.match_id AND sp.activity_id = k.activity_id)
            ON CONFLICT DO NOTHING
            """
        ),
        params,
    )
    await session.execute(
        text(
            """
            INSERT INTO shared_plan_members (id, plan_id, user_id, decision, attended_at,
                                             personal_note, created_at, updated_at)
            SELECT gen_random_uuid(), p.id, u.uid, 'joined', NULL, NULL, p.created_at, now()
            FROM shared_plans p
            JOIN matches m ON m.id = p.match_id
            CROSS JOIN LATERAL (SELECT m.user_a_id AS uid UNION ALL SELECT m.user_b_id) u
            WHERE (m.user_a_id = :viewer OR m.user_b_id = :viewer)
              AND NOT EXISTS (SELECT 1 FROM shared_plan_members sm
                              WHERE sm.plan_id = p.id AND sm.user_id = u.uid)
            ON CONFLICT DO NOTHING
            """,
        ),
        {"viewer": ctx["viewer_id"]},
    )
    # The card's address, taken outside every window the way `unlike_peers` is taken: the door opens
    # one plan, and the plan it opens has to be one the reader is in — a screen that named somebody
    # else's arrangement would be priced answering 404.
    ctx["plan_id"] = await session.scalar(
        text(
            "SELECT p.id FROM shared_plans p JOIN matches m ON m.id = p.match_id "
            "WHERE m.user_a_id = :viewer OR m.user_b_id = :viewer "
            "ORDER BY p.created_at DESC LIMIT 1"
        ),
        {"viewer": ctx["viewer_id"]},
    )
    if ctx["plan_id"] is None:
        raise RuntimeError(
            "the plan seed named no arrangement: the viewer of this stand holds no pair, so both "
            "rows of the plan family would price an empty list rather than the screen"
        )
    await session.commit()


async def _seed_hour_moves(session, ctx) -> None:
    """Hand the two writing doors of the plan family the arrangements they can each write on.

    Stage 119 priced the family's two reads and named the taps as the open end. The probe of this
    stage counted them (`s120_gap.json`, db `befos_s120gap`): a tap that names a different evening is
    25 statements and writes two lines into the pair's chat, a tap that answers the evening the other
    half named is 22 statements and writes one, a tap that names the hour the plan already holds is
    18 and writes nothing, and a refusal costs 11. None of those numbers belongs to a door pointed at
    a state the harness never built, so the seed builds the two states the doors meet: half of the
    pool is an evening the pair stands on with nobody asking, and the other half is a question the
    partner is asking.

    The question is asked through the partner's own verb — `PlanService.offer_hour`, which is what
    `POST /api/v1/plans/{id}/hour` dispatches to for them. The first take of `s120_shape.py` wrote the
    partner's preference row with an UPDATE instead, and the answer then landed on a pair of rows the
    product does not hold: the projection still read the old evening as agreed, so the answer wrote a
    `plan_voided` line and no `plan_agreed` one. A question is not a value in a column; `_record_ask`
    is what puts it on the plan, and only the verb calls it.

    The pool is ordered with the card's own plan first, so the arrangement the move door taps in its
    first repeat is the one the card row reads afterwards — that is why the two doors sit ahead of
    `plan_detail` and behind `plans`: `s120_shape2.json` counts the card at 13 statements over a
    journal its own plan filled against the 12 stage 119 took over an empty one.

    The second call of one scale — the one behind the row for the answer — reads back the question it
    already asked from `pending_hour` and writes nothing, which is the rule stage 118 put on the tap
    seed: the two doors have to price one page of the screen, not two.
    """
    from datetime import timedelta

    from sqlalchemy import text

    from app.services.plan_service import PlanService

    await _seed_arrangements(session, ctx)
    rows = (await session.execute(
        text(
            """
            SELECT p.id, p.match_id, p.activity_id,
                   CASE WHEN m.user_a_id = :viewer THEN m.user_b_id ELSE m.user_a_id END AS peer,
                   coalesce(p.starts_at, p.pending_hour) AS anchor,
                   p.pending_by, p.pending_hour
            FROM shared_plans p
            JOIN matches m ON m.id = p.match_id
            WHERE (m.user_a_id = :viewer OR m.user_b_id = :viewer)
              AND p.status IN ('planned', 'rescheduled')
              AND coalesce(p.starts_at, p.pending_hour) IS NOT NULL
            ORDER BY (p.id = :addressed) DESC, p.created_at, p.id
            LIMIT :cap
            """
        ),
        {
            "viewer": ctx["viewer_id"],
            "addressed": ctx["plan_id"],
            "cap": 2 * HOUR_ARRANGEMENTS,
        },
    )).all()
    if not rows:
        raise RuntimeError(
            "the hour seed found no arrangement to write on: the plan family would price a door "
            "whose list is empty, which is the mistake stage 119 closed for its screen"
        )
    half = len(rows) // 2
    moves, questions = [], []
    service = PlanService(session)
    for index, row in enumerate(rows):
        anchor = row.anchor
        if index < half:
            moves.append((row.id, anchor + timedelta(hours=index + 1)))
            continue
        if row.pending_by is not None and str(row.pending_by) != str(ctx["viewer_id"]):
            questions.append((row.id, row.pending_hour))
            continue
        asked = anchor + timedelta(days=1, hours=index + 1)
        await service.offer_hour(row.match_id, row.peer, row.activity_id, asked)
        questions.append((row.id, asked))
    ctx["hour_moves"] = moves[:HOUR_ARRANGEMENTS]
    ctx["hour_questions"] = questions[:HOUR_ARRANGEMENTS]
    if not ctx["hour_moves"] or not ctx["hour_questions"]:
        raise RuntimeError(
            f"the hour seed split {len(rows)} arrangements into {len(ctx['hour_moves'])} evenings to "
            f"move and {len(ctx['hour_questions'])} questions to answer: one of the two doors would "
            "price a queue it never got"
        )
    await session.commit()


async def _empty_deck(session, ctx) -> None:
    """Put the viewer back into the state a profile edit leaves: nothing ready in the deck.

    This is the statement `PATCH /users/me` and `POST /tests/complete` pay, not the page's. It used
    to sit inside the rebuild's window, which is how the row for `GET /discover` came to carry a
    DELETE the route never sends.
    """
    from app.repositories.social_repo import DiscoveryRepository

    await DiscoveryRepository(session).deck_invalidate(ctx["viewer_id"])
    await session.commit()


def _build_resets():
    """The state a path's *repeat* needs, restored between the timed calls of that path.

    The setups above run once, before the first call, and are guarded by the context. A path that
    consumes the state it is priced on has to have that state put back before every call, or the
    second repeat times the answer the first one left behind — for the rebuild, a deck that just
    filled itself with 150 ranked candidates, which is a warm page and not a rebuild. Restoring it
    belongs to the screen that comes before, so it runs outside the timer and outside the capture.
    """
    return {"discovery_rebuild": _empty_deck}


async def _seed_catalog(engine) -> None:
    """Put the question and activity rows on the stand, which the generated crowd does not carry.

    The population is written as vectors straight into `compatibility_profiles`, so a stand
    without these rows has no catalogue for the test-submission path to validate against, and
    that path would measure a refusal instead of a save. The viewer also gets one answer per
    question: finishing the test is gated on the catalog being answered through, and the gate
    must pass for the completion path to measure a completion.

    The activities are the recommendation engine's input. Without them the cold page scored an
    empty catalogue, wrote nothing and still reported a median — the number was the price of
    reading nobody's profile, not the price of producing a page.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import Activity, TestAnswer, TestOption, TestQuestion
    from app.seed_data.activities_catalog import ACTIVITIES
    from app.seed_data.questions_catalog import QUESTIONS

    async with AsyncSession(bind=engine) as session:
        for slug, title, description, category, interests, cities, energy, social, cost in ACTIVITIES:
            session.add(
                Activity(
                    slug=slug,
                    title=title,
                    description=description,
                    category=category,
                    interests=interests,
                    cities=cities,
                    energy=energy,
                    social=social,
                    cost=cost,
                )
            )
        answered: list[tuple[int, int]] = []
        for position, (category, trait, text_, options) in enumerate(QUESTIONS):
            question = TestQuestion(
                category=category, trait=trait, text=text_, position=position, is_active=True
            )
            session.add(question)
            await session.flush()
            option_rows = [
                TestOption(
                    question_id=question.id,
                    text=option_text,
                    value=value,
                    position=option_position,
                )
                for option_position, (option_text, value) in enumerate(options)
            ]
            session.add_all(option_rows)
            # Flushed before the id is read: an unpersisted option still carries None.
            await session.flush()
            answered.append((question.id, option_rows[0].id))
        viewer = await session.scalar(text("SELECT id FROM users WHERE email = :e"), {"e": VIEWER_EMAIL})
        for question_id, option_id in answered:
            session.add(TestAnswer(user_id=viewer, question_id=question_id, option_id=option_id))
        await session.commit()


async def _context(engine) -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import User

    async with AsyncSession(bind=engine) as session:
        viewer = await session.scalar(text("SELECT id FROM users WHERE email = :e"), {"e": VIEWER_EMAIL})
        peer = await session.scalar(
            text("SELECT u.id FROM users u JOIN profiles p ON p.user_id = u.id "
                 "WHERE u.email ~ '^scale_[0-9]+@befos.test$' ORDER BY u.email LIMIT 1")
        )
        # The person the auth dependency hands to every handler of an authenticated route. Loaded
        # once here, outside every measured window, because the dependency resolves it before the
        # handler runs: a wrapper that read `users` inside its own window would count the token's
        # owner as part of the screen's price, and the screen it is pricing does not pay it.
        viewer_user = await session.get(User, viewer)
        match_id = await session.scalar(
            text("SELECT id FROM matches WHERE user_a_id = :v ORDER BY created_at DESC LIMIT 1"),
            {"v": viewer},
        )
        # People the viewer has never acted on, for the tap that has to land on a fresh pair:
        # the seeding gives the viewer passes and matches over slices of the crowd, and a like
        # on somebody already passed takes the delete branch a first tap on a stranger does not.
        like_peers = list(
            (
                await session.execute(
                    text(
                        "SELECT u.id FROM users u JOIN profiles p ON p.user_id = u.id "
                        "WHERE u.email ~ '^scale_[0-9]+@befos.test$' "
                        "AND p.onboarding_completed_at IS NOT NULL AND p.is_hidden IS FALSE "
                        "AND NOT EXISTS (SELECT 1 FROM likes l WHERE l.from_user_id = :v AND l.to_user_id = u.id) "
                        "AND NOT EXISTS (SELECT 1 FROM passes ss WHERE ss.from_user_id = :v AND ss.to_user_id = u.id) "
                        "AND NOT EXISTS (SELECT 1 FROM matches m WHERE (m.user_a_id = :v AND m.user_b_id = u.id) "
                        "OR (m.user_b_id = :v AND m.user_a_id = u.id)) "
                        "ORDER BY md5(u.email) LIMIT 64"
                    ),
                    {"v": viewer},
                )
            ).scalars()
        )
        # People the viewer has actually passed: the return path rotates its undo over these,
        # because the gesture consumes its own row and a second return of the same pass answers
        # 404. The pool is addressed here — before any window opens — the same way `like_peers`
        # is; `_seed_activity` wrote every one of these rows. Showability is not part of the
        # address: the return clears the answer whatever the deck's filter says about the person.
        # `unpass` takes the same address again at its own turn (`_address_pass_pool`), because the
        # tap seeds that come earlier in the registry delete `passes` rows out of this list.
        unpass_peers = list(
            (
                await session.execute(
                    text(_PASS_POOL_ADDRESS),
                    {"v": viewer},
                )
            ).scalars()
        )
    return {
        "viewer_email": VIEWER_EMAIL,
        "viewer_id": viewer,
        "viewer_user": viewer_user,
        "peer_id": peer,
        "match_id": match_id,
        "like_peers": like_peers,
        "like_turn": 0,
        "unpass_peers": unpass_peers,
        "unpass_turn": 0,
    }


_WRITING = re.compile(r"\b(insert|update|delete)\b", re.IGNORECASE)

# The verbs a request pays a statement for: reading rows and writing rows.
_PAID_VERBS = ("select", "with", "insert", "update", "delete")
_FIRST_WORD = re.compile(r"[a-z]+")


def _captured_by_harness(statement: str) -> bool:
    """Does this statement belong to the count of statements the measured call paid?

    The window used to answer by first letter — `s` or `w` — and that answer was written for the
    EXPLAIN replay, where a write must never run a second time (`_read_only`). Applied to the count
    it dropped every `INSERT`, `UPDATE` and `DELETE` the call sent: the stage-77 artifact publishes
    `login` at one statement per call although the wrapper demonstrably sends the profile read and
    the session `INSERT`, and `session_logout` at zero for a route whose whole answer is one
    `UPDATE`. Naming the rule is what makes the next change to it visible to a test.

    DDL and connection plumbing stay out: `CREATE INDEX` is the stand's own work, and `SET`, `SHOW`
    and `SAVEPOINT` are not statements a screen charges the reader for.
    """
    head = _FIRST_WORD.match(statement.lstrip().lower())
    return head is not None and head.group() in _PAID_VERBS


def _walk(node: dict):
    yield node
    for child in node.get("Plans", ()):
        yield from _walk(child)


def _read_only(sql: str) -> bool:
    """EXPLAIN ANALYZE runs the statement, so a write must never be replayed.

    This is the replay guard, and it is stricter than the count: the capture keeps writes, because
    the call paid them (`_captured_by_harness`), and only reads are replayed, because a second write
    would not be the same call. `W` in the old filter also matched the `WITH … INSERT` the discovery
    queue is written with. Column names like `updated_at` are one word, so the boundary in
    `\\bupdate\\b` does not catch them.
    """
    return _WRITING.search(sql) is None


def _scan_summary(plan: dict) -> dict:
    """Root shape plus the scan that burned the most wall time — that is what grows with rows."""
    worst = None
    for node in _walk(plan):
        if "Scan" not in str(node.get("Node Type", "")):
            continue
        spent = node.get("Actual Total Time", 0.0) * node.get("Actual Loops", 1)
        if worst is None or spent > worst[0]:
            worst = (spent, node)
    summary = {
        "root": plan.get("Node Type"),
        "rows": plan.get("Actual Rows"),
        "read": plan.get("Shared Read Blocks"),
        "hit": plan.get("Shared Hit Blocks"),
    }
    if worst is not None:
        node = worst[1]
        summary["scan"] = {
            "node": node.get("Node Type"),
            "relation": node.get("Relation Name"),
            "rows": node.get("Actual Rows"),
            "loops": node.get("Actual Loops"),
            "ms": round(worst[0], 2),
            "read": node.get("Shared Read Blocks"),
            "hit": node.get("Shared Hit Blocks"),
        }
    return summary


async def _settle_statistics(asyncpg, database: str) -> None:
    """Make the planner's row estimates describe the rows the stand holds right now.

    A path's latency is the price of the plan the server chose, and the plan is chosen from
    ``pg_class.reltuples`` and ``pg_statistic`` — not from the rows. The harness writes those rows
    in two places the estimates do not follow automatically: the catalogue seed after the readout,
    and a path's own setup, which for the exhausted deck is a queue of one row per account on the
    stand. Until this function was called per path, the only ``ANALYZE`` of the run sat before both
    of them, so the measured page was planned against a queue the statistics still called empty.

    Measured on ``befos_s67fresh`` (50 000 accounts, viewer with 20 000 passes, deck drained by the
    setup): ``reltuples = 0`` and ``relpages = 0`` with 50 000 rows in the table, ``last_analyze``
    16:33:55 while the drain wrote at 16:34:0x and the server's own autoanalyze only reached the
    table at 16:34:54 — after every number of the run had been taken. The published row was
    323.4 ms median with a plan of 317.5 ms, 223 169 shared-buffer hits and an index-only scan of
    the queue run 30 000 times; the same statement text and the same parameters, replayed once the
    queue was counted, cost 68.1…76.5 ms with 1 760 hits and a hash anti join, and the whole call
    102.2 ms (``s67_capture_feed.py``, ``s67_probe_flip.py``). One row moved in ``_measure_size``
    between those two states: when the statistics were refreshed. Re-run end to end with this step in
    the loop, the same stand published ``deck_exhausted`` first 159.7 / median 107.2 / max 108.3 ms
    and ``discovery_rebuild`` 118.2 / 108.7 / 109.2 ms, with worst reads of 81.73 and 74.32 ms over
    1 766 and 1 760 hits and a ``Seq Scan`` of the 50 000 profiles in a single loop.

    ``ANALYZE`` costs about 2.2 s on a 50 000 stand (measured twice: 2 321 ms and 2 189 ms), which
    is why it runs once per path rather than being hoisted into the seed: a path that grows the
    queue as it is timed — every deck page appends — has to be planned against the queue the
    previous paths left, not the one the crowd was seeded with.
    """
    conn = await asyncpg.connect(dsn=_asyncpg_dsn(database))
    try:
        await conn.execute("ANALYZE")
    finally:
        await conn.close()


async def _plans(asyncpg, dsn: str, captured: dict[str, list[tuple[str, tuple]]]) -> dict:
    """Replay the reads each path sent, so a latency number arrives with the plan behind it.

    Grouped by statement text and replayed once each: a path that loads one row per card sends the
    same text many times, and the aggregate is meant to describe one pass over the screen, which is
    what can then be compared against the wall-clock median for the same pass.
    """
    out = {}
    conn = await asyncpg.connect(dsn=dsn)
    try:
        for name, statements in captured.items():
            best_by_sql: dict[str, tuple[float, dict]] = {}
            for sql, params in statements:
                if not _read_only(sql):
                    continue
                try:
                    rows = await conn.fetch(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}", *params)
                except Exception:
                    continue
                report = json.loads(rows[0][0])[0]
                cost = report.get("Execution Time", 0.0)
                if cost >= best_by_sql.get(sql, (0.0, {}))[0]:
                    best_by_sql[sql] = (cost, report["Plan"])
            if not best_by_sql:
                continue
            top_sql, (cost, plan) = max(best_by_sql.items(), key=lambda item: item[1][0])
            out[name] = {
                "plan_ms": round(cost, 2),
                "distinct_reads": len(best_by_sql),
                "reads_sum_ms": round(sum(value[0] for value in best_by_sql.values()), 2),
                **_scan_summary(plan),
                "sql": " ".join(top_sql.split())[:220],
            }
    finally:
        await conn.close()
    return out


def _row(name: str, timings: list[float], statements_per_run: list[int]) -> dict:
    """Turn the timed calls of one path into a row, keeping the first call out of the page.

    The calls of a path are not one sample. Measured 2026-10-09 on the same stand the same path was
    read on, the first call of `public_profile` at 1 001 profiles cost 124.0 ms and the four that
    followed 25.5…30.4 ms; at 50 000 the first call of `deck_exhausted` cost 55 472.8 ms and the
    next four 255.7…290.3 ms. Averaging or maxing over that first call publishes a number no reader
    can attribute to the screen — stage 42's «максимум 55 118.0 мс» was exactly this call, and the
    warming of a connection's plans and of pages the stand had not been read from yet is not a page
    that got slower. So the first call gets its own column and the median and the maximum are taken
    over the repeats that came after it.

    The same split belongs to the statement count, and it only became visible once writes were
    counted (`_captured_by_harness`): a path whose first call takes a branch its repeats do not —
    `answers_submit` writes rows that the seeding had already put there — averaged a cold call into
    a column meant to describe the page. Both halves are published, and the per-repeat list travels
    in the artifact so a fractional cell is re-derivable rather than explained away.
    """
    if len(timings) < 2:
        raise ValueError(
            f"путь {name} замерен одним вызовом: медиана берётся по прогретому повтору, "
            "нужен --runs не меньше двух"
        )
    if len(statements_per_run) != len(timings):
        raise ValueError(
            f"путь {name}: замеров {len(timings)}, а обращений записано {len(statements_per_run)} — "
            "ряд обращений не соответствует ряду замеров"
        )
    cold, *warm = timings
    warm_statements = statements_per_run[1:]
    return {
        "path": name,
        "first_ms": round(cold, 1),
        "median_ms": round(statistics.median(warm), 1),
        "max_ms": round(max(warm), 1),
        "statements_per_call": round(sum(warm_statements) / len(warm_statements), 1),
        "statements_first": statements_per_run[0],
        "statements_per_run": list(statements_per_run),
        # The row stays readable against the run it came from, so a published number can be
        # re-derived by whoever repeats the command.
        "timings": [round(value, 1) for value in timings],
    }


def _format_row(row: dict) -> str:
    return (
        f"  {row['path']:<20} первый {row['first_ms']:>9.1f} мс"
        f"   медиана {row['median_ms']:>8.1f} мс   max {row['max_ms']:>8.1f} мс"
        f"   запросов за вызов {row['statements_per_call']}"
        f" (первый {row['statements_first']}, по повторам {row['statements_per_run']})"
    )


def _viewer_matches(size: int, override: int = 0) -> int:
    """How many pairs the viewer of one stand holds.

    The route this feeds puts no ceiling on its read (`MatchesService.list_matches` has no
    `.limit()`), so the list the screen returns grows with the account while the default here was
    flat: 20 пар at 1 000, 60 at 10 000 and at 50 000. That is the shape the published rows were
    measured at (стадия 33 gives 29.8 / 37.2 / 34.3 мс), and it is why the waste stage 49 removed
    from this read was invisible for the thirty stages before it — the same reason a cap hides an
    overflow: the axis was never sampled. On the stand of 2026-10-10 the same code at 1 000 пар
    стоит 276.7 мс. `--viewer-matches` makes that axis a command instead of an edit.
    """
    if override > 0:
        return override
    return min(60, max(5, size // 50))


def _stand_engine(database: str):
    """An engine for the stand that plans the way the product's connections plan.

    Every latency row this harness publishes is read as what one call costs the app, so the
    connection it is measured on has to make the same plan decision the app's connections make.
    Until stage 58 it did not: the engine was built here, bare, and Postgres therefore switched
    the deck's selection rule to one generic plan after the fifth execution of the pooled
    connection — the decision `app.core.database` now refuses to let the server make. The
    published table was measured on the configuration that produced the penalty, so it described
    neither the app of the day nor the app after the fix.

    The switch is reachable here precisely because the harness borrows one connection at a time:
    the pool's ceiling of five is never filled — one backend pid serves a whole run of the paths,
    thirteen of them at the evening that measured this — so the deck's rule, which
    `discovery_rebuild` and `discovery_page` call before the exhausted page is timed, passes its
    fifth execution inside the same run. Measured on the 50 000
    stand, holding the harness's own path order and reading `pg_prepared_statements` after every
    path: the rule stands at 1 generic plan against 5 custom already when `discovery_page` ends, and
    at 4 against 8 by the time `deck_exhausted` is timed, while the same sequence on this engine
    leaves it at 0 against 12 and the page at 101 ms against 238.

    Only the plan decision is shared. The pool stays the harness's own, without the product's
    pre-ping and recycling, because the stand measures a single call rather than a queue of
    concurrent ones.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.database import PLAN_MODE_CONNECT_ARGS

    return create_async_engine(
        _sqlalchemy_url(database), pool_size=5, connect_args=PLAN_MODE_CONNECT_ARGS
    )


async def _measure_size(asyncpg, database: str, size: int, acted: int, runs: int,
                        path_names: list[str], verbose: bool, viewer_matches: int = 0) -> dict:
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.security import hash_password

    await _recreate_database(asyncpg, database)
    _upgrade_schema(database)
    seed = await _seed(asyncpg, database, size, hash_password(PASSWORD))
    activity = await _seed_activity(
        asyncpg, database, acted, matches=_viewer_matches(size, viewer_matches), messages=120,
        crowd_matches=size // 10, crowd_messages=8,
    )

    admin = await asyncpg.connect(dsn=_asyncpg_dsn(database))
    # No ANALYZE here: the numbers below read the live counters and the on-disk sizes, both of
    # which describe the crowd as it was seeded, while the estimates a path is planned under have
    # to describe the queue and the catalogue this harness is about to write on top of that crowd.
    # `_settle_statistics` is called per path for that reason.
    tables = await admin.fetch(
        "SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE n_live_tup > 0 "
        "ORDER BY n_live_tup DESC LIMIT 8"
    )
    # The table the read plan scans is only half the story: `pg_total_relation_size` counts the
    # indexes the writes pay for, which is the other reason a schema stops scaling.
    sizes = await admin.fetch(
        "SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS total,"
        " pg_size_pretty(pg_relation_size(relid)) AS heap"
        " FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 8"
    )
    await admin.close()

    engine = _stand_engine(database)
    await _seed_catalog(engine)
    captured: dict[str, list[tuple[str, tuple]]] = {}
    active = {"path": None}

    def before(conn, cursor, statement, parameters, context, executemany):
        if active["path"] and _captured_by_harness(statement):
            captured.setdefault(active["path"], []).append((statement, tuple(parameters)))

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    paths, setups, resets = _build_paths(), _build_setups(), _build_resets()
    ctx = await _context(engine)
    rows = []
    try:
        for name in path_names:
            if name == "discovery_page" and not ctx.get("cursor"):
                rows.append({"path": name, "error": "no cursor after rebuild"})
                continue
            setup = setups.get(name)
            if setup is not None:
                # Outside the measured window and outside the capture: putting the queue of a
                # thousand or fifty thousand rows together is stand setup, not the screen's work,
                # and timing it made the page that has nothing to show look like the price of the
                # rows the setup had just written.
                async with AsyncSession(bind=engine, expire_on_commit=False) as session:
                    try:
                        await setup(session, ctx)
                    except Exception as error:
                        await session.rollback()
                        rows.append({"path": name, "error": f"setup: {type(error).__name__}: {str(error)[:200]}"})
                        continue
            # Outside the measured window, and before every path rather than once per stand: the
            # rows a path is planned against include the ones the setup above wrote and the ones
            # the earlier paths left in the deck. Without this the exhausted page is timed on a
            # queue the statistics call empty — see `_settle_statistics`.
            await _settle_statistics(asyncpg, database)
            timings = []
            per_run: list[int] = []
            failure = None
            for _ in range(runs):
                reset = resets.get(name)
                if reset is not None:
                    # Between the repeats, outside the timer and outside the capture: the state the
                    # screen before this one leaves behind, put back so that the second call prices
                    # the same request as the first.
                    async with AsyncSession(bind=engine, expire_on_commit=False) as prep:
                        await reset(prep, ctx)
                    # The reset is the last thing that moved the rows this path is planned against,
                    # so the estimates are retaken after it — the same reason the call above the loop
                    # exists at all (see `_settle_statistics`).
                    await _settle_statistics(asyncpg, database)
                sent_before = len(captured.get(name, []))
                async with AsyncSession(bind=engine, expire_on_commit=False) as session:
                    active["path"] = name
                    started = time.perf_counter()
                    try:
                        await paths[name](session, ctx)
                        await session.commit()
                    except Exception as error:
                        await session.rollback()
                        failure = f"{type(error).__name__}: {str(error)[:200]}"
                    timings.append((time.perf_counter() - started) * 1000)
                    active["path"] = None
                per_run.append(len(captured.get(name, [])) - sent_before)
            if failure:
                rows.append({"path": name, "error": failure})
                continue
            rows.append(_row(name, timings, per_run))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)

    plans = await _plans(asyncpg, _asyncpg_dsn(database), captured)
    sessions = await _session_rows(asyncpg, database)
    scale = {
        "users": size,
        "viewer_passes": activity["passes"],
        "viewer_matches": activity["matches"],
        "crowd_matches": activity["crowd_matches"],
        "crowd_messages_per_match": activity["crowd_messages"],
        "refresh_tokens": sessions,
        "seed": seed,
        "tables": {r["relname"]: r["n_live_tup"] for r in tables},
        "sizes": {r["relname"]: {"total": r["total"], "heap": r["heap"]} for r in sizes},
        "paths": rows,
        "plans": plans,
    }

    print(f"\n=== {size} анкет, {activity['passes']} пропусков у зрителя ===", flush=True)
    print(f"строки: {scale['tables']}", flush=True)
    if verbose:
        print(f"размеры: {scale['sizes']}", flush=True)
    for row in rows:
        if "error" in row:
            print(f"  {row['path']:<20} ОШИБКА {row['error']}", flush=True)
        else:
            print(_format_row(row), flush=True)
    if verbose:
        for name, plan in plans.items():
            scan = plan.get("scan") or {}
            print(
                f"  план {name}: худший {plan['plan_ms']} мс, сумма по уникальным {plan['reads_sum_ms']} мс, "
                f"уникальных чтений {plan['distinct_reads']}, корень {plan['root']}, "
                f"строк {plan['rows']}, read {plan['read']}, hit {plan['hit']}",
                flush=True,
            )
            if scan:
                print(
                    f"      скан {scan['ms']} мс: {scan['node']} {scan['relation']}, "
                    f"строк {scan['rows']}, циклов {scan['loops']}, "
                    f"read {scan['read']}, hit {scan['hit']}",
                    flush=True,
                )
            print(f"    {plan['sql']}", flush=True)
    return scale


async def main() -> None:
    parser = argparse.ArgumentParser(description="Замер горячих путей BeFoS на синтетической базе.")
    parser.add_argument("--sizes", default="1000,10000")
    parser.add_argument("--database", default="befos_scale")
    parser.add_argument("--acted", type=int, default=0, help="пропуски зрителя (0 = 40%% от размера)")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--paths", default="")
    parser.add_argument(
        "--viewer-matches",
        type=int,
        default=0,
        help="пар у зрителя (0 = прежняя формула min(60, max(5, размер / 50)))",
    )
    parser.add_argument("--json", default="")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    import asyncpg

    if "DATABASE_URL" not in os.environ:
        raise SystemExit(
            "нужен DATABASE_URL, например "
            "postgresql+asyncpg://befos:befos_password@127.0.0.1:5432/befos"
        )
    if args.runs < 2:
        raise SystemExit(
            f"--runs {args.runs}: медиана и максимум берутся по повторам после первого вызова, "
            "поэтому повторов нужно минимум два"
        )

    known = list(_build_paths())
    wanted = _select_paths(known, args.paths)
    report = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "postgres": None, "scales": []}
    # The plan shape is what the document argues from, and the planner's choices belong to a
    # server version — a report without one cannot be reproduced by anyone else.
    maintenance = await asyncpg.connect(dsn=_asyncpg_dsn(MAINTENANCE_DB))
    try:
        report["postgres"] = (await maintenance.fetchval("SHOW server_version"))
    finally:
        await maintenance.close()
    for size_text in args.sizes.split(","):
        size = int(size_text)
        acted = args.acted or int(size * 0.4)
        report["scales"].append(
            await _measure_size(
                asyncpg, args.database, size, acted, args.runs, wanted, not args.quiet,
                args.viewer_matches,
            )
        )
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nотчёт: {args.json}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
