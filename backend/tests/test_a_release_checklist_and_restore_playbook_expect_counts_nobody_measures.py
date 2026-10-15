"""A release checklist and a restore playbook awaited counts no tree ever produced.

``docs/RELEASE.md`` §8 told the person who signs a release to expect «backend **191/191**, Android
**131/131**, живой путь **64/64** (замер 2026-10-06)» and to read the commands from ``README.md``,
«раздел «Testing»». ``docs/OPERATIONS.md`` §4 step 6 told whoever restores a lost copy to expect
«ожидание: 64/64». Both numbers were true on 2026-10-06 and stopped being true afterwards: the
Android suite got its first new methods in stage 63 and grew again through stage 72, the live path
grew a check in stage 63, and the backend suite has been re-measured on every stage since. README's
own command block carried the same disease one row closer to home — it commented the Android line
with 162 while the measurement table in the same file published 182.

The damage is not a cosmetic mismatch. A checklist is a promise an operator can only keep by
ticking a box: with «191/191» printed above a suite that answers 534 on the tree carrying this
check, either the number is ignored and the checklist stops gating, or the run looks broken and the
release stops. The restore playbook is worse, because the operator there has fewer options: 64/64
cannot be produced by any current tree, so a restored copy either fails a step that is actually
fine or teaches the operator to skip the one step that proves the data is readable.

``docs/VERIFICATION.md`` is where the numbers are actually measured. It became the carrier on stage
94, when ``README.md`` was rebuilt as the product's landing page and its «Тесты» narrative,
measurement table and commented command block moved out of it verbatim — a visitor reading README
has no business parsing per-stage shoot history, while an operator signing a release still needs one
place that says how each count was obtained. The document keeps one table row per suite, each naming
its count, the day it was measured, the UTC window and the artifact, and the checks below read that
table as the source and require the three imperative documents to expect exactly what it publishes,
so that the next stage cannot leave one of them behind again. The paragraph above that table is one
of the documents: until the tenth revision of stage 72 it mirrored the measured counts by hand and
had fallen a whole revision behind them.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_VERIFICATION = _ROOT / "docs" / "VERIFICATION.md"
_RELEASE = _ROOT / "docs" / "RELEASE.md"
_OPERATIONS = _ROOT / "docs" / "OPERATIONS.md"

# The three suites the documents make promises about, keyed by the command each is run with.
_BACKEND = "backend"
_ANDROID = "android"
_JOURNEY = "journey"
_COMMANDS = {
    _BACKEND: "cd backend && pytest",
    _ANDROID: "cd android && ./gradlew :app:testDebugUnitTest",
    _JOURNEY: "cd backend && python e2e_journey.py",
}

_VERIFICATION_HEADINGS = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.MULTILINE)
_TABLE_ROW = re.compile(r"^\| (?P<name>[^|]*) \| (?P<result>.*) \| `(?P<cmd>[^`]*)` \|$")
_PASSED_COUNT = re.compile(r"\*\*(\d+) passed, 0 failed\*\* — замер (\d{4}-\d{2}-\d{2})")
_JOURNEY_COUNT = re.compile(r"\*\*(\d+)\s*/\s*(\d+) проверок\*\* — замер (\d{4}-\d{2}-\d{2})")
_ARTIFACT = re.compile(r"`s\d\d_[a-z0-9_]+(?:\.\w+)?`")
_UTC_WINDOW = re.compile(r"\d\d:\d\d:\d\d…\d\d:\d\d:\d\d UTC")
_BLOCK_LINE = re.compile(r"^(?P<cmd>[^#]+?)\s+#\s*(?P<count>\d+)\b")
_RELEASE_CLAIM = re.compile(
    r"(?P<set>бэкенд|Android|живой путь) \*\*(?P<left>\d+)/(?P<right>\d+)\*\* "
    r"\(замер (?P<date>\d{4}-\d{2}-\d{2})\)"
)
_OPERATIONS_CLAIM = re.compile(
    r"ожидание: (?P<left>\d+)/(?P<right>\d+); замер (?P<date>\d{4}-\d{2}-\d{2})"
)
_SET_LABELS = {"бэкенд": _BACKEND, "Android": _ANDROID, "живой путь": _JOURNEY}


def _carrier_text() -> str:
    return _VERIFICATION.read_text(encoding="utf-8")


def _release_text() -> str:
    return _RELEASE.read_text(encoding="utf-8")


def _operations_text() -> str:
    return _OPERATIONS.read_text(encoding="utf-8")


def _section(text: str, marker: str) -> str:
    start = text.index(marker)
    tail = text[start + len(marker) :]
    end = tail.find("\n## ")
    return tail if end == -1 else tail[:end]


def _numbered_items(section: str) -> list[str]:
    """Each ``1.``-style entry of a prose list, continuation lines joined to it."""
    items: list[str] = []
    for line in section.splitlines():
        if re.match(r"^\d+\.\s", line):
            items.append(line)
        elif items and line.strip():
            items[-1] += " " + line.strip()
    return items


def _checklist_items(section: str) -> list[str]:
    """Each ``- [ ]`` entry of the section, continuation lines joined to it."""
    items: list[str] = []
    for line in section.splitlines():
        if line.startswith("- ["):
            items.append(line)
        elif items and line.strip():
            items[-1] += " " + line.strip()
    return items


def _measured_counts() -> dict[str, tuple[int, str]]:
    """Every count VERIFICATION's measurement table publishes, with the day it names beside it.

    The table is the only place in the repository that says how a number was obtained, so its rows
    are what the other documents have to agree with. A row that stops carrying a count, a date, an
    artifact or a UTC window is not read as a small number but as a missing measurement.
    """
    rows: dict[str, str] = {}
    for line in _carrier_text().splitlines():
        match = _TABLE_ROW.match(line)
        if not match or "`" not in line:
            continue
        for suite, command in _COMMANDS.items():
            if command in match.group("cmd"):
                rows[suite] = match.group("result")
    assert set(rows) == set(_COMMANDS), (
        f"VERIFICATION's table publishes rows for {sorted(rows)}; a suite lost its row, so its count "
        "has no source left"
    )

    counts: dict[str, tuple[int, str]] = {}
    for suite, cell in rows.items():
        pattern = _JOURNEY_COUNT if suite == _JOURNEY else _PASSED_COUNT
        claim = pattern.search(cell)
        assert claim, f"VERIFICATION's {suite} row no longer publishes «N passed»-style count and a date"
        numbers = claim.groups()[:-1]
        assert len(set(numbers)) == 1, (
            f"VERIFICATION's {suite} row says {numbers}: a suite cannot both pass two different counts"
        )
        assert _ARTIFACT.search(cell) and _UTC_WINDOW.search(cell), (
            f"VERIFICATION's {suite} row publishes {numbers[0]} without an artifact and a UTC window; "
            "an unattributed number is not a measurement"
        )
        counts[suite] = (int(numbers[0]), claim.group(len(numbers) + 1))
    return counts


def _command_block_lines() -> list[str]:
    """The command lines inside VERIFICATION's ``### Тесты`` fenced block, comments and all."""
    section = _section(_carrier_text(), "### Тесты")
    body = section.split("```", 2)
    assert len(body) >= 3, "VERIFICATION's «Тесты» section lost its fenced command block"
    return [line for line in body[1].splitlines() if _BLOCK_LINE.match(line.strip())]


def _command_block_counts() -> dict[str, int]:
    """The counts the ``### Тесты`` fenced block of VERIFICATION comments onto each command."""
    counts: dict[str, int] = {}
    for line in _command_block_lines():
        match = _BLOCK_LINE.match(line.strip())
        assert match
        for suite, command in _COMMANDS.items():
            if match.group("cmd").strip() == command:
                counts[suite] = int(match.group("count"))
    assert set(counts) == set(_COMMANDS), (
        f"the command block comments {sorted(counts)}; one of the three commands lost its number"
    )
    return counts


def _release_test_item() -> str:
    """The §8 line that makes the release depend on the three suites."""
    items = _checklist_items(_section(_release_text(), "## 8."))
    item = next((entry for entry in items if "Тесты" in entry.split(":")[0]), "")
    assert item, "RELEASE.md §8 no longer has a Тесты item; the release gate lost its expectation"
    return item


def _release_claims() -> dict[str, tuple[int, str]]:
    """The counts the release checklist tells the operator to expect, keyed by suite."""
    item = _release_test_item()
    claims = {
        match.group("set"): match for match in _RELEASE_CLAIM.finditer(item)
    }
    assert set(claims) == set(_SET_LABELS), (
        f"the checklist item names counts for {sorted(claims)}; it has to state all three suites"
    )
    out: dict[str, tuple[int, str]] = {}
    for label, match in claims.items():
        assert match.group("left") == match.group("right"), (
            f"the checklist expects {label} {match.group('left')}/{match.group('right')}: a suite "
            "is either green or it is not"
        )
        out[_SET_LABELS[label]] = (int(match.group("left")), match.group("date"))
    return out


def _operations_claim() -> tuple[int, str]:
    """The count the restore playbook awaits after ``pg_restore``."""
    items = _numbered_items(_section(_operations_text(), "## 4."))
    step = next((entry for entry in items if "e2e_journey.py" in entry), "")
    assert step, (
        "OPERATIONS.md §4 no longer runs the live path after a restore; the copy is proven by that "
        "run, not by a zero exit code"
    )
    match = _OPERATIONS_CLAIM.search(step)
    assert match, (
        f"the restore step awaits a count without a measurement date: {step}"
    )
    assert match.group("left") == match.group("right"), (
        f"the restore step awaits {match.group('left')}/{match.group('right')}"
    )
    return int(match.group("left")), match.group("date")


def _counter_claims() -> dict[str, tuple[int, str]]:
    """The counts VERIFICATION's own «Тесты» opening promises, keyed by suite.

    The paragraph above the table is the first thing a reader cites, and until stage 72's tenth
    revision it was the one place the table's numbers were mirrored by hand: it still promised the
    eighth revision's 528 while the row below it had been re-measured at 534. It therefore has to
    state all three suites in the same shape the release checklist does.
    """
    text = _carrier_text()
    paragraph = text[text.index("## Тесты") : text.index("| Набор | Результат |")]
    claims = {match.group("set"): match for match in _RELEASE_CLAIM.finditer(paragraph)}
    assert set(claims) == set(_SET_LABELS), (
        f"the opening of VERIFICATION's «Тесты» names counts for {sorted(claims)}; the paragraph above "
        "the table has to promise all three suites the table measures"
    )
    out: dict[str, tuple[int, str]] = {}
    for label, match in claims.items():
        assert match.group("left") == match.group("right"), (
            f"the opening expects {label} {match.group('left')}/{match.group('right')}: a suite "
            "is either green or it is not"
        )
        out[_SET_LABELS[label]] = (int(match.group("left")), match.group("date"))
    return out


def _divergences() -> list[str]:
    """Every place an imperative document promises a count the measurement table disagrees with."""
    measured = _measured_counts()
    out: list[str] = []
    for suite, (number, date) in _counter_claims().items():
        if number != measured[suite][0]:
            out.append(
                f"VERIFICATION «Тесты» opening: {suite} {number}, measured {measured[suite][0]}"
            )
        if date != measured[suite][1]:
            out.append(
                f"VERIFICATION «Тесты» opening: {suite} dates its count at {date}, the table measured "
                f"it on {measured[suite][1]}"
            )
    for suite, number in _command_block_counts().items():
        if number != measured[suite][0]:
            out.append(
                f"VERIFICATION command block: {suite} {number}, measured {measured[suite][0]}"
            )
    for suite, (number, date) in _release_claims().items():
        if number != measured[suite][0]:
            out.append(
                f"RELEASE.md §8: {suite} {number}, measured {measured[suite][0]}"
            )
        if date != measured[suite][1]:
            out.append(
                f"RELEASE.md §8: {suite} dates its count at {date}, the table measured it on "
                f"{measured[suite][1]}"
            )
    number, date = _operations_claim()
    if number != measured[_JOURNEY][0]:
        out.append(
            f"OPERATIONS.md §4: живой путь {number}, measured {measured[_JOURNEY][0]}"
        )
    if date != measured[_JOURNEY][1]:
        out.append(
            f"OPERATIONS.md §4: живой путь dates at {date}, the table measured it on "
            f"{measured[_JOURNEY][1]}"
        )
    return out


def test_the_measurement_table_publishes_a_count_with_a_date_and_a_run():
    counts = _measured_counts()
    assert counts[_BACKEND][0] > 0 and counts[_ANDROID][0] > 0 and counts[_JOURNEY][0] > 0, counts


def test_the_command_block_comments_the_counts_the_table_publishes():
    measured = _measured_counts()
    printed = _command_block_counts()
    for suite in _COMMANDS:
        assert printed[suite] == measured[suite][0], (
            f"the block tells the reader to expect {printed[suite]} for {suite} while the table in "
            f"the same file publishes {measured[suite][0]}"
        )


def test_the_counter_paragraph_promises_the_counts_the_table_publishes():
    measured = _measured_counts()
    promised = _counter_claims()
    for suite in _COMMANDS:
        assert promised[suite] == measured[suite], (
            f"the paragraph above the table promises {promised[suite]} for {suite} while the same "
            f"file measures {measured[suite]}"
        )


def test_the_release_checklist_expects_the_counts_the_table_publishes():
    assert _divergences() == [], " | ".join(_divergences())


def test_the_release_checklist_sends_the_operator_to_a_section_that_exists():
    line = _release_test_item()
    assert "VERIFICATION.md" in line, (
        "the checklist no longer says where the commands and the measurements live"
    )
    headings = {name.strip() for name in _VERIFICATION_HEADINGS.findall(_carrier_text())}
    named = re.findall(r"раздел\w* «([^»]+)»", line)
    assert named, "the checklist points at VERIFICATION without naming the section to open"
    for name in named:
        assert name in headings, (
            f"the checklist sends the operator to VERIFICATION section «{name}», which the file does not "
            f"have; its sections are {sorted(headings)}"
        )


def test_the_restore_playbook_awaits_the_live_path_count_the_table_publishes():
    measured = _measured_counts()
    number, date = _operations_claim()
    assert number == measured[_JOURNEY][0], (
        f"a restored copy is declared good at {number}/{number} while the path this tree answers "
        f"with is {measured[_JOURNEY][0]}, so the step can never be passed"
    )
    assert date == measured[_JOURNEY][1], (
        f"the restore step dates its expectation at {date}, the table measured it on "
        f"{measured[_JOURNEY][1]}"
    )


def test_the_guard_reads_the_numbers_it_compares(monkeypatch):
    """The coupling has to be the number itself, not a sentence the parser happens to match.

    Each flip rewrites one published count in one document and leaves the rest of the tree alone:
    the check that fires is the one that owns that document, and the count it fires against is the
    table's. Without the flips a parser that only recognised a shape would pass every check above
    while the documents drifted.
    """
    assert _divergences() == []
    measured = _measured_counts()

    android = measured[_ANDROID][0]
    table = _carrier_text().replace(
        f"**{android} passed, 0 failed**", "**199 passed, 0 failed**", 1
    )
    assert table != _carrier_text(), "the flip did not reach the measurement table"
    monkeypatch.setitem(globals(), "_carrier_text", lambda: table)
    assert _divergences(), "moving the table did not move the command block's expectation"
    monkeypatch.undo()

    block_line = next(
        line for line in _command_block_lines() if _COMMANDS[_ANDROID] in line
    )
    assert f"# {android}" in block_line, f"the Android line of the block reads: {block_line}"
    block = _carrier_text().replace(block_line, block_line.replace(f"# {android}", "# 199"), 1)
    assert block != _carrier_text(), "the flip did not reach the command block"
    monkeypatch.setitem(globals(), "_carrier_text", lambda: block)
    assert any(
        "command block" in line for line in _divergences()
    ), "the block could say anything about the Android suite and stay green"
    monkeypatch.undo()

    backend = measured[_BACKEND][0]
    counter_claim = f"**{backend}/{backend}**"
    opening = _carrier_text().replace(counter_claim, "**191/191**", 1)
    assert opening != _carrier_text(), "the flip did not reach the paragraph above the table"
    monkeypatch.setitem(globals(), "_carrier_text", lambda: opening)
    assert any(
        "opening" in line for line in _divergences()
    ), "the counter paragraph could still promise a count the table no longer measures"
    monkeypatch.undo()

    backend_claim = f"**{measured[_BACKEND][0]}/{measured[_BACKEND][0]}**"
    released = _release_text().replace(backend_claim, "**191/191**", 1)
    assert released != _release_text(), "the flip did not reach the release checklist"
    monkeypatch.setitem(globals(), "_release_text", lambda: released)
    assert any(
        "RELEASE.md" in line for line in _divergences()
    ), "the checklist could still promise the 2026-10-06 counts"
    monkeypatch.undo()

    journey = measured[_JOURNEY][0]
    restored = _operations_text().replace(
        f"ожидание: {journey}/{journey}", f"ожидание: {journey - 1}/{journey - 1}", 1
    )
    assert restored != _operations_text(), "the flip did not reach the restore playbook"
    monkeypatch.setitem(globals(), "_operations_text", lambda: restored)
    assert any(
        "OPERATIONS.md" in line for line in _divergences()
    ), "the restore step could still await a count no tree produces"
