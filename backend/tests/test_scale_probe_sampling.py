"""The stand must not mix the cold first call of a path into the numbers of the page.

`backend/ops/scale_probe.py` times the same path several times and publishes a median and a
maximum over all of those calls. Measured on 2026-10-09 the calls are not one sample: at a stand
of 1 001 profiles the first call of `public_profile` cost 124.0 ms while the four that followed
cost 25.5…30.4 ms, and at 50 000 profiles the first call of `deck_exhausted` cost 55 472.8 ms
while the next four cost 255.7…290.3 ms — 190 times more. The same path, the same statements, the
same stand: at 50 000 the maximum column the harness published for that path (55 118.0 ms, stage
42) was the first call, and the median (355.0 ms) was a warmed one. A trigger reading the maximum
therefore watched the warming of a cold cache, never the page.

These checks hold the split: the row keeps the sample it was built from, reports the first call as
its own number, and takes the median and the maximum over the calls that came after it.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

_PROBE_PATH = Path(__file__).resolve().parents[1] / "ops" / "scale_probe.py"


def _probe():
    """Load the stand as a module: it is a script, so it is not on the import path."""
    spec = importlib.util.spec_from_file_location("scale_probe", _PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# One cold call and three warm ones, in the shape the 50 000 stand gave on 2026-10-09
# (`deck_exhausted`: 55 472.8 ms, then 290.3 / 287.8 / 255.7 / 264.3 ms).
_COLD_FIRST = [900.0, 30.0, 20.0, 10.0]


def test_the_first_call_is_not_the_page() -> None:
    """The cold call gets its own number instead of becoming the maximum of the page."""
    row = _probe()._row("deck_exhausted", _COLD_FIRST, 40, 4)
    assert row["first_ms"] == 900.0, row
    assert row["max_ms"] == 30.0, (
        f"максимум страницы {row['max_ms']} ms: the maximum of the sample is the first call, which "
        "the server pays once per path and no reader of the table can attribute to the screen"
    )
    assert row["median_ms"] == 20.0, (
        f"медиана {row['median_ms']} ms is taken over a sample that still holds the cold call"
    )


def test_the_row_keeps_the_sample_it_was_built_from() -> None:
    """A published number a reader cannot re-derive from the run is not a measurement."""
    row = _probe()._row("public_profile", _COLD_FIRST, 20, 4)
    assert row["timings"] == _COLD_FIRST, row
    assert row["statements_per_call"] == 5.0, (
        f"{row['statements_per_call']} запросов за вызов: the capture accumulates over all four "
        "calls, so the row of one call divides by their number"
    )


def test_one_call_is_not_a_sample() -> None:
    """A run of one call has no warmed repeat to take a median over, and must say so."""
    try:
        _probe()._row("matches_list", [70.3], 5, 1)
    except ValueError:
        return
    raise AssertionError("a single timed call produced a median: that median is the cold call")


def test_the_measured_loop_has_no_second_place_where_the_sample_is_mixed() -> None:
    """Only `_row` turns timings into numbers, and the printed line carries both halves."""
    probe = _probe()
    loop = inspect.getsource(probe._measure_size)
    assert "_row(" in loop, "the timing loop builds its row somewhere other than `_row`"
    assert '"median_ms"' not in loop, (
        "the loop computes the median itself, so a second mixing site survived the split"
    )
    line = probe._format_row(probe._row("deck_exhausted", _COLD_FIRST, 40, 4))
    assert "900.0" in line and "30.0" in line, (
        f"the printed row hides one half of the sample: {line}"
    )
    assert "_format_row(" in loop, "the loop prints rows it did not pass through `_format_row`"
