"""`docs/DEVELOPMENT_HISTORY.md` prints a count of stage headings; until now nothing read it.

Every stage from 114 on appended one sentence to the history document: "the same command on this
tree gives N", where N is the number of `### <stage>.` headings in `CHANGELOG.md`. The command is
printed, the number is printed, and the two had no guard: a stage could append its own sentence and
forget the arithmetic, or rename a heading, and the document would keep asserting a count the tree no
longer produced. Stage 124 measured this silence — 0 files of `backend/tests/` named the document at
all — and wrote that number into the release checklist rather than hiding it. This row is the debt
being paid: the claim is now checked against the file it counts.

Three things are pinned: the last printed number equals the real count, the printed numbers increase
by exactly one (one stage, one heading — the sentence's own promise), and the two exceptions the
document names are the tree's actual exceptions: `### 81.2.` is a fix inside stage 81, and stage 98
has no heading of its own because its change landed under 97.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_HISTORY = _ROOT / "docs/DEVELOPMENT_HISTORY.md"
_CHANGELOG = _ROOT / "CHANGELOG.md"

# The very command the document prints, kept here so the guard counts what a reader would count.
_HEADING = re.compile(r"^### (79|8[0-9]|9[0-9]|1[01][0-9]|12[0-9])\.", re.MULTILINE)
_PRINTED = re.compile(r"та же команда на нём даёт\s+(\d+)")


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_last_printed_count_is_the_count_the_tree_produces() -> None:
    printed = [int(number) for number in _PRINTED.findall(_text(_HISTORY))]
    assert printed, "история больше не печатает ни одной строки «та же команда на нём даёт»"
    actual = len(_HEADING.findall(_text(_CHANGELOG)))
    assert printed[-1] == actual, f"документ печатает {printed[-1]}, дерево даёт {actual}"


def test_each_stage_added_exactly_one_heading_over_the_previous_printed_count() -> None:
    printed = [int(number) for number in _PRINTED.findall(_text(_HISTORY))]
    steps = [(before, after) for before, after in zip(printed, printed[1:]) if after != before + 1]
    assert not steps, f"заголовок стадии прибавился не на один: {steps}"


def test_the_two_exceptions_the_document_names_are_the_exceptions_the_tree_has() -> None:
    changelog = _text(_CHANGELOG)
    history = _text(_HISTORY)
    inside_81 = len(re.findall(r"^### 81\.2\.", changelog, re.MULTILINE))
    stage_98 = len(re.findall(r"^### 98\.", changelog, re.MULTILINE))
    assert inside_81 == 1, f"`### 81.2.` встречается {inside_81} раз — история говорит «один»"
    assert stage_98 == 0, f"у стадии 98 появился заголовок ({stage_98}) — оговорку надо переписать"
    assert "`### 81.2.`" in history, "история перестала называть исключение 81.2"
    assert "= 0" in history, "история перестала печатать, что у стадии 98 заголовка нет"
