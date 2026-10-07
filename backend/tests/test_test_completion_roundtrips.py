"""Finishing the test read the same answers twice, and the question list counted what it had listed.

``POST /tests/complete`` rebuilt the compatibility profile from the stored answers and then built
the same vector again to answer with — counting the statements of the request on a fresh account
gave 15 of them, three of which re-read the answer rows, the question rows and the option rows the
recompute had just read. ``GET /tests`` listed the whole catalog and then asked the database how
many active questions there were, next to the read that had returned them (5 statements, one of
them that count).

The bounds below are about that repetition. What the two requests answer is checked against the
engine reading the stored answers from scratch, and the unfinished-test refusal is checked to
write neither the vector nor the scores — so the saving cannot be bought by reporting less.
"""

from __future__ import annotations

import uuid
from typing import Callable

from httpx import AsyncClient
from sqlalchemy import event

from app.core.database import engine
from app.repositories.test_repo import TestRepository as AnswerRepository
from app.services.test_service import TestService as AnswerService

from .conftest import auth_headers, complete_onboarding, register_and_auth

_ANSWER_ROW = "select test_answers.id, test_answers.user_id, test_answers.question_id"
_QUESTION_LOADER = "select test_questions.id as test_questions_id"
_OPTION_LOADER = "select test_options.id as test_options_id"


def _count_of(seen: list[str], prefix: str) -> int:
    return sum(1 for statement in seen if statement.startswith(prefix))


async def _counted(client: AsyncClient, coro):
    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    listener: Callable[..., None] = record
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        resp = await coro
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    return resp, seen


async def _answered_account(client: AsyncClient, email: str) -> tuple[dict, list[dict]]:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"])
    resp = await client.get("/api/v1/tests", headers=auth_headers(creds["token"]))
    assert resp.status_code == 200, resp.text
    questions = resp.json()["questions"]
    resp = await client.post(
        "/api/v1/tests/answers",
        json={
            "answers": [
                {"question_id": q["id"], "option_id": q["options"][0]["id"]} for q in questions
            ]
        },
        headers=auth_headers(creds["token"]),
    )
    assert resp.status_code == 200, resp.text
    return creds, questions


async def test_completion_reads_the_stored_answers_once(client: AsyncClient) -> None:
    """The recompute hands its result to the response instead of the response reading again."""
    creds, _ = await _answered_account(client, "s22_complete@befos.app")

    resp, seen = await _counted(
        client, client.post("/api/v1/tests/complete", headers=auth_headers(creds["token"]))
    )
    assert resp.status_code == 200, resp.text

    assert _count_of(seen, _ANSWER_ROW) == 1, "the answer rows were read more than once"
    assert _count_of(seen, _QUESTION_LOADER) == 1, "the question rows were read more than once"
    assert _count_of(seen, _OPTION_LOADER) == 1, "the option rows were read more than once"
    # Two counts for the "is it finished" gate, the reads above, and the fan-out that the
    # changed answers invalidate: the deck, the activity pages and the percents on the pairs.
    assert len(seen) <= 12, f"{len(seen)} trips to the database to finish a test"


async def test_completion_reports_what_the_engine_computes(client: AsyncClient, session) -> None:
    """Fewer reads, same numbers: the scores still match a build from the stored answers."""
    creds, _ = await _answered_account(client, "s22_scores@befos.app")

    resp, _ = await _counted(
        client, client.post("/api/v1/tests/complete", headers=auth_headers(creds["token"]))
    )
    assert resp.status_code == 200, resp.text
    reported = {row["category"]: row["score"] for row in resp.json()["categories"]}

    _, expected = await AnswerService(session).build_vector(uuid.UUID(creds["user_id"]))
    assert reported == {key: int(round(value * 100)) for key, value in expected.items()}
    stored = await AnswerRepository(session).list_results(uuid.UUID(creds["user_id"]))
    assert {row.category for row in stored} == set(reported)


async def test_an_unfinished_test_is_still_refused(client: AsyncClient) -> None:
    """The gate that used to cost two counts and three reads still gates on the counts."""
    creds = await register_and_auth(client, "s22_gate@befos.app")
    await complete_onboarding(client, creds["token"])
    resp = await client.get("/api/v1/tests", headers=auth_headers(creds["token"]))
    questions = resp.json()["questions"]
    resp = await client.post(
        "/api/v1/tests/answers",
        json={
            "answers": [
                {"question_id": q["id"], "option_id": q["options"][0]["id"]}
                for q in questions[: max(1, len(questions) // 2)]
            ]
        },
        headers=auth_headers(creds["token"]),
    )
    assert resp.status_code == 200, resp.text

    resp, seen = await _counted(
        client, client.post("/api/v1/tests/complete", headers=auth_headers(creds["token"]))
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "validation_error"
    # The refusal happens before the recompute, so it writes neither the vector nor the scores.
    assert not any(statement.startswith("insert into compatibility_profiles") for statement in seen)
    assert not any(statement.startswith("insert into test_results") for statement in seen)
    assert not any(statement.startswith("delete from test_results") for statement in seen)


async def test_the_question_list_counts_what_it_sends(client: AsyncClient) -> None:
    """The catalog size comes from the rows the response carries, not from a second read."""
    creds = await register_and_auth(client, "s22_list@befos.app")
    await complete_onboarding(client, creds["token"])

    resp, seen = await _counted(
        client, client.get("/api/v1/tests", headers=auth_headers(creds["token"]))
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total"] == len(body["questions"])
    assert not _count_of(seen, "select count(test_questions.id)")
    assert len(seen) <= 4, f"{len(seen)} trips to the database to list the catalog"
