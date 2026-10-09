"""The stand must not drop a keep-alive connection before the user's next action.

Measured on 2026-10-09 against the stand as shipped, one socket, two requests on it, the
second issued after an idle gap (emulator -> `10.0.2.2:8000`): a 1 s gap answers both
requests, a 4 s gap still answers, and at 8 s / 20 s / 40 s the socket carries one response
only. The same socket watched from the host names the author: the peer sends FIN 5000 ms
after the first response (5016 ms with the request included), which is uvicorn's default
`--timeout-keep-alive`. The cost of getting it back is measured on the same probe: a fresh
connection answers its first response line 573 / 576 / 578 / 583 ms after the client starts,
while the second request of one socket, written 2 s in, was answered 110 ms later (+2009 ms
written, +2109 ms read; the reader forks `date` per line and that costs 20-27 ms on this
tool, so 110 ms is the upper bound). So with a five-second ceiling every action taken after
a short pause pays a reconnect, while the client pool keeps idle connections far longer than
that and expects to reuse them.

This guard pins configuration, not behaviour: the suite runs the ASGI app in-process over
httpx, where there is no wire connection to time. What it can check is the command the
container starts with, because that command is where the five-second default comes from.
"""
from __future__ import annotations

import shlex
from pathlib import Path

import yaml
from uvicorn.config import Config

_COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"

# What uvicorn uses when the shipped command says nothing — the state this file guards.
_UVICORN_DEFAULT = 5
# Gaps measured between a cold launch's last request and the next action of the same
# session: 17 s on the pre-fix tree (02:46:27 -> 02:46:44) and 41 s on the fixed one
# (02:59:45 -> 03:00:26), while the deck itself arrives 2 s after the profile. A reader
# dwelling on one card waits longer than either. This floor is not the shipped value —
# the stand runs at 75 s — it fails anything that puts the ceiling back near the default.
_MIN_KEEP_ALIVE_SECONDS = 30
# Nothing sits in front of this stand to force a shorter value, so the ceiling is our own:
# an abandoned socket should not be held open for minutes per client.
_MAX_KEEP_ALIVE_SECONDS = 120


def _backend_command() -> str:
    services = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))["services"]
    return services["backend"]["command"]


def _uvicorn_flags() -> list[str]:
    """Flags of the uvicorn call inside the container's `sh -c` payload."""
    payload = shlex.split(_backend_command())[-1]
    for segment in payload.split("&&"):
        tokens = shlex.split(segment)
        if "uvicorn" in tokens:
            return tokens[tokens.index("uvicorn") + 1:]
    raise AssertionError(f"the backend command starts no uvicorn: {_backend_command()!r}")


def _keep_alive_seconds() -> int | None:
    flags = _uvicorn_flags()
    for index, token in enumerate(flags):
        if token == "--timeout-keep-alive":
            return int(flags[index + 1])
        if token.startswith("--timeout-keep-alive="):
            return int(token.split("=", 1)[1])
    return None


def test_the_shipped_command_outlives_a_pause_between_actions() -> None:
    seconds = _keep_alive_seconds()
    assert seconds is not None, (
        "uvicorn runs on its five-second keep-alive default: an idle socket dies before the "
        "next action, and the client pays a fresh connection (573-583 ms measured against "
        "~110 ms on a socket that survived)"
    )
    assert seconds >= _MIN_KEEP_ALIVE_SECONDS


def test_keep_alive_stays_below_the_ceiling() -> None:
    seconds = _keep_alive_seconds()
    assert seconds is not None
    assert seconds <= _MAX_KEEP_ALIVE_SECONDS


def test_the_flag_names_a_setting_uvicorn_actually_reads() -> None:
    without_flag = Config(app="app.main:app")
    assert without_flag.timeout_keep_alive == _UVICORN_DEFAULT

    seconds = _keep_alive_seconds()
    assert seconds is not None
    assert Config(app="app.main:app", timeout_keep_alive=seconds).timeout_keep_alive == seconds
