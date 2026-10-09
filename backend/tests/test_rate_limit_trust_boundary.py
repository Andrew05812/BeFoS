"""Whose window the rate limiter counts: the deployment's choice, or the caller's.

Measured on this stand on 2026-10-10 against the shipped container — sweeps of
`GET /api/v1/users/me`, `RATE_LIMIT_PER_MINUTE` at its 120 default, the container restarted
between sweeps because the window lives in process memory:

- 130 requests through the published port with no forwarded header: 120 answered, the 121st
  `429 rate_limited`. This is the rule `README.md` states;
- 300 requests through that same port rotating thirty `X-Forwarded-For` values: still 120
  answered and 180 refused, first refusal at #121. Outside the container the TCP peer is the
  bridge gateway, which uvicorn does not accept as a proxy, so nothing rewrote the address;
- the same rotation from the container's own loopback (`127.0.0.1:8000` inside it): **300
  answered, zero refusals**. There the peer is the one address uvicorn trusts by default, so
  `ProxyHeadersMiddleware` replaces `scope["client"]` with the header before
  `app/core/rate_limit.py` reads it, and `_client_key`'s own `trust_proxy_headers` check is
  looking at an address somebody else wrote. Thirty identities bought thirty windows against a
  ceiling of one;
- two controls on that same loopback, 130 requests each: one *fixed* header value answered 120
  and refused from #121, and no header at all answered 120 and refused from #121. So loopback
  traffic is not unthrottled — rotation is what buys the windows.

The loopback case is not hypothetical on this project's documented paths: `README.md` starts the
bare-metal dev server on the host, where every local client *is* a loopback peer. Measured there
with a fresh uvicorn per case, header rotation from loopback served 300 of a 120-request window,
the same rotation from a non-trusted peer (`127.0.0.2`) was refused at #121 — which locates the
rewrite in uvicorn rather than in the app — and every case run under `--no-proxy-headers`
behaved as documented: thirty identities refused at #121, thirty real peer addresses ten requests
each served 300 with no refusals, and `TRUST_PROXY_HEADERS=true` with `--no-proxy-headers`
serving all 300, which is how a proxied deployment keeps one window per user.

So the boundary is decided by the command line, and no command line in this repository states
it: `proxy_headers` defaults to True and `forwarded_allow_ips` to `"127.0.0.1"`. These checks
hold both halves — a caller must not choose the key while the deployment declares no proxy, and
an operator who does put a proxy in front must still get per-identity windows through the switch
named in `.env.example` and `docker-compose.yml`.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

import yaml
from httpx import AsyncClient
from uvicorn.config import Config

from .conftest import auth_headers, register_and_auth

_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE = _ROOT / "docker-compose.yml"
_DOCKERFILE = _ROOT / "backend" / "Dockerfile"
_README = _ROOT / "README.md"
_OPERATIONS = _ROOT / "docs" / "OPERATIONS.md"
_ENV_EXAMPLE = _ROOT / ".env.example"

# uvicorn options that decide whose address the application ends up seeing.
_SWITCH_FLAGS = {
    "--proxy-headers": ("proxy_headers", True),
    "--no-proxy-headers": ("proxy_headers", False),
}
_VALUE_FLAGS = {"--forwarded-allow-ips": "forwarded_allow_ips"}


async def _spend_the_window(
    client: AsyncClient, token: str, identities: list[str], monkeypatch
) -> list[int]:
    """Ask the same route once per claimed identity, with a window of two hits."""
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit._default_limiter, "limit", 2)
    rate_limit.reset_rate_limiters()
    codes = [
        (
            await client.get(
                "/api/v1/users/me", headers={**auth_headers(token), "x-forwarded-for": xff}
            )
        ).status_code
        for xff in identities
    ]
    rate_limit.reset_rate_limiters()
    return codes


async def test_thirty_forged_identities_from_one_peer_spend_one_window(
    client: AsyncClient, monkeypatch
) -> None:
    """A caller must not be able to buy a fresh budget by rewriting its own header.

    `trust_proxy_headers` keeps its shipped default, which is the case the README describes:
    the key is the address of the connection. Two requests answer, the third is refused — and
    the third claims an identity nobody has used yet.
    """
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit.settings, "trust_proxy_headers", False)
    account = await register_and_auth(client, "one_window@befos.app")

    codes = await _spend_the_window(
        client, account["token"], ["1.1.1.1", "2.2.2.2", "3.3.3.3"], monkeypatch
    )

    assert codes == [200, 200, 429], (
        f"a header the client writes itself moved the bucket: {codes}"
    )


async def test_a_trusted_proxy_header_moves_the_window_to_the_identity_behind_it(
    client: AsyncClient, monkeypatch
) -> None:
    """The other half of the same rule, so the fix cannot be "ignore the header forever".

    Behind a proxy that overwrites `X-Forwarded-For` the operator declares it with
    `TRUST_PROXY_HEADERS=true`, and then each address behind that proxy gets its own window —
    the only way a proxied deployment keeps the 120/minute ceiling meaningful per user.
    """
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit.settings, "trust_proxy_headers", True)
    account = await register_and_auth(client, "trusted_proxy@befos.app")

    spread = await _spend_the_window(
        client, account["token"], ["1.1.1.1", "2.2.2.2", "3.3.3.3"], monkeypatch
    )
    assert spread == [200, 200, 200], f"a trusted proxy's header did not split the window: {spread}"

    repeated = await _spend_the_window(
        client, account["token"], ["4.4.4.4", "4.4.4.4", "4.4.4.4"], monkeypatch
    )
    assert repeated == [200, 200, 429], f"one identity got more than its own window: {repeated}"


def test_no_shipped_command_leaves_the_server_to_choose_the_limiter_key() -> None:
    """Every command that starts uvicorn here has to name the trust boundary.

    Both halves of the rewrite are defaults nobody wrote down (`proxy_headers=True`,
    `forwarded_allow_ips="127.0.0.1"`), and the measured loopback sweep above is what a caller
    gets when a command inherits them. The check reads the flags out of the compose command, the
    image's `CMD` and the README quickstart, resolves each through `uvicorn.config.Config`, and
    requires the peer address to survive.
    """
    assert Config(app="app.main:app").proxy_headers is True, (
        "uvicorn stopped rewriting the peer address by default; the page's argument changes"
    )

    for source, flags in _shipped_commands().items():
        config = Config(app="app.main:app", **flags)
        assert config.proxy_headers is False, (
            f"{source} lets uvicorn replace the peer address with X-Forwarded-For, so the "
            f"limiter's key is chosen by whoever sends the request: {flags}"
        )


def test_the_operations_page_names_the_window_its_owner_and_the_knob() -> None:
    """An operator behind a reverse proxy has to be told who counts the requests.

    The page said the forwarded header is not trusted — that is what `_client_key` does, not
    what the deployment did — and it never named `TRUST_PROXY_HEADERS` at all, so the one
    switch that decides the answer was readable only in `config.py`. Behind a proxy the server
    does not trust, every user of the site spends one 120/minute window together, so this is
    capacity advice and not only a security note.
    """
    section = _rate_limit_section(_OPERATIONS.read_text(encoding="utf-8"))
    for name in ("TRUST_PROXY_HEADERS", "--no-proxy-headers", "X-Forwarded-For", "120"):
        assert name in section, f"the limiter section says nothing about {name}"

    assert "TRUST_PROXY_HEADERS" in _ENV_EXAMPLE.read_text(encoding="utf-8"), (
        "the switch that owns the window is missing from the file an operator copies"
    )
    assert "TRUST_PROXY_HEADERS" in _COMPOSE.read_text(encoding="utf-8"), (
        "a compose deployment cannot set the switch without editing the compose file itself"
    )


def _shipped_commands() -> dict[str, dict[str, object]]:
    """Where uvicorn is started from in this repository, with its trust flags resolved."""
    compose = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    payload = shlex.split(compose["services"]["backend"]["command"])[-1]
    uvicorn = next(
        shlex.split(segment) for segment in payload.split("&&") if "uvicorn" in segment
    )
    image_cmd = next(
        (
            json.loads(raw[4:].strip())
            for raw in _DOCKERFILE.read_text(encoding="utf-8").splitlines()
            if raw.startswith("CMD ")
        ),
        None,
    )
    assert image_cmd, "the image no longer starts uvicorn from a CMD this check can read"
    quickstart = [
        line
        for block in re.findall(r"```(?:bash|sh)\n(.*?)```", _README.read_text(encoding="utf-8"), re.S)
        for line in block.splitlines()
        if line.startswith("uvicorn app.main:app")
    ]
    assert quickstart, "README no longer shows a uvicorn command to guard"

    return {
        "docker-compose.yml command": _trust_flags(uvicorn[uvicorn.index("uvicorn") + 1:]),
        "backend/Dockerfile CMD": _trust_flags(image_cmd[1:]),
        **{
            f"README quickstart: {line}": _trust_flags(shlex.split(line)[1:])
            for line in quickstart
        },
    }


def _trust_flags(argv: list[str]) -> dict[str, object]:
    flags: dict[str, object] = {}
    for index, token in enumerate(argv):
        name = token.split("=", 1)[0]
        if name in _SWITCH_FLAGS:
            flag, value = _SWITCH_FLAGS[name]
            flags[flag] = value
        elif name in _VALUE_FLAGS:
            flags[_VALUE_FLAGS[name]] = (
                token.split("=", 1)[1] if "=" in token else argv[index + 1]
            )
    return flags


def _rate_limit_section(page: str) -> str:
    """The limiter subsection of docs/OPERATIONS.md: heading to the next heading."""
    match = re.search(r"^### .*(лимит|Лимит).*\n", page, flags=re.MULTILINE)
    assert match, "docs/OPERATIONS.md has no limiter subsection — the page does not own this yet"
    rest = page[match.end():]
    end = re.search(r"^#{2,3} ", rest, flags=re.MULTILINE)
    return rest[: end.start()] if end else rest
