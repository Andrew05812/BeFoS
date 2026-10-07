"""The test submission is the widest write path a new user takes, and it was paid for per answer.

The Android client sends the whole answer map in one POST when the last question is tapped, and
the route accepts a batch. ``save_answers`` nonetheless walked the batch one item at a time: it
read the named question with its options (2 statements), then wrote that single answer with its
own UPSERT (1 statement). Counting the statements of a full 21-answer submission on a fresh
account gave 79 of them, 63 of which belonged to the loop — 3 per answer. The recompute that
follows a save is a fixed cost, so the loop was the whole growth of the path.

The bounds below are about that growth. A batch is now validated against one read of the catalog
and written in one statement, so the request costs the same whether it carries 5 answers or 21.
Each count is paired with the answer staying the same: the refusals still refuse, a question
named twice still keeps the last tap, and the category rows still hold what the engine computes
from the stored answers.
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Callable

from httpx import AsyncClient
from sqlalchemy import event

from app.core.database import engine
from app.repositories.test_repo import TestRepository as AnswerRepository
from app.services.test_service import TestService as AnswerService

from .conftest import auth_headers, complete_onboarding, register_and_auth

_MARKERS = {
    "question": "test_questions",
    "option": "test_options",
    "answer": "test_answers",
    "result": "test_results",
}


def _listener(seen: list[tuple[str, str]]) -> Callable[..., None]:
    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append((" ".join(statement.lower().split()), str(parameters)))

    return _record


def _reads(seen: list[tuple[str, str]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for statement, _ in seen:
        for name, marker in _MARKERS.items():
            if marker in statement:
                counts[name] += 1
    return counts


def _writes(seen: list[tuple[str, str]], table: str) -> int:
    prefix = f"insert into {table}"
    return sum(1 for statement, _ in seen if statement.startswith(prefix))


async def _account(client: AsyncClient, email: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"])
    return creds


async def _catalog(client: AsyncClient, token: str) -> list[dict]:
    resp = await client.get("/api/v1/tests", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["questions"]


async def _counted(client: AsyncClient, coro):
    seen: list[tuple[str, str]] = []
    listener = _listener(seen)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        resp = await coro
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    return resp, seen


def _body(questions: list[dict], option_index: int = 0) -> list[dict]:
    return [
        {"question_id": q["id"], "option_id": q["options"][option_index]["id"]}
        for q in questions
    ]


async def test_a_full_batch_is_read_and_written_in_a_handful_of_statements(
    client: AsyncClient,
) -> None:
    """Twenty-one answers, one catalog read, one INSERT — and the progress still says 21."""
    creds = await _account(client, "s21_full@befos.app")
    questions = await _catalog(client, creds["token"])
    assert len(questions) >= 15, "the demo catalog is too small to prove a batch"

    resp, seen = await _counted(
        client,
        client.post(
            "/api/v1/tests/answers",
            json={"answers": _body(questions)},
            headers=auth_headers(creds["token"]),
        ),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answered"] == body["total"] == len(questions)

    counts = _reads(seen)
    # One read of the named questions and their options, then the recompute's own batched
    # read of the stored answers, then the two counts that build the progress it answers with.
    assert counts["question"] == 3, f"questions read {counts['question']} times"
    assert counts["option"] == 2, f"options read {counts['option']} times"
    assert _writes(seen, "test_answers") == 1, (
        "the batch was written one UPSERT per answer"
    )
    # The loop used to add three statements per answer; the rest of the path is fixed.
    # Measured on this tree: 15 statements — 3 catalog reads, 1 INSERT for the answers,
    # the recompute's 9, and the 2 counts that build the progress in the answer.
    assert len(seen) <= 16, f"{len(seen)} trips to the database to store a batch"


async def test_the_submission_does_not_grow_with_the_batch(client: AsyncClient) -> None:
    """Five answers and twenty-one cost the same number of trips.

    This is the property the loop broke: the price of the request used to be a function of how
    many answers it carried.
    """
    small = await _account(client, "s21_small@befos.app")
    full = await _account(client, "s21_full_batch@befos.app")
    questions = await _catalog(client, full["token"])

    resp, small_seen = await _counted(
        client,
        client.post(
            "/api/v1/tests/answers",
            json={"answers": _body(questions[:5])},
            headers=auth_headers(small["token"]),
        ),
    )
    assert resp.status_code == 200, resp.text
    resp, full_seen = await _counted(
        client,
        client.post(
            "/api/v1/tests/answers",
            json={"answers": _body(questions)},
            headers=auth_headers(full["token"]),
        ),
    )
    assert resp.status_code == 200, resp.text

    assert len(small_seen) == len(full_seen), (
        f"a batch of 5 costs {len(small_seen)} and of {len(questions)} costs {len(full_seen)}"
    )
    assert _writes(small_seen, "test_answers") == 1
    assert _writes(full_seen, "test_answers") == 1


async def test_a_batch_naming_one_impossible_option_writes_nothing(
    client: AsyncClient, session
) -> None:
    """The whole body is checked before the first row is written, so a refusal keeps the old answers."""
    creds = await _account(client, "s21_refuse@befos.app")
    questions = await _catalog(client, creds["token"])
    user_id = uuid.UUID(creds["user_id"])
    repo = AnswerRepository(session)

    resp = await client.post(
        "/api/v1/tests/answers",
        json={"answers": _body(questions)},
        headers=auth_headers(creds["token"]),
    )
    assert resp.status_code == 200, resp.text
    before = [(a.question_id, a.option_id) for a in await repo.list_answers(user_id)]

    bad = _body(questions[:3])
    bad.append(
        {
            "question_id": questions[4]["id"],
            "option_id": questions[5]["options"][0]["id"],
        }
    )
    resp, _ = await _counted(
        client,
        client.post(
            "/api/v1/tests/answers",
            json={"answers": bad},
            headers=auth_headers(creds["token"]),
        ),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "validation_error"

    after = [(a.question_id, a.option_id) for a in await repo.list_answers(user_id)]
    assert after == before, "a refused batch moved an answer"


async def test_a_question_answered_twice_in_one_batch_keeps_the_last_tap(
    client: AsyncClient, session
) -> None:
    """A body that repeats a question is the same tap twice, not a statement that fails.

    Postgres refuses an ON CONFLICT statement whose own rows collide, so the batch is collapsed
    before it reaches the database — last tap wins, exactly as two separate requests did.
    """
    creds = await _account(client, "s21_repeat@befos.app")
    questions = await _catalog(client, creds["token"])
    q = questions[0]
    user_id = uuid.UUID(creds["user_id"])

    body = [
        {"question_id": q["id"], "option_id": q["options"][0]["id"]},
        {"question_id": q["id"], "option_id": q["options"][1]["id"]},
    ]
    resp, seen = await _counted(
        client,
        client.post("/api/v1/tests/answers", json={"answers": body}, headers=auth_headers(creds["token"])),
    )
    assert resp.status_code == 200, resp.text
    assert _writes(seen, "test_answers") == 1

    answers = await AnswerRepository(session).list_answers(user_id)
    assert len(answers) == 1
    assert answers[0].option_id == q["options"][1]["id"]


async def test_an_impossible_batch_size_is_refused_before_the_driver(
    client: AsyncClient, session
) -> None:
    """A body longer than the whole catalog is not a test submission, and it says so at the entry.

    The batch is validated in one read whose parameters are the ids the body names, and written in
    one statement whose parameters are its rows. A bound on the body is what keeps both bounded.
    """
    creds = await _account(client, "s21_oversize@befos.app")
    questions = await _catalog(client, creds["token"])
    body = _body(questions) * 30

    resp, seen = await _counted(
        client,
        client.post(
            "/api/v1/tests/answers",
            json={"answers": body},
            headers=auth_headers(creds["token"]),
        ),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "validation_error"
    assert _writes(seen, "test_answers") == 0
    assert await AnswerRepository(session).list_answers(uuid.UUID(creds["user_id"])) == []


async def test_the_categories_are_written_in_one_statement(
    client: AsyncClient, session
) -> None:
    """One INSERT for the result rows, holding the same scores the engine computes."""
    creds = await _account(client, "s21_categories@befos.app")
    questions = await _catalog(client, creds["token"])

    resp, seen = await _counted(
        client,
        client.post(
            "/api/v1/tests/answers",
            json={"answers": _body(questions, option_index=1)},
            headers=auth_headers(creds["token"]),
        ),
    )
    assert resp.status_code == 200, resp.text

    written = await AnswerRepository(session).list_results(uuid.UUID(creds["user_id"]))
    _, expected = await AnswerService(session).build_vector(uuid.UUID(creds["user_id"]))
    assert _writes(seen, "test_results") == 1, (
        "the result rows were written one INSERT per category"
    )
    assert len(written) == len(expected)
    assert {r.category for r in written} == set(expected)
    for row in written:
        assert abs(float(row.score) - expected[row.category]) < 1e-9
