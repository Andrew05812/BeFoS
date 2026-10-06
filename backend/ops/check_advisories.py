"""Ask GitHub's advisory database whether anything BeFoS runs has a published flaw.

Dependabot reports what is wrong with the *manifests*; this reports what is wrong with the
*resolved set* — the transitive packages a manifest does not name, and the Android artefacts
Gradle picked from BOMs and version constraints. It answers with the same database Dependabot
uses, so the two cannot disagree about what is a flaw.

    # the backend, as the container resolves it
    docker compose build backend
    docker exec befos_backend python -m pip freeze | python ops/check_advisories.py --pip-stdin

    # the mobile app, as Gradle resolves it
    ./gradlew :app:dependencies --configuration debugRuntimeClasspath > tree.txt
    python ops/check_advisories.py --gradle-tree tree.txt

A range the script cannot read is printed as UNPARSED rather than guessed at, so a silent
"nothing found" always means "nothing matched a range I could read".

Set GITHUB_TOKEN to raise the API rate limit above the 60 requests an hour an anonymous
caller gets — the full Android tree is around 165 artefacts.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

RANGE_TOKEN = re.compile(r"(<=|>=|<|>|=)\s*([0-9][0-9A-Za-z.\-_+]*)")
GRADLE_ARTEFACT = re.compile(r"([A-Za-z0-9._\-]+):([A-Za-z0-9._\-]+):([0-9][A-Za-z0-9.\-_]*)")
GRADLE_RESOLVED = re.compile(r"->\s*([0-9][A-Za-z0-9.\-_]*)")


def _version_parts(value: str) -> list[int]:
    return [int(chunk) if chunk.isdigit() else 0 for chunk in re.split(r"[.\-_+]", value)]


def _compare(left: str, right: str) -> int:
    a, b = _version_parts(left), _version_parts(right)
    width = max(len(a), len(b))
    a += [0] * (width - len(a))
    b += [0] * (width - len(b))
    return (a > b) - (a < b)


def covers(version: str, spec: str) -> str:
    """'yes', 'no' or 'unparsed' — whether one range string covers one installed version."""
    tokens = RANGE_TOKEN.findall(spec or "")
    if not tokens:
        return "unparsed"
    inside = True
    for operator, bound in tokens:
        relation = _compare(version, bound)
        inside = inside and {
            "<": relation < 0,
            "<=": relation <= 0,
            ">": relation > 0,
            ">=": relation >= 0,
            "=": relation == 0,
        }[operator]
    return "yes" if inside else "no"


def advisories(ecosystem: str, package: str) -> list[dict]:
    query = urllib.parse.urlencode(
        {"ecosystem": ecosystem, "affects": package, "per_page": 100, "type": "reviewed"}
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "befos-dependency-audit",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"https://api.github.com/advisories?{query}", headers=headers
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


def from_pip(raw: str) -> list[tuple[str, str, str]]:
    rows = []
    for line in raw.splitlines():
        if "==" in line:
            name, _, version = line.partition("==")
            rows.append(("pip", name.strip(), version.split(" ")[0].strip()))
    return rows


def from_gradle_tree(raw: str) -> list[tuple[str, str, str]]:
    """The resolved runtime classpath: every `group:name:version`, with `-> x` applied.

    Lines marked `(c)` are dependency constraints — a version some other module insists on,
    not an artefact that reaches the device — so they are skipped.
    """
    resolved: dict[tuple[str, str], str] = {}
    for line in raw.splitlines():
        if "(c)" in line:
            continue
        arrow = GRADLE_RESOLVED.search(line)
        for group, name, version in GRADLE_ARTEFACT.findall(line):
            resolved[(group, name)] = arrow.group(1) if arrow else version
    return [("maven", f"{group}:{name}", version) for (group, name), version in resolved.items()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pip-stdin", action="store_true", help="read `pip freeze` from stdin")
    source.add_argument("--gradle-tree", metavar="FILE", help="read a `gradlew :app:dependencies` dump")
    args = parser.parse_args()

    if args.pip_stdin:
        artefacts = from_pip(sys.stdin.read())
    else:
        with open(args.gradle_tree, encoding="utf-8", errors="replace") as handle:
            artefacts = from_gradle_tree(handle.read())

    affected = unparsed = errors = 0
    for ecosystem, package, version in sorted(artefacts):
        try:
            rows = advisories(ecosystem, package)
        except Exception as error:  # noqa: BLE001 - the network is the boundary here
            errors += 1
            print(f"ERROR    {ecosystem} {package}: {type(error).__name__} {error}")
            continue
        for advisory in rows:
            for vulnerability in advisory.get("vulnerabilities", []):
                if vulnerability.get("package", {}).get("name") != package:
                    continue
                if vulnerability.get("ecosystem") != ecosystem:
                    continue
                spec = vulnerability.get("vulnerable_version_range") or ""
                verdict = covers(version, spec)
                if verdict == "unparsed":
                    unparsed += 1
                    print(f"UNPARSED {ecosystem} {package} {version}: {spec!r} ({advisory['ghsa_id']})")
                elif verdict == "yes":
                    affected += 1
                    print(
                        f"AFFECTED {ecosystem} {package} {version}: {advisory['ghsa_id']}"
                        f" / {advisory.get('cve_id')} {advisory['severity']}"
                        f" — {advisory['summary'][:80]}"
                    )
    print(
        f"\nchecked {len(artefacts)} artefacts; affected {affected};"
        f" unparsed ranges {unparsed}; query errors {errors}"
    )
    return 1 if (affected or errors) else 0


if __name__ == "__main__":
    sys.exit(main())
