from __future__ import annotations

"""The recommendation scale promises 100, and five numbers decide whether anything can reach it.

`score_activity` adds five weighted components and hands the total to `_clamp01`, so the page's
ceiling is exactly the sum of those weights: with `0.40 + 0.20 + 0.15 + 0.15 + 0.10 = 1.0`, a pair
that matches a card on every component is shown 100. Nothing stated that requirement for the
recommendation engine, while its sibling does: `app/compatibility/weights.py` calls
`WeightConfig.validate()` at import and raises when the seven weights miss 1.0 by more than 1e-6.
Both engines are published as a 0…100 scale, and only one of them checked its own arithmetic.

The gap is silent in both directions, and the two directions fail differently.

A weight lowered below the sum drops the ceiling and every score moves with it. Measured on the
engine before this stage: `leisure` 0.20 → 0.05 gave the maxed pair 0.85, shown as 85, and `goal`
0.10 → 0.00 gave 0.90, shown as 90. The best match the product can offer was described as a merely
good one, on a scale whose top is advertised as 100.

A weight raised above the sum cannot be seen through scores at all, because `_clamp01` saturates the
total. Measured the same way: `interest` 0.40 → 0.50 (sum 1.10) still returned 1.0, still 100, while
a pair that misses one component is now paid for a tenth of the scale that does not exist.

So the check belongs where both directions are visible — when the weights are read, not when a score
is computed. The table is therefore written in one place rather than kept as five constants beside a
copy: an edit to `W_LEISURE` after the import had finished checking a validated dict would have
changed the score and left the guard certifying numbers the engine no longer uses.
"""

import importlib.util
import pathlib
import sys
from typing import Any

import pytest

from app.recommendations import engine

ACTIVITY = engine.ActivitySignal(
    activity_id=1,
    slug="photo_walk",
    title="Прогулка с фотоаппаратом",
    category="outdoor",
    interests=["photography", "walks", "coffee"],
    cities=[],  # unrestricted, so location is 1.0 for any pair
    energy=0.4,
    social=0.6,
)


def _maxed_pair() -> tuple[engine.UserSignal, engine.UserSignal]:
    """The best pair the product can offer: every component of this card reads 1.0.

    The interests name the whole tag list, so coverage is full. The leisure vector is the card's own
    energy and social written back as the three traits `_leisure_match` compares, so that similarity
    is 1.0 by construction. Both halves answer alike, which makes the lifestyle comparison 1.0, and
    `relationship` × `relationship` is 1.0 in the goal table.
    """
    both = engine.UserSignal(
        interests=set(ACTIVITY.interests),
        vector={
            "leisure": {
                "outdoor": ACTIVITY.energy,
                "social_leisure": ACTIVITY.social,
                "relaxation": 1.0 - ACTIVITY.energy,
            },
            "lifestyle": {"smoking": 0.2, "drinking": 0.1, "sleep": 0.6, "fitness": 0.4},
        },
        city="Москва",
        dating_goal="relationship",
    )
    return both, both


def _engine_with_one_weight_changed(old: str, new: str) -> tuple[Any, Exception | None]:
    """Run the shipped engine's source with one weight edited, the way an import would run it.

    The edit is made to the file the product imports, not to a dict built beside it, because the
    guard is only worth anything if it fires on the real table at import time.
    """
    source = pathlib.Path(engine.__file__).read_text(encoding="utf-8")
    assert old in source, f"{old!r} is not in the weight table any more, so the edit cannot be made"
    spec = importlib.util.spec_from_loader("engine_with_an_edited_weight", loader=None)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before the body runs: `@dataclass` resolves the module it decorates through
    # `sys.modules`, so an unregistered copy would raise on the first class below the guard and the
    # assertion would pass on a broken exec rather than on a checked sum.
    sys.modules[module.__name__] = module
    try:
        exec(compile(source.replace(old, new, 1), "<edited engine>", "exec"), module.__dict__)
        return module, None
    except ValueError as exc:
        return module, exc
    finally:
        sys.modules.pop(module.__name__, None)


def test_the_weight_table_sums_to_the_scale_the_page_promises() -> None:
    """The invariant the ceiling rests on, stated once in the repository."""
    weights = engine.WEIGHTS
    assert set(weights) == {"interest", "leisure", "lifestyle", "location", "goal"}, (
        f"the table is keyed by {sorted(weights)}: `score_activity` multiplies exactly these five "
        "components, so an extra name is never read and a missing one raises on the first request "
        "instead of at import"
    )
    assert engine.validate_weights() == 1.0, (
        f"the five weights sum to {sum(weights.values())!r}: the pair that matches a card on every "
        "component is shown a percentage of that sum, not of the 100 the scale promises"
    )


def test_the_ceiling_of_the_scale_is_reachable() -> None:
    """What the guard exists to keep: a pair matching everything reads 100, not 95.

    Green on the shipped engine too, which is the point — the repair must not move the number any
    pair can already earn, and a change that did would fail here rather than only in the arithmetic
    above.
    """
    a, b = _maxed_pair()
    scored = engine.score_activity(ACTIVITY, a, b)
    assert scored.score == pytest.approx(1.0)
    assert scored.percent == 100


@pytest.mark.parametrize(
    ("old", "new", "total", "percent"),
    [
        ('    "leisure": 0.20,', '    "leisure": 0.05,', 0.85, 85),
        ('    "goal": 0.10,', '    "goal": 0.00,', 0.90, 90),
    ],
)
def test_a_weight_edited_below_the_sum_is_refused_at_import(old, new, total, percent) -> None:
    """One number off, and the import has to break instead of the page.

    The `percent` column is what the same pair scored on the pre-fix engine — 85 and 90, measured
    with the maxed pair above — for a product whose page still described the result on a scale up to
    100 and offered no way to tell the two states apart.
    """
    _module, error = _engine_with_one_weight_changed(old, new)
    assert error is not None, (
        f"an engine whose weights sum to {total} imports cleanly and returns {percent} as its top "
        "score: the ceiling is a property of that sum, so the sum is what has to be checked"
    )
    assert str(error) == f"Recommendation weights must sum to 1.0, got {total}", str(error)


def test_a_weight_edited_above_the_sum_is_invisible_through_scores() -> None:
    """Why the check cannot live where the score is computed: the clamp eats this direction whole.

    `interest` 0.40 → 0.50 puts the sum at 1.10, and the maxed pair still returns 1.0 and 100 —
    measured on the pre-fix engine that way. A reviewer comparing two pages sees nothing, while a
    pair that misses one component is now paid out of a tenth of the scale that does not exist.
    """
    _module, error = _engine_with_one_weight_changed('    "interest": 0.40,', '    "interest": 0.50,')
    assert error is not None, (
        "a sum above 1.0 imports cleanly; `_clamp01` then hides it in every score the engine returns"
    )
    assert str(error) == "Recommendation weights must sum to 1.0, got 1.1", str(error)

    a, b = _maxed_pair()
    clamped = engine._clamp01(1.10)
    assert clamped == 1.0, (
        "the saturation is what makes this direction invisible; if `_clamp01` ever stopped clamping, "
        "this test should stop claiming it does"
    )
    assert engine.score_activity(ACTIVITY, a, b).percent == 100


def test_the_score_multiplies_the_table_the_guard_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """The checked numbers and the used numbers have to be the same object.

    With `setitem` rather than a reimport, because this asserts wiring: the guard reads `WEIGHTS` and
    `score_activity` reads `WEIGHTS`, so an edit that fails the check is an edit that changes the
    page. Pre-fix, the two were separate: five constants the score read, and nothing that checked
    them.
    """
    a, b = _maxed_pair()
    assert engine.score_activity(ACTIVITY, a, b).percent == 100
    monkeypatch.setitem(engine.WEIGHTS, "leisure", 0.05)
    with pytest.raises(ValueError):
        engine.validate_weights()
    assert engine.score_activity(ACTIVITY, a, b).percent == 85
