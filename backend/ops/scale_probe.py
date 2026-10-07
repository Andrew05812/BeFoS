"""Measure the hot read paths against a synthetic population, at several scales.

The numbers in `docs/SCALE_PLAN.md` come from this script. It creates a throwaway database
(`befos_scale`), brings it to the current schema with Alembic, fills it with a generated
population, and then drives the *real* service objects — the same classes the API calls — while
timing each call. Every SELECT the path sent is then replayed under
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

# The vector shape is what the engine reads; the trait keys come from
# app/compatibility/traits.py and values stay inside 0..1 like a real questionnaire leaves them.
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
            INSERT INTO users (id, email, password_hash, is_active, is_verified, is_deleted, created_at, updated_at)
            SELECT gen_random_uuid(), 'scale_' || g || '@befos.test', $1::text,
                   true, true, false, now() - make_interval(mins => g), now() - make_interval(mins => g)
            FROM generate_series(1, $2::int) g
            ON CONFLICT DO NOTHING
            """,
            password_hash,
            size,
        )
        await conn.execute(
            """
            INSERT INTO users (id, email, password_hash, is_active, is_verified, is_deleted, created_at, updated_at)
            VALUES (gen_random_uuid(), $1, $2, true, true, false, now(), now())
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


def _build_paths():
    """One wrapper per screen: each calls the same service object the API route calls."""
    from app.services.auth_service import AuthService
    from app.services.chat_service import ChatService
    from app.services.compatibility_service import CompatibilityService
    from app.services.discovery_service import DiscoveryService
    from app.services.matches_service import MatchesService

    async def login(session, ctx):
        await AuthService(session).authenticate(ctx["viewer_email"], PASSWORD)

    async def public_profile(session, ctx):
        await DiscoveryService(session).get_public_profile(ctx["viewer_id"], ctx["peer_id"])

    async def discovery_rebuild(session, ctx):
        from app.repositories.social_repo import DiscoveryRepository

        await DiscoveryRepository(session).deck_invalidate(ctx["viewer_id"])
        page = await DiscoveryService(session).feed(ctx["viewer_id"], limit=DECK_SIZE)
        ctx["cursor"] = page.get("next_cursor")

    async def discovery_page(session, ctx):
        await DiscoveryService(session).feed(ctx["viewer_id"], limit=DECK_SIZE, cursor=ctx.get("cursor"))

    async def matches_list(session, ctx):
        await MatchesService(session).list_matches(ctx["viewer_id"])

    async def compatibility(session, ctx):
        await CompatibilityService(session).explain_pair(ctx["viewer_id"], ctx["peer_id"])

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
        from app.repositories.test_repo import TestRepository
        from app.services.test_service import TestService

        # The whole map in one call, because that is the shape the client sends it in: the
        # app posts every answer when the last question is tapped.
        questions = await TestRepository(session).list_active_questions()
        rows = [
            {"question_id": q.id, "option_id": q.options[0].id} for q in questions
        ]
        await TestService(session).save_answers(ctx["viewer_id"], rows)

    async def test_complete(session, ctx):
        from app.services.test_service import TestService

        # The screen after the last answer: the gate, then the same recompute the submission
        # just did. Measured on the answered-through viewer, so it costs a completion, not a
        # refusal.
        await TestService(session).complete(ctx["viewer_id"])

    return {
        "login": login,
        "public_profile": public_profile,
        "discovery_rebuild": discovery_rebuild,
        "discovery_page": discovery_page,
        "matches_list": matches_list,
        "compatibility": compatibility,
        "chat_history": chat_history,
        "recommendations": recommendations,
        "answers_submit": answers_submit,
        "test_complete": test_complete,
    }


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

    async with AsyncSession(bind=engine) as session:
        viewer = await session.scalar(text("SELECT id FROM users WHERE email = :e"), {"e": VIEWER_EMAIL})
        peer = await session.scalar(
            text("SELECT u.id FROM users u JOIN profiles p ON p.user_id = u.id "
                 "WHERE u.email ~ '^scale_[0-9]+@befos.test$' ORDER BY u.email LIMIT 1")
        )
        match_id = await session.scalar(
            text("SELECT id FROM matches WHERE user_a_id = :v ORDER BY created_at DESC LIMIT 1"),
            {"v": viewer},
        )
    return {"viewer_email": VIEWER_EMAIL, "viewer_id": viewer, "peer_id": peer, "match_id": match_id}


_WRITING = re.compile(r"\b(insert|update|delete)\b", re.IGNORECASE)


def _walk(node: dict):
    yield node
    for child in node.get("Plans", ()):
        yield from _walk(child)


def _read_only(sql: str) -> bool:
    """EXPLAIN ANALYZE runs the statement, so a write must never be replayed.

    The capture filter takes anything starting with S or W, and `W` also matches the
    `WITH … INSERT` the discovery queue is written with. Column names like `updated_at`
    are one word, so the boundary in `\\bupdate\\b` does not catch them.
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


async def _measure_size(asyncpg, database: str, size: int, acted: int, runs: int,
                        path_names: list[str], verbose: bool) -> dict:
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.core.security import hash_password

    await _recreate_database(asyncpg, database)
    _upgrade_schema(database)
    seed = await _seed(asyncpg, database, size, hash_password(PASSWORD))
    activity = await _seed_activity(
        asyncpg, database, acted, matches=min(60, max(5, size // 50)), messages=120,
        crowd_matches=size // 10, crowd_messages=8,
    )

    admin = await asyncpg.connect(dsn=_asyncpg_dsn(database))
    await admin.execute("ANALYZE")
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

    engine = create_async_engine(_sqlalchemy_url(database), pool_size=5)
    await _seed_catalog(engine)
    captured: dict[str, list[tuple[str, tuple]]] = {}
    active = {"path": None}

    def before(conn, cursor, statement, parameters, context, executemany):
        if active["path"] and statement.lstrip()[:1].lower() in ("s", "w"):
            captured.setdefault(active["path"], []).append((statement, tuple(parameters)))

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    paths = _build_paths()
    ctx = await _context(engine)
    rows = []
    try:
        for name in path_names:
            if name == "discovery_page" and not ctx.get("cursor"):
                rows.append({"path": name, "error": "no cursor after rebuild"})
                continue
            timings = []
            failure = None
            for _ in range(runs):
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
            if failure:
                rows.append({"path": name, "error": failure})
                continue
            rows.append(
                {
                    "path": name,
                    "median_ms": round(statistics.median(timings), 1),
                    "max_ms": round(max(timings), 1),
                    # captured accumulates across the runs of this path; the reader wants one pass.
                    "statements_per_call": round(len(captured.get(name, [])) / runs, 1),
                }
            )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)

    plans = await _plans(asyncpg, _asyncpg_dsn(database), captured)
    scale = {
        "users": size,
        "viewer_passes": activity["passes"],
        "viewer_matches": activity["matches"],
        "crowd_matches": activity["crowd_matches"],
        "crowd_messages_per_match": activity["crowd_messages"],
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
            print(
                f"  {row['path']:<20} медиана {row['median_ms']:>8.1f} мс   max {row['max_ms']:>8.1f} мс"
                f"   запросов за вызов {row['statements_per_call']}",
                flush=True,
            )
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
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--paths", default="")
    parser.add_argument("--json", default="")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    import asyncpg

    if "DATABASE_URL" not in os.environ:
        raise SystemExit(
            "нужен DATABASE_URL, например "
            "postgresql+asyncpg://befos:befos_password@127.0.0.1:5432/befos"
        )

    known = list(_build_paths())
    wanted = [p for p in (args.paths.split(",") if args.paths else known) if p in known]
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
            await _measure_size(asyncpg, args.database, size, acted, args.runs, wanted, not args.quiet)
        )
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nотчёт: {args.json}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
