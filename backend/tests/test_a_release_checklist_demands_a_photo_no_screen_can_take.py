"""A release checklist asked for a device check of a photograph the app cannot take.

``docs/RELEASE.md`` §8 told the operator to verify on a device «вход, онбординг, подбор, пара,
чат (WebSocket работает именно с `wss://`-адресом), загрузка фото». Measured on this tree the last
of the five cannot be performed at all: ``uploadPhoto`` is declared in three client files
(``ApiService.kt``, ``ProfileRepositoryImpl.kt``, ``Repositories.kt``) and has no caller anywhere
under ``presentation/``, and ``android/app/src/main`` touches no file picker and no camera API
(``GetContent``, ``PickVisualMedia``, ``TakePicture``, ``MediaStore``, ``CameraX``,
``ImageReader`` — zero hits each) and declares no camera or storage permission
(probe ``s72_d8_photo_unreachable_v2.txt``, 21:44:10…21:44:12 UTC, tree ``217d3a8``).

The probe of that tree listed nine names; the six above are what a photograph needs. The two generic
ones it also counted — ``ActivityResultContracts`` and ``rememberLauncherForActivityResult`` — carry
no picture: since stage 95 the plans page launches one of them to ask the system for
``POST_NOTIFICATIONS``, the third permission the manifest declares alongside ``INTERNET`` and
``ACCESS_NETWORK_STATE``. A guard that called those two names photo APIs would have gone red on a
reminder, which is not a camera, so the lists below were cut to the APIs whose presence would actually
mean a screen can pick or shoot an image. So the checklist demanded a check nobody could reproduce: an operator who ticked it
either ticked a lie or had to stop and guess what the document meant.

The route beside it is alive and covered — ``POST /users/me/photo`` is declared in
``app/api/v1/users.py`` and called from three backend test files — which is why the gap is a missing
screen and not a dead endpoint, and why ``README.md`` already counts it as a product gap: a person
who registers today reaches the deck without any photograph.

What the checks below pin: the reachability fact itself; that the route is nevertheless live and
tested; that §8 asks for the upload exactly when the client is able to perform it, and while it is
not, that §8 names the route and the absent caller instead of dropping the item in silence; that
§11 keeps the gap listed as a product gap rather than a release step; and that every ``.kt:NN``
citation the checklist uses still points at the line carrying the symbol it is cited for.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_CLIENT_MAIN = _ROOT / "android" / "app" / "src" / "main"
_PRESENTATION = _CLIENT_MAIN / "java" / "app" / "befos" / "presentation"
_TESTS = _ROOT / "backend" / "tests"
_ROUTE = _ROOT / "backend" / "app" / "api" / "v1" / "users.py"
_RELEASE = _ROOT / "docs" / "RELEASE.md"
_README = _ROOT / "README.md"

# Every API this app would have to touch to let a person choose or shoot a picture. A screen that
# adds upload without one of them cannot exist, so the list is the client-side half of the fact.
# The generic activity-result launcher is deliberately absent: it is how this app asks the system for
# a permission too, and its presence says nothing about photographs.
_PICKER_APIS = (
    "GetContent",
    "PickVisualMedia",
    "TakePicture",
    "MediaStore",
    "CameraX",
    "ImageReader",
)

_NEGATION = re.compile(r"\bне\b|\bнет\b|\bнельзя\b|\bno\b", re.IGNORECASE)
_UPLOAD_MENTION = re.compile(r"загруз\w*", re.IGNORECASE)
_PHOTO_MENTION = re.compile(r"фото\w*|снимк\w*", re.IGNORECASE)
_KOTLIN_CITATION = re.compile(r"([A-Za-z]+\.kt):(\d+)(?:-(\d+))?")


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _presentation_upload_sites() -> list[str]:
    """Every place the client's screens or view models reach the upload method."""
    sites: list[str] = []
    for file in sorted(_PRESENTATION.rglob("*.kt")):
        for number, line in enumerate(_text(file).splitlines(), start=1):
            if "uploadPhoto" in line:
                sites.append(f"{file.relative_to(_ROOT)}:{number}")
    return sites


def _picker_hits() -> dict[str, int]:
    sources = [_text(file) for file in _CLIENT_MAIN.rglob("*.kt")]
    return {api: sum(text.count(api) for text in sources) for api in _PICKER_APIS}


def _manifest_permissions() -> set[str]:
    manifest = _text(_CLIENT_MAIN / "AndroidManifest.xml")
    return set(re.findall(r'android:name="android\.permission\.([A-Z_]+)"', manifest))


def _route_upload_lines() -> dict[str, int]:
    """Backend test files that call the upload route, with the number of call lines in each."""
    out: dict[str, int] = {}
    for file in sorted(_TESTS.glob("test_*.py")):
        count = sum(1 for line in _text(file).splitlines() if "/users/me/photo" in line)
        if count:
            out[file.name] = count
    return out


def _release_section(number: str) -> str:
    text = _text(_RELEASE)
    marker = f"## {number}."
    start = text.index(marker)
    tail = text[start + len(marker) :]
    end = tail.find("\n## ")
    return tail if end == -1 else tail[:end]


def _checklist_items(section: str) -> list[str]:
    """Each ``- [ ]`` entry of the section, continuation lines joined to it."""
    items: list[str] = []
    for line in section.splitlines():
        if line.startswith("- ["):
            items.append(line)
        elif items and line.strip():
            items[-1] += " " + line.strip()
    return items


def _numbered_items(section: str) -> list[str]:
    """Each ``1.``-style entry of a prose list, continuation lines joined to it."""
    items: list[str] = []
    for line in section.splitlines():
        if re.match(r"^\d+\.\s", line):
            items.append(line)
        elif items and line.strip():
            items[-1] += " " + line.strip()
    return items


def _upload_demands(items: list[str]) -> list[str]:
    """Items that ask the operator to perform a photo upload, as opposed to explaining one away.

    The split is by sentence: the defect was a bare list member («…, загрузка фото.»), and an
    honest note about the same route always negates itself («Загрузки своего снимка в этом списке
    нет»). A demand is therefore a sentence that mentions uploading and a photograph and says
    nothing against it.
    """
    demands: list[str] = []
    for item in items:
        for sentence in re.split(r"(?<=[.:])\s+", item):
            if (
                _UPLOAD_MENTION.search(sentence)
                and _PHOTO_MENTION.search(sentence)
                and not _NEGATION.search(sentence)
            ):
                demands.append(sentence)
    return demands


def _client_can_take_a_photo() -> bool:
    return bool(_presentation_upload_sites()) and any(
        count for count in _picker_hits().values()
    )


def test_the_client_cannot_reach_the_photo_upload_itself():
    assert _presentation_upload_sites() == [], (
        "screens now reach uploadPhoto, and the docs that say no screen does have to be rewritten: "
        + ", ".join(_presentation_upload_sites())
    )
    reached = {api: count for api, count in _picker_hits().items() if count}
    assert not reached, f"a picker or camera API appeared in the client: {reached}"
    # A photograph arrives through a picker or a camera, never through a permission, so the set below
    # is read as「no photo API is reachable」rather than as «the app holds no third permission»: the
    # third one is the plans page asking to remind the pair about an hour (stage 95).
    assert _manifest_permissions() == {
        "INTERNET",
        "ACCESS_NETWORK_STATE",
        "POST_NOTIFICATIONS",
    }, (
        "the APK gained a permission outside the three this tree explains; the claim that no photo can "
        f"be taken from a device has to be re-read: {sorted(_manifest_permissions())}"
    )


def test_the_upload_route_itself_is_live_and_covered():
    assert '@router.post("/me/photo"' in _text(_ROUTE), (
        "the checklist gap was written as a missing screen over a working route; if the route is "
        "gone, the gap is a broken endpoint and needs a different fix"
    )
    calls = _route_upload_lines()
    assert calls, "no backend test calls the upload route anymore"
    assert len(calls) >= 3 and sum(calls.values()) >= 14, (
        f"the docs count this coverage as {calls}; re-read the sentence in RELEASE.md §8 if it moved"
    )


def test_the_checklist_asks_for_the_upload_only_when_the_client_can_perform_it():
    items = _checklist_items(_release_section("8"))
    assert items, "RELEASE.md §8 has no checklist items to guard"
    demands = _upload_demands(items)
    if _client_can_take_a_photo():
        assert demands, (
            "the client can attach a photograph now, and the release checklist still does not ask "
            "anybody to check it on a device"
        )
        return
    assert not demands, (
        "the checklist asks for a photo upload that no screen can perform: " + " | ".join(demands)
    )


def test_the_guard_asks_the_checklist_back_when_a_screen_appears(monkeypatch):
    """Half of this guard would be invisible without the flip, so the flip is simulated here.

    The two probes that decide whether the client can take a photograph are pointed at a client
    that can — a screen calling ``uploadPhoto`` and a picker API beside it — and the shipped §8 is
    read unchanged. It must then carry no device demand for the upload, which is exactly the
    failure ``test_the_checklist_asks_for_the_upload_only_when_the_client_can_perform_it`` would
    raise: the document that today explains why it cannot ask has to be rewritten the day it can.
    """
    monkeypatch.setitem(
        globals(),
        "_presentation_upload_sites",
        lambda: ["android/app/src/main/java/app/befos/presentation/fake/FakeScreen.kt:1"],
    )
    monkeypatch.setitem(
        globals(),
        "_picker_hits",
        lambda: {api: (1 if api == "PickVisualMedia" else 0) for api in _PICKER_APIS},
    )
    assert _client_can_take_a_photo(), "the simulated client did not become reachable"
    demands = _upload_demands(_checklist_items(_release_section("8")))
    assert demands == [], (
        "the shipped §8 already demands a device check of the upload (" + " | ".join(demands) +
        "), so the flip test proves nothing: the explanatory item has to be restored first"
    )


def test_the_dropped_item_is_named_and_not_silently_removed():
    section = _release_section("8")
    assert "/users/me/photo" in section, (
        "§8 no longer names the route whose upload it does not ask to check; the item has to be "
        "replaced by a sentence that says what remains true"
    )
    assert "presentation/" in section, (
        "§8 names the route but not the reason it is uncheckable on a device: the absent caller "
        "from presentation/ is the fact the operator cannot verify"
    )


def test_the_release_doc_keeps_the_gap_as_a_product_gap():
    section = _release_section("11")
    assert section, "RELEASE.md §11 disappeared; the not-done list has to live somewhere"
    items = _numbered_items(section)
    assert items, "RELEASE.md §11 has no numbered entries to guard"
    named = [
        item
        for item in items
        if _PHOTO_MENTION.search(item)
        and "/users/me/photo" in item
        and "presentation" in item
        and "README" in item
    ]
    assert named, (
        "§11 does not list the missing photo screen as a product gap naming the route, the absent "
        "caller and the document that owns the gap"
    )


def test_every_kotlin_citation_in_the_checklist_still_names_the_symbol():
    section = _release_section("8")
    checked = 0
    for file_name, start, end in _KOTLIN_CITATION.findall(section):
        candidates = list(_CLIENT_MAIN.rglob(file_name))
        assert candidates, f"§8 cites {file_name}, which is not in the client anymore"
        lines = _text(candidates[0]).splitlines()
        last = int(end or start)
        assert last <= len(lines), f"§8 cites {file_name}:{last}, the file has {len(lines)} lines"
        window = lines[int(start) - 1 : last]
        assert any("uploadPhoto" in line for line in window), (
            f"§8 cites {file_name}:{start}-{last} as the client path to the upload route, "
            "and that window no longer carries it"
        )
        checked += 1
    assert checked >= 3, f"§8 cites {checked} Kotlin lines; the client path lost its citations"

    readme = _text(_README)
    bullet = next(
        (
            block
            for block in readme.split("- **")
            if "снимок из приложения нельзя" in block
        ),
        "",
    )
    assert bullet, "README.md no longer states that a photo cannot be added from the app"
    for file_name, start, end in _KOTLIN_CITATION.findall(bullet):
        candidates = list(_CLIENT_MAIN.rglob(file_name))
        assert candidates, f"README cites {file_name}, which is gone"
        lines = _text(candidates[0]).splitlines()
        window = lines[int(start) - 1 : int(end or start)]
        assert any("uploadPhoto" in line for line in window), (
            f"README cites {file_name}:{start} for the client path and the line moved"
        )
