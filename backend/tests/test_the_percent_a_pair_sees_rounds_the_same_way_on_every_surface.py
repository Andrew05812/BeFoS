"""One number, one rule: the percent a pair reads must not depend on who printed it.

The engine used Python's ``round`` for ``CategoryScore.percent`` and ``overall_percent``, which
sends a tie to the even neighbour: 12.5 became 12. The map's own sentences already refused that
behaviour — ``universe._percent`` rounds half up "because that is what the client does", and the
phone prints ``(sweep.value * 100).roundToInt()``, which sends 12.5 to 13. So the same 0.125 of a
band could read 12 % on the compatibility screen and 13 % in the sentence underneath it.

This row pins the single rule down: half always goes up, on every surface, and the phone's own
rounding site stays the rule the backend matches instead of drifting away from it.
"""

from __future__ import annotations

import pathlib

import pytest

from app.compatibility.engine import CategoryScore, CompatibilityResult, to_percent
from app.compatibility.universe import _percent

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PHONE_SCORE = _ROOT / "android/app/src/main/java/app/befos/core/designsystem/Components.kt"


@pytest.mark.parametrize("value", [0.0, 0.125, 0.375, 0.5, 0.625, 0.875, 1.0])
def test_the_engine_and_the_map_print_the_same_number(value: float) -> None:
    assert to_percent(value) == int(_percent(value)), (value, to_percent(value), _percent(value))


@pytest.mark.parametrize("value,expected", [(0.125, 13), (0.375, 38), (0.625, 63), (0.875, 88)])
def test_a_half_always_goes_up_the_way_the_mark_next_to_it_does(value: float, expected: int) -> None:
    assert to_percent(value) == expected


def test_a_band_and_the_whole_result_round_like_each_other() -> None:
    band = CategoryScore(key="values", label="Ценности", score=0.125, weight=0.25, has_data=True)
    result = CompatibilityResult(overall=0.625, categories=(band,), version=1)
    assert band.percent == 13
    assert result.overall_percent == 63


def test_a_number_outside_the_scale_is_clamped_before_it_is_printed() -> None:
    assert to_percent(-0.2) == 0
    assert to_percent(1.4) == 100
    assert to_percent(float("nan")) == 0


def test_the_phone_still_rounds_the_way_the_backend_now_does() -> None:
    """The claim is about the phone's rule, so the check reads the phone.

    ``CompatibilityScore`` animates a 0..1 sweep and prints the frame's number; that expression is
    the rule the backend has to match. If it changes shape, this check goes red and the two files
    get reconciled on purpose rather than by accident.
    """
    line = next((row for row in _PHONE_SCORE.read_text(encoding="utf-8").splitlines()
                 if "roundToInt()" in row and "* 100" in row), "")
    assert line.strip().startswith("val shown ="), f"the phone's print moved: {line!r}"
