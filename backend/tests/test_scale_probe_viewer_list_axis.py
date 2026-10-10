"""The stand the scale table is published from cannot express the axis the pair list grows along.

`backend/ops/scale_probe.py` gives the viewer `min(60, max(5, size // 50))` pairs — 20 at 1 000
анкет, 60 at 10 000 and at 50 000 — and it seeds no photo at all (`grep -c "INSERT INTO photos"
ops/scale_probe.py` answers 0). `GET /api/v1/matches` puts no ceiling on its read
(`MatchesService.list_matches` has no `.limit()`, the route takes no query parameter), so every
`matches_list` number the table published was a short list of accounts without pictures: 29.8 /
37.2 / 34.3 мс (стадия 33), while the same code on a 1 000-pair list with two photos per partner
costs 276.7 мс — замер 2026-10-10, стенд `befos_s49`, 3 000 анкет. The waste stage 49 removed was
invisible to the harness for the same reason a cap hides an overflow: the axis was never sampled.

These checks hold both halves: the published default is not quietly rewritten, and the long-list
axis becomes a flag a reader can pass.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

_PROBE_PATH = Path(__file__).resolve().parents[1] / "ops" / "scale_probe.py"

# The three scales the published table is built from, with the list length each gave.
_PUBLISHED_SCALES = [(1_000, 20), (10_000, 60), (50_000, 60)]


def _probe():
    """Load the stand as a module: it is a script, so it is not on the import path."""
    spec = importlib.util.spec_from_file_location("scale_probe", _PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_published_default_list_length_is_unchanged() -> None:
    """The rows already in the document stay re-derivable: the default is the old formula."""
    probe = _probe()
    for size, pairs in _PUBLISHED_SCALES:
        assert probe._viewer_matches(size) == pairs, (
            f"{size} анкет давали список из {pairs} пар; на {size} теперь {_probe()._viewer_matches(size)}. "
            "Сдвиг молча переписывает каждую опубликованную строку таблицы, потому что вместе с "
            "этим числом меняются и пути, которые держат того же зрителя"
        )


def test_the_long_list_axis_can_be_asked_for() -> None:
    """The axis the screen grows along has to be expressible without editing the harness."""
    probe = _probe()
    assert probe._viewer_matches(3_000, 1_000) == 1_000, probe._viewer_matches(3_000, 1_000)
    assert probe._viewer_matches(3_000, 0) == probe._viewer_matches(3_000), (
        "нулевое значение должно означать прежнюю формулу, а не пустой список"
    )


def test_the_number_reaches_the_seed_it_names() -> None:
    """A flag that is parsed and then dropped measures the list it says it did not measure."""
    probe = _probe()
    seed = inspect.getsource(probe._seed_activity)
    assert "matches" in seed.splitlines()[0], "the seed takes the pair count from somewhere else"
    loop = inspect.getsource(probe._measure_size)
    assert "viewer_matches" in loop, (
        "`_measure_size` still writes the pair count inline, so the axis cannot be passed to it"
    )
    assert "min(60" not in loop, (
        "the ceiling still lives at the call site rather than in `_viewer_matches`, where the flag "
        "would have to override it"
    )


def test_the_command_line_names_the_axis() -> None:
    """Every published number has to be re-derivable by a command someone can type."""
    source = inspect.getsource(_probe().main)
    assert "--viewer-matches" in source, "the axis has no flag, so the long list stays unmeasurable"
