"""The engine's headline claim is one pair of answers -> one percent.

The trait mean is a sum of floats, and a float sum depends on the order the terms
are added in. Reading the terms straight out of a set makes that order a property
of hash randomisation rather than of the answers, so the same two profiles can
come out one point apart in two different processes.
"""

from __future__ import annotations

import itertools
import os
import subprocess
import sys
import uuid
from pathlib import Path

from app.compatibility.engine import CompatibilityInput, compute_compatibility
from app.recommendations.engine import ActivitySignal, UserSignal, score_activity
from app.repositories.test_repo import TestRepository as AnswerRepository
from .conftest import auth_headers, complete_onboarding, register_and_auth

BACKEND_DIR = str(Path(__file__).resolve().parents[1])

# Four answers per side. Their similarities are 0.60, 0.45, 0.40 and 0.53, which
# mean out at 0.495 — the percent sits exactly on the 49.5 rounding boundary.
VECTOR_A = {"values": {"family": 0.50, "career": 0.20, "growth": 0.90, "stability": 0.60}}
VECTOR_B = {"values": {"family": 0.10, "career": 0.75, "growth": 0.30, "stability": 0.13}}

_CHILD = (
    "import sys; sys.path.insert(0, @BACKEND@);"
    "from app.compatibility.engine import CompatibilityInput, compute_compatibility;"
    "va, vb = @A@, @B@;"
    "result = compute_compatibility("
    "CompatibilityInput(vector=va, interests={'x'}, dating_goal='relationship'), "
    "CompatibilityInput(vector=vb, interests={'x'}, dating_goal='relationship'));"
    "print(result.category('values').percent)"
)


def _values_percent_in_a_fresh_process(hash_seed: int) -> int:
    code = (
        _CHILD.replace("@BACKEND@", repr(BACKEND_DIR))
        .replace("@A@", repr(VECTOR_A))
        .replace("@B@", repr(VECTOR_B))
    )
    env = dict(os.environ, PYTHONHASHSEED=str(hash_seed))
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env
    )
    assert done.returncode == 0, done.stderr
    return int(done.stdout.strip())


def test_one_pair_of_answers_gets_one_percent_in_every_process():
    # Seeds 0 and 1 order these four trait keys differently, which used to be enough
    # to move the answer across the rounding boundary.
    assert _values_percent_in_a_fresh_process(0) == _values_percent_in_a_fresh_process(1)


def test_percent_does_not_depend_on_the_order_answers_arrive_in():
    keys = list(VECTOR_A["values"])
    percents = set()
    for permutation in itertools.permutations(keys):
        a = {k: VECTOR_A["values"][k] for k in permutation}
        b = {k: VECTOR_B["values"][k] for k in permutation}
        result = compute_compatibility(
            CompatibilityInput(vector=a, interests={"x"}, dating_goal="relationship"),
            CompatibilityInput(vector=b, interests={"x"}, dating_goal="relationship"),
        )
        percents.add(result.category("values").percent)
    assert len(percents) == 1


def test_recommendation_score_does_not_depend_on_the_order_answers_arrive_in():
    lifestyle = {
        "activity_level": (0.20, 0.75),
        "sleep_schedule": (0.50, 0.10),
        "health_focus": (0.90, 0.30),
        "social_frequency": (0.60, 0.13),
    }
    keys = list(lifestyle)
    scores = set()
    for permutation in itertools.permutations(keys):
        a = UserSignal(
            interests={"coffee"}, city="Москва", dating_goal="relationship",
            vector={"lifestyle": {k: lifestyle[k][0] for k in permutation}},
        )
        b = UserSignal(
            interests={"coffee"}, city="Москва", dating_goal="relationship",
            vector={"lifestyle": {k: lifestyle[k][1] for k in permutation}},
        )
        activity = ActivitySignal(
            activity_id=1, slug="cafe", title="Кофейня", category="culture",
            interests=["coffee"], cities=[], energy=0.3, social=0.8,
        )
        scores.add(score_activity(activity, a, b).score)
    assert len(scores) == 1


async def test_re_tapping_one_answer_does_not_reshuffle_the_others(client, session):
    # The vector is a mean over the answers, and a mean of floats follows the order of
    # its terms. An upsert writes a new tuple version, so without an explicit order the
    # re-tapped row comes back last and the same set of answers is summed differently.
    creds = await register_and_auth(client, "answer_order@befos.app")
    await complete_onboarding(client, creds["token"], name="Порядок")
    questions = (
        await client.get("/api/v1/tests", headers=auth_headers(creds["token"]))
    ).json()["questions"]
    answers = [
        {"question_id": q["id"], "option_id": q["options"][0]["id"]} for q in questions
    ]
    user_id = uuid.UUID(creds["user_id"])
    repo = AnswerRepository(session)

    await client.post(
        "/api/v1/tests/answers", json={"answers": answers}, headers=auth_headers(creds["token"])
    )
    before = [a.question_id for a in await repo.list_answers(user_id)]

    await client.post(
        "/api/v1/tests/answers",
        json={"answers": answers[:1]},
        headers=auth_headers(creds["token"]),
    )
    after = [a.question_id for a in await repo.list_answers(user_id)]

    assert len(after) == len(before)
    assert after == before
    assert after == sorted(after)
