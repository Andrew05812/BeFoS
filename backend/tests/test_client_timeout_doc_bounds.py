"""Every wait the client declares must have a re-derivable measured end on the page that owns it.

Stage 47 named the three phases of the Android HTTP client (`connectTimeoutMillis`,
`socketTimeoutMillis`, `requestTimeoutMillis`) and published one extra number next to the connect
phase: «соединение, которое никто не принимает, обрывается на 7 598 мс с `connect_timeout=5000 ms`».
Re-measured on 2026-10-10 with the shipped client against three black-hole addresses
(`10.255.255.1`, `192.0.2.1`, `198.51.100.1`), nine runs, JVM probes run through
`:app:testDebugUnitTest`: the warm calls ended at 5 007 / 5 009 / 5 013 / 5 013 / 5 015 / 5 019 /
5 021 / 5 021 ms and the first call of a fresh JVM at 5 614 ms — every one of them with
`ConnectTimeoutException: Connect timeout has expired [connect_timeout=5000 ms]` caused by
`SocketTimeoutException: Connect timed out`. A tenth warm call, from the cold-start probe below, gave
5 011 ms. No run ended at 7 598 ms.
What does reach that neighbourhood is a different clock: measuring from before the client is
constructed gives 1 191 ms of construction plus 5 594 ms of the first call = 6 811 ms wall, and the
same call once everything is warm costs 5 011 ms. So 7 598 was a wall clock that had been started
before the bound existed, and it cannot be re-derived by a reader.

This guard pins that the page keeps the two apart: `docs/OPERATIONS.md` owns a table naming, for
each declared phase, the declared number and the measured ends, and every measured end has to sit
between the declared bound and that bound plus the slack the page is allowed (2 000 ms — rounded up
from the 603 ms that lay between the warm 5 011 ms and the first-call 5 614 ms; the slack is a
tolerance the page declares, not a measurement, and pinning it to a single run would redden the test
whenever the stand warmed up differently).
A number above the window is a wait the app does not declare; a number below it is a failure that
came from somewhere else and is being sold as the bound.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY = _ROOT / "android" / "app" / "src" / "main" / "java" / "app" / "befos" / "core" / "network" / "HttpClientFactory.kt"
_OPERATIONS = _ROOT / "docs" / "OPERATIONS.md"

_PHASES = ("connectTimeoutMillis", "socketTimeoutMillis", "requestTimeoutMillis")

# Rounded up from the measured gap on the stack above: 5 614 ms (first call of a fresh JVM) against
# 5 011 ms (warm) is 603 ms. The extra is a declared tolerance, not a second measurement.
_SLACK_MS = 2_000

_NUMBER = re.compile(r"(?P<value>\d[\d ]*\d|\d)\s*мс")


def _declared_milliseconds() -> dict[str, int]:
    """The three numbers the shipped client declares, read from the source it compiles from."""
    source = _FACTORY.read_text(encoding="utf-8")
    declared: dict[str, int] = {}
    for phase in _PHASES:
        match = re.search(rf"{phase}\s*=\s*(\d[\d_]*)", source)
        assert match is not None, f"HttpClientFactory.kt declares no {phase}"
        declared[phase] = int(match.group(1).replace("_", ""))
    return declared


def _table_rows() -> list[str]:
    """Markdown table rows of OPERATIONS.md that name one of the declared phases."""
    lines = _OPERATIONS.read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line.lstrip().startswith("|") and any(p in line for p in _PHASES)]


def test_operations_page_publishes_a_measured_end_for_every_declared_phase() -> None:
    declared = _declared_milliseconds()
    rows = _table_rows()
    for phase, bound in declared.items():
        hits = [row for row in rows if phase in row]
        assert hits, (
            f"docs/OPERATIONS.md names no measured end for {phase} (declared {bound} ms): the page "
            "owns the client's waits and must publish what each bound actually ended at"
        )


def test_every_published_end_sits_inside_the_declared_bound_plus_measured_slack() -> None:
    declared = _declared_milliseconds()
    for row in _table_rows():
        phase = next(name for name in _PHASES if name in row)
        bound = declared[phase]
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        measured: list[int] = []
        for cell in cells[1:]:
            if f"{phase} =" in cell.replace("_", " ") or re.search(rf"{phase}\s*=\s*\d", cell):
                continue  # the declared number itself, not a measurement
            measured.extend(int(match.group("value").replace(" ", "")) for match in _NUMBER.finditer(cell))
        assert measured, f"the {phase} row of docs/OPERATIONS.md publishes no measured milliseconds"
        for value in measured:
            assert bound <= value <= bound + _SLACK_MS, (
                f"docs/OPERATIONS.md publishes {value} ms as an end of the {phase} phase, whose "
                f"declared bound is {bound} ms (window {bound}-{bound + _SLACK_MS} ms): a number "
                "outside it is either a wait the app does not declare or a failure that came from "
                "a different clock"
            )
