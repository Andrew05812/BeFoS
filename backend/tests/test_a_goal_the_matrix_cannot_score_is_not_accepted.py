"""One vocabulary, six copies, and a score that read a missing answer as a maximal disagreement.

The dating goal is the only compatibility input this repository writes down in six places at once:
the rows of ``_GOAL_COMPAT`` (``app/compatibility/traits.py``), its columns, ``VALID_GOALS``
(``app/services/profile_service.py``, the set a write is refused against), ``GOALS``
(``app/seed.py``), ``DatingGoal`` (``app/models/enums.py``) and ``DatingGoalLabels``
(``android/.../presentation/common/Labels.kt``, which turns a stored code into the word the card
shows). Measured before this stage the six agree — one distinct set among them,
``probe_goal_vocabulary.txt``
— and nothing held them there. A goal added to the accepted set alone is accepted by the route,
stored, and scored ``0.0``: the probe pair differing only in that one answer read 68 % where the same
pair with a scored goal reads 72 % and with no answer at all 70 %, so the goal nobody scored was
treated as a worse disagreement than silence, and cost more than saying nothing.

The same comment-only promise sits one line above the table: «Symmetric. Same goals score 1.0». The
matrix is symmetric today — 25 cells, 0 asymmetric, diagonal 1.0 — and the engine is fed
requester-first (``CompatibilityService.score_inputs(a, b)`` with ``a`` the person asking), so the
first asymmetric cell would make the two partners see different percentages of the same pair, with
nothing failing anywhere.

The recommendation engine is where the convention gap is not a hypothesis. Its sibling treats an
absent answer as nothing to compare — ``NEUTRAL_SCORE`` with ``has_data=False``, the rule stage 60
applied to interests — while ``_goal_match`` calls ``goal_compatibility`` directly, which answers
``0.0`` for any pair it has no row for, including the empty string the signal builder itself uses
when a profile is missing. Measured: the same card a pair with two scored goals is shown 82 % is
shown 72 % when one side has no goal — a tenth of the scale, the whole ``goal`` weight, charged for
an answer that was never given.

What the checks below pin: the table is validated where it is read, so an asymmetric, incomplete,
off-diagonal or out-of-band edit is a broken import instead of a page; the accepted vocabulary is
that same table rather than a second list beside it; the refusal on the route names the goals the
server does carry; the other four copies agree with it, the Kotlin labels included; and a goal that
was not answered costs a recommendation card nothing.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys
from typing import Any

import pytest
from httpx import AsyncClient

from app.compatibility import traits
from app.models import enums
from app.recommendations import engine
from app.services import profile_service, safety_service

from .conftest import auth_headers, complete_onboarding, register_and_auth

# One of the five, and one that none of the six copies carries. The accepted half of every check
# below has to use the real names, because the fault being pinned is a name outside them.
_SCORED = "marriage"
_PHANTOM = "situational"

_KOTLIN_LABELS = (
    pathlib.Path(engine.__file__).parents[3]
    / "android/app/src/main/java/app/befos/presentation/common/Labels.kt"
)

ACTIVITY = engine.ActivitySignal(
    activity_id=1,
    slug="photo_walk",
    title="Прогулка с фотоаппаратом",
    category="outdoor",
    interests=["photography", "walks"],
    cities=[],
    energy=0.4,
    social=0.6,
)


def _pair(goal_a: str, goal_b: str) -> tuple[Any, Any]:
    """Two signals that differ from each other only in the goal they name.

    Everything ``score_activity`` else multiplies is held at the same value in all three cases, so a
    moved card is moved by ``_goal_match`` alone.
    """
    a = engine.UserSignal(interests={"photography"}, vector={}, city="Москва", dating_goal=goal_a)
    b = engine.UserSignal(interests={"photography"}, vector={}, city="Москва", dating_goal=goal_b)
    return a, b


def _compat_pair_score(goal_a: str, goal_b: str) -> float:
    from app.compatibility.engine import CompatibilityInput, compute_compatibility
    vector = {"values": {"family": 0.8}}
    a = CompatibilityInput(vector=vector, interests={"music"}, dating_goal=goal_a)
    b = CompatibilityInput(vector=vector, interests={"music"}, dating_goal=goal_b)
    return compute_compatibility(a, b).overall


def _traits_with_one_cell_edited(old: str, new: str) -> tuple[Any, Exception | None]:
    """Run the shipped module's source with one matrix cell edited, the way an import would run it.

    The edit goes into the file the product imports, not into a dict built beside it: the guard is
    only worth anything if it fires on the real table at import time.
    """
    source = pathlib.Path(traits.__file__).read_text(encoding="utf-8")
    assert old in source, f"{old!r} is no longer in the goal table, so the edit cannot be made"
    spec = importlib.util.spec_from_loader("traits_with_an_edited_goal_cell", loader=None)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    try:
        exec(compile(source.replace(old, new, 1), "<edited traits>", "exec"), module.__dict__)
        return module, None
    except ValueError as exc:
        return module, exc
    finally:
        sys.modules.pop(module.__name__, None)


def _kotlin_goal_labels() -> set[str]:
    text = _KOTLIN_LABELS.read_text(encoding="utf-8")
    block = text.split("val DatingGoalLabels = linkedMapOf(", 1)[1].split(")\n", 1)[0]
    return set(re.findall(r'"([a-z_]+)"\s+to', block))


def test_the_goal_matrix_is_validated_where_it_is_read() -> None:
    """The table is complete, symmetric, 1.0 on its diagonal and inside 0..1 — and checked at import."""
    cells = traits.validate_goal_matrix()
    rows = set(traits.GOAL_KEYS)
    assert cells == len(rows) * len(rows), (
        f"{cells} cells for {len(rows)} goals: every row has to name every column"
    )
    for goal_a in sorted(rows):
        for goal_b in sorted(rows):
            assert traits._GOAL_COMPAT[goal_a][goal_b] == traits._GOAL_COMPAT[goal_b][goal_a]
        assert traits._GOAL_COMPAT[goal_a][goal_a] == 1.0


def test_an_asymmetric_goal_cell_is_a_broken_import() -> None:
    """One cell leaned to one side, and the module refuses to load instead of the pair disagreeing.

    0.45 and 0.6 are the two numbers the shipped table carries for this pair today; leaning one of
    them is what an edit would look like. Pre-fix, the same edited module imports cleanly and the two
    viewers of one pair are handed different percentages, because the engine is fed requester-first.
    """
    _module, error = _traits_with_one_cell_edited(
        '"friendship": 0.45,', '"friendship": 0.60,',
    )
    assert error is not None, (
        "an asymmetric goal matrix imports cleanly: the comment above the table promises symmetry, "
        "and nothing else reads that promise"
    )
    message = str(error)
    assert "marriage" in message and "friendship" in message, message
    assert "0.45" in message and "0.6" in message, message


def test_a_goal_row_without_its_own_name_is_a_broken_import() -> None:
    """The diagonal is the scale's top: a goal that does not match itself is not a goal."""
    _module, error = _traits_with_one_cell_edited(
        '"marriage": {"marriage": 1.0,', '"marriage": {"marriage": 0.9,',
    )
    assert error is not None, "a matrix whose diagonal misses 1.0 imports cleanly"
    assert "marriage" in str(error), str(error)


def test_a_goal_row_that_does_not_name_every_column_is_a_broken_import() -> None:
    """A missing cell is the silent half of the same fault: ``table.get(goal_b, 0.0)`` answers 0.0."""
    _module, error = _traits_with_one_cell_edited(
        '"casual": 0.3, "networking": 0.3},', '"casual": 0.3},',
    )
    assert error is not None, (
        "a row that names four of the five columns imports cleanly, and the fifth goal it was asked "
        "about is scored 0.0 as though the answer had been read and found opposite"
    )
    assert "networking" in str(error), str(error)


def test_the_accepted_goals_are_the_scored_goals() -> None:
    """One vocabulary, not a list beside the table that decides what a goal is worth.

    Pre-fix these were two literals that happened to agree; the agreement is what the probe measured
    (one distinct set among six copies), and an accepted-but-unscored goal was worth 68 % against the
    72 % the same pair earns with a scored goal and the 70 % it earns with no answer at all.
    """
    assert profile_service.VALID_GOALS is traits.GOAL_KEYS, (
        "the set a write is refused against has to be the set the matrix scores, or a goal added to "
        "one of them is accepted by the route and charged as a maximal disagreement by the engine"
    )


def test_the_other_copies_of_the_vocabulary_agree() -> None:
    """The seed, the enum and the screen labels name the same five goals the table scores."""
    from app import seed

    rows = set(traits._GOAL_COMPAT)
    assert set(seed.GOALS) == rows, sorted(seed.GOALS)
    assert {member.value for member in enums.DatingGoal} == rows
    assert _kotlin_goal_labels() == rows, (
        "the card falls back to the stored code when the label map has no name for it, so a goal "
        "added on the server alone is shown to the user as its slug"
    )


def test_the_erased_goal_is_not_an_accepted_one() -> None:
    """The value a deleted account is anonymised to is outside the scored set, on purpose.

    It is what makes the erasure safe to leave in the row: measured against the three live bases on
    the morning this stage commits, the only off-matrix goal value among them is this one and every
    row carrying it sits on a deleted account — 236 on ``befos``, each with ``is_deleted = true``,
    none on ``befos_scale``, none on ``befos_test`` (``s70_final_erased.txt``, 00:51:59 UTC).
    And 0 of the pairs those bases report have a half whose profile row is missing
    (``s70_final_cards.txt``, 00:51:54…00:51:59 UTC), so the engine is never asked to score it.
    """
    assert safety_service.ERASED_DATING_GOAL not in traits._GOAL_COMPAT
    assert traits.goal_compatibility(safety_service.ERASED_DATING_GOAL, _SCORED) == 0.0


def test_an_unscored_goal_read_by_the_engine_costs_more_than_no_answer() -> None:
    """The ordering the two lists drifting apart would produce, held where it can be seen.

    Measured before this stage on the shipped engine: the pair 72 % with a scored goal, 70 % with
    none, 68 % with a goal the matrix has no row for. The last of the three is the fault — an answer
    nobody can score cannot be a worse disagreement than an answer that was not given.
    """
    scored = _compat_pair_score(_SCORED, _SCORED)
    silent = _compat_pair_score(_SCORED, "")
    phantom = _compat_pair_score(_SCORED, _PHANTOM)
    assert scored > silent > phantom, (scored, silent, phantom)
    assert _PHANTOM not in profile_service.VALID_GOALS, (
        "the route is what keeps this ordering out of the product: a goal it accepts has to be a "
        "goal the table scores"
    )


async def test_a_goal_the_matrix_cannot_score_is_refused_and_named(client: AsyncClient) -> None:
    """The write already refused an unknown goal; the refusal now says what the server does carry."""
    creds = await register_and_auth(client, "s70_refuse@befos.app")
    await complete_onboarding(client, creds["token"], interests=["hiking", "cinema"])

    resp = await client.patch(
        "/api/v1/users/me", json={"dating_goal": _PHANTOM}, headers=auth_headers(creds["token"])
    )

    assert resp.status_code == 422, resp.text
    body = resp.json()["error"]
    assert body["code"] == "validation_error", body
    message = body["message"]
    assert _PHANTOM in message, message
    for goal in sorted(traits.GOAL_KEYS):
        assert goal in message, f"{goal} missing from {message}"


async def test_every_scored_goal_is_accepted_by_the_route(client: AsyncClient) -> None:
    """The accepted set is not larger than the scored one and not smaller: all five round-trip."""
    creds = await register_and_auth(client, "s70_five@befos.app")
    await complete_onboarding(client, creds["token"], interests=["hiking", "cinema"])

    for goal in sorted(traits._GOAL_COMPAT):
        resp = await client.patch(
            "/api/v1/users/me", json={"dating_goal": goal}, headers=auth_headers(creds["token"])
        )
        assert resp.status_code == 200, f"{goal}: {resp.text}"
        assert resp.json()["dating_goal"] == goal


def test_an_unanswered_goal_costs_a_recommendation_card_nothing() -> None:
    """The convention the compatibility engine already keeps, applied to the card.

    Measured on the engine before this stage: the same card a pair with two scored goals is shown at
    82 % was shown at 72 % when one side named no goal at all — the whole ``goal`` weight charged for
    an answer that was never given, while ``_interest_match`` beside it returns 0.5 for exactly the
    same kind of silence.
    """
    a, b = _pair(_SCORED, _SCORED)
    top = engine.score_activity(ACTIVITY, a, b).score

    score, reasons = engine._goal_match(*_pair(_SCORED, ""))
    assert score == 0.5, score
    assert reasons == [], reasons

    silent, partner = _pair(_SCORED, "")
    card = engine.score_activity(ACTIVITY, silent, partner).score
    # Half of the goal band is what a neutral read costs against a matching one; the weight is read
    # from the same table the score multiplies, so the arithmetic cannot fall out of date silently.
    assert card == pytest.approx(top - 0.5 * engine.WEIGHTS["goal"]), (top, card)


def test_a_named_pair_keeps_the_number_the_table_gives_it() -> None:
    """The repair moves silence, not disagreement: two named goals score exactly as before."""
    a, b = _pair("casual", "networking")
    cell = traits._GOAL_COMPAT["casual"]["networking"]
    score, _reasons = engine._goal_match(a, b)
    assert score == cell

    top_a, top_b = _pair(_SCORED, _SCORED)
    top = engine.score_activity(ACTIVITY, top_a, top_b).score
    card = engine.score_activity(ACTIVITY, a, b).score
    assert card == pytest.approx(top - (1.0 - cell) * engine.WEIGHTS["goal"]), (top, cell, card)
