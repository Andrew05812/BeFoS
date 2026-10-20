"""The screen map has to name the line where each route is actually declared.

``docs/USER_FLOWS.md`` opens its screen section with «Карта экранов»: one row per screen, its route
pattern, and a bare ``:NNN`` under «Composable (`BeFosNavHost.kt`)» that an operator is supposed to
open before tapping the door on a device. Measured on the tree stage 114 committed, that column was
wrong in four different ways, and three of them are older than this stage.

- Stale by memory. The map cites splash at ``:62`` while its block opens at ``:68``. The gap is not
  this stage's: the block opened at ``:67`` on the tree stage 114 started from, where the map already
  said ``:61``. Line-by-line renumbering — the tool that repairs citations this stage did move —
  shifted that ``61`` to ``62`` and left the error standing, because a number that was wrong once
  stays wrong however carefully the tree moves under it.
- Two rows, one line. «Мой профиль совместимости» and «Правка профиля» both cite ``:122``; their
  blocks open at ``:126`` and ``:156``. Nothing catches a duplicated cell, which is how the pair was
  written without anyone noticing.
- A route the client does not declare. The history row maps ``planHistory/{planId}``, while
  ``Routes.kt:68`` declares ``planHistory/{$PLAN_ARG}`` with ``PLAN_ARG = "plan"`` — a pattern an
  operator could copy and never open.
- Two screens missing altogether. ``likedMe`` has been in the nav host since stage 112 and ``passed``
  since this stage; neither has a row, so a section that reads as the list of screens left out the
  only two screens a person enters to read rather than to write.

The table was also split in three by blank lines inside it, which is how the last two rows lost their
header when the file renders.

Nothing in the guard circle noticed any of this, because nothing read that column: the only file that
opened ``docs/USER_FLOWS.md`` before this one looked at the settings row's copy. So the map is checked
against the tree instead of remembered:

- every ``composable(`` block the nav host declares has exactly one row, matched by the route pattern
  ``Routes.kt`` gives it;
- the row's «Composable» cell is one bare ``:NNN``, and that line is where the block opens;
- no two rows share a line;
- where a row also cites ``Routes.kt:N`` and its builder ``:M``, ``N`` is the line declaring that
  constant and ``M`` is a line holding a ``fun``;
- the section is one unbroken table, because a row that lost its header is not a row;
- and every pipe table in the whole document opens with a header and its separator, because a blank
  line ends a table — the scenario table lost its header to exactly one at ``:106`` and rendered
  twelve rows unnamed, in a file this stage rewrote around its last row.

Six checks follow. What they cannot check is stated in ``docs/RELEASE.md`` §8 instead: no test here
renders a screen, so the map's prose columns — how a person enters, where the screen leads, what its
refusal says — stay a human's claim about the device, not a measured one.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_DOC = _ROOT / "docs" / "USER_FLOWS.md"
_NAV = _ROOT / ("android/app/src/main/java/app/befos/presentation/"
                "navigation/BeFosNavHost.kt")
_ROUTES = _ROOT / ("android/app/src/main/java/app/befos/presentation/"
                   "navigation/Routes.kt")

_HEADING = "## Карта экранов"
_BARE = re.compile(r"^`:(\d+)`$")
_CONST = re.compile(r'^\s*const val ([A-Z_]+)(?:\s*:\s*String)?\s*=\s*"([^"]+)"')
_BLOCK = re.compile(r"composable\(\s*(?:Routes\.)?([A-Z_]+)")
_ROUTE_ARG = re.compile(r"route\s*=\s*(?:Routes\.)?([A-Z_]+)\b")
_FUN = re.compile(r"^\s*(?:@\w+\s+)?fun ([a-zA-Z]\w*)\(")
_ROUTE_LIN = re.compile(r"`Routes\.kt:(\d+)`")
_BUILDER_LIN = re.compile(r"построитель `:(\d+)`")


def _routes_text() -> list[str]:
    return _ROUTES.read_text(encoding="utf-8").splitlines()


def _patterns() -> dict[str, str]:
    """Route constant -> the pattern the client registers, with ``$X_ARG`` names filled in."""
    lines = _routes_text()
    declared: dict[str, str] = {}
    args: dict[str, str] = {}
    for line in lines:
        hit = _CONST.match(line)
        if not hit:
            continue
        name, value = hit.group(1), hit.group(2)
        if name.endswith("_ARG"):
            args[name] = value
        else:
            declared[name] = value
    return {name: _expand(value, args) for name, value in declared.items()}


def _expand(pattern: str, args: dict[str, str]) -> str:
    for key, value in args.items():
        pattern = pattern.replace("{$" + key + "}", "{" + value + "}").replace("$" + key, value)
    return pattern


def _blocks() -> dict[str, int]:
    """Route constant -> the line its ``composable`` block opens at."""
    lines = _NAV.read_text(encoding="utf-8").splitlines()
    known = _patterns()
    out: dict[str, int] = {}
    for number, line in enumerate(lines, start=1):
        if "composable(" not in line:
            continue
        hit = _BLOCK.search(line)
        name = hit.group(1) if hit and hit.group(1) in known else None
        if name is None:
            for follow in lines[number:min(number + 7, len(lines))]:
                arg = _ROUTE_ARG.search(follow)
                if arg and arg.group(1) in known:
                    name = arg.group(1)
                    break
        assert name, f"BeFosNavHost.kt:{number} opens a composable no route constant covers"
        assert name not in out, f"BeFosNavHost.kt declares {name} in two blocks"
        out[name] = number
    return out


def _section() -> list[tuple[int, str]]:
    """(document line, raw text) for every line of the map section, heading and next heading excluded."""
    lines = _DOC.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == _HEADING), None)
    assert start is not None, f"docs/USER_FLOWS.md lost its {_HEADING!r} heading"
    body: list[tuple[int, str]] = []
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            break
        body.append((index + 1, lines[index]))
    return body


def test_every_pipe_table_the_flows_doc_holds_starts_with_a_header_a_split_cannot_orphan():
    """The whole file, not only «Карта экранов».

    Measured on the tree stage 114 committed: the scenario table «Тридцать шесть сценариев» was split
    by a blank line at ``:106``, so its rows 24 through 35 rendered without their header. The map test
    above reads one section and cannot see this one, and the split was invisible to every author
    because the table is whole in the editor and broken only where markdown parses it.

    A blank line always ends a pipe table, so every run of consecutive ``|`` lines must open with a
    header and its separator. A run whose second line is not a separator is the tail of a table some
    earlier blank line cut off from its header — precisely the defect this stage repaired by hand.
    """
    lines = _DOC.read_text(encoding="utf-8").splitlines()
    orphans: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        if not lines[index].startswith("|"):
            index += 1
            continue
        start = index
        while index < len(lines) and lines[index].startswith("|"):
            index += 1
        if index - start < 2 or not _is_separator(lines[start + 1]):
            orphans.append((start + 1, lines[start].strip()[:60]))
    assert not orphans, (
        "pipe table(s) in docs/USER_FLOWS.md begin without a header separator -> "
        + "; ".join(f":{line} {text!r}" for line, text in orphans)
    )


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.split("|")]


def _is_separator(row: str) -> bool:
    cells = _cells(row)
    return len(cells) >= 3 and all(c and set(c) <= {"-", ":", " "} for c in cells[1:-1])


def _rows() -> list[tuple[int, str, str, str]]:
    """(document line, route cell, composable cell, screen name) for every data row of the map."""
    rows = []
    seen_header = False
    for number, raw in _section():
        if not raw.startswith("|"):
            continue
        if not seen_header:
            seen_header = True
            continue
        cells = _cells(raw)
        if len(cells) < 5 or set(cells[2]) <= {"-", ":", " "}:
            continue
        rows.append((number, cells[2], cells[3], cells[1]))
    return rows


def _route_of(cell: str) -> str:
    """The first backticked span of the route cell, which may also cite Routes.kt beside it."""
    hit = re.search(r"`([^`]+)`", cell)
    assert hit, f"a map row names no route in its second cell: {cell[:60]!r}"
    return hit.group(1)


def _base(pattern: str) -> str:
    return pattern.split("?")[0]


def test_the_map_has_one_row_for_every_route_the_nav_host_declares():
    blocks = _blocks()
    patterns = _patterns()
    rows = {_base(_route_of(cell)) for _line, cell, _composable, _name in _rows()}
    missing = sorted(
        f"{name} (`{patterns[name]}` opens at :{blocks[name]})"
        for name in blocks if _base(patterns[name]) not in rows
    )
    assert not missing, (
        "docs/USER_FLOWS.md «Карта экранов» has no row for " + ", ".join(missing)
    )
    assert len(blocks) >= 19, (
        f"BeFosNavHost.kt declares {len(blocks)} composable blocks; the probe expects the whole host, "
        "so a block stopped being read rather than being dropped from the map"
    )


def test_the_map_is_one_table_a_reader_sees_whole():
    body = _section()
    pipes = [number for number, raw in body if raw.startswith("|")]
    assert len(pipes) >= 2, "the screen map has lost its header row"
    header = _cells(next(raw for number, raw in body if raw.startswith("|")))
    assert header[1] == "Экран", (
        f"the first row of the map is {header[1]!r}; the header names «Экран»"
    )
    split = []
    for number, raw in body:
        if raw.strip() != "" or not pipes:
            continue
        if min(pipes) < number < max(pipes):
            split.append(number)
    assert not split, (
        "docs/USER_FLOWS.md: the screen map is split by blank line(s) "
        + ", ".join(f":{line}" for line in split)
        + " — markdown ends the table there, so every row after it loses its header"
    )


def test_every_map_row_names_the_line_where_its_composable_block_opens():
    blocks = _blocks()
    patterns = _patterns()
    truth = {_base(patterns[name]): line for name, line in blocks.items()}
    wrong = []
    for number, route_cell, composable_cell, name in _rows():
        pattern = _route_of(route_cell)
        hit = _BARE.match(composable_cell)
        assert hit, (
            f"docs/USER_FLOWS.md:{number} ({name}) names its composable as {composable_cell!r}; "
            "the column holds one bare `:NNN`"
        )
        expected = truth.get(_base(pattern))
        assert expected is not None, (
            f"docs/USER_FLOWS.md:{number} ({name}) maps {pattern}, which BeFosNavHost.kt does not "
            "declare as a composable"
        )
        if int(hit.group(1)) != expected:
            wrong.append(f"{name} cites :{hit.group(1)}, the block opens at :{expected}")
    assert not wrong, (
        "stale composable lines in docs/USER_FLOWS.md -> " + "; ".join(wrong)
    )


def test_no_two_map_rows_share_one_composable_line():
    seen: dict[int, list[str]] = {}
    for _number, _route_cell, composable_cell, name in _rows():
        hit = _BARE.match(composable_cell)
        if hit:
            seen.setdefault(int(hit.group(1)), []).append(name)
    shared = {line: names for line, names in seen.items() if len(names) > 1}
    assert not shared, (
        "two rows of the map cite one line of BeFosNavHost.kt: "
        + "; ".join(f":{line} -> {', '.join(names)}" for line, names in sorted(shared.items()))
    )


def test_a_map_row_naming_the_route_constant_points_at_its_declaration_and_builder():
    lines = _routes_text()
    declared = {hit.group(1): number for number, line in enumerate(lines, start=1)
                if (hit := _CONST.match(line)) and not hit.group(1).endswith("_ARG")}
    patterns = _patterns()
    for number, route_cell, _composable_cell, name in _rows():
        cited = _ROUTE_LIN.search(route_cell)
        if not cited:
            continue
        pattern = _route_of(route_cell)
        constant = next((key for key, value in patterns.items()
                         if _base(value) == _base(pattern)), None)
        assert constant, f"docs/USER_FLOWS.md:{number} ({name}) maps an unknown route {pattern}"
        assert declared.get(constant) == int(cited.group(1)), (
            f"docs/USER_FLOWS.md:{number} ({name}) cites Routes.kt:{cited.group(1)} for {constant}, "
            f"which is declared at :{declared.get(constant)}"
        )
        builder = _BUILDER_LIN.search(route_cell)
        if builder:
            at = int(builder.group(1))
            assert _FUN.match(lines[at - 1]), (
                f"docs/USER_FLOWS.md:{number} ({name}) calls Routes.kt:{at} the builder of "
                f"{constant}; that line reads {lines[at - 1].strip()[:60]!r}"
            )
