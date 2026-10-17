"""A release checklist once asked for a device check of a photograph the app could not take.

``docs/RELEASE.md`` §8 told the operator to verify on a device «вход, онбординг, подбор, пара,
чат (WebSocket работает именно с `wss://`-адресом), загрузка фото». Measured on that tree the last
of the five could not be performed at all: ``uploadPhoto`` was declared in three client files
(``ApiService.kt``, ``ProfileRepositoryImpl.kt``, ``Repositories.kt``) and had no caller anywhere
under ``presentation/``, and ``android/app/src/main`` touched no file picker and no camera API
(``GetContent``, ``PickVisualMedia``, ``TakePicture``, ``MediaStore``, ``CameraX``,
``ImageReader`` — zero hits each) and declared no camera or storage permission
(probe ``s72_d8_photo_unreachable_v2.txt``, 21:44:10…21:44:12 UTC, tree ``217d3a8``).

Stage 99 closed that gap: the profile tab now opens the system's picture chooser
(``ActivityResultContracts.PickVisualMedia``, declared in
``presentation/profile/ProfileScreen.kt``), sends what came back through the route that was already
there, and paints the answer. The checklist item this file was written to police is therefore a
check an operator can actually perform, and the checks below turned to hold the new shape: that the
client really reaches the upload from a screen, that it still holds no camera and asked for no new
permission to get a picture, that §8 asks for the device check exactly when the client can perform
it, that the citations §8 and ``README.md`` use still name the symbols they are cited for, and that
the two halves of one refusal — the formats the server re-encodes, the formats the client is willing
to send — have not drifted apart.

What remains open is stated in §8 and §11 rather than in the client: nothing in ``presentation/``
removes or reorders a photograph, because no route does either
(``delete_stored_photo`` is reached only when an account is purged), and ``e2e_journey.py`` still
never touches a picture.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_CLIENT_MAIN = _ROOT / "android" / "app" / "src" / "main"
_PRESENTATION = _CLIENT_MAIN / "java" / "app" / "befos" / "presentation"
_ERROR_TEXT = _CLIENT_MAIN / "java" / "app" / "befos" / "core" / "network" / "BackendErrorText.kt"
_TESTS = _ROOT / "backend" / "tests"
_ROUTE = _ROOT / "backend" / "app" / "api" / "v1" / "users.py"
_PHOTO_SERVICE = _ROOT / "backend" / "app" / "services" / "photo_service.py"
_RELEASE = _ROOT / "docs" / "RELEASE.md"
_README = _ROOT / "README.md"

# Every API this app would have to touch to let a person choose or shoot a picture. The generic
# activity-result launcher is deliberately absent: it is how this app asks the system for a
# permission too, and its presence says nothing about photographs.
_PICKER_APIS = (
    "GetContent",
    "PickVisualMedia",
    "TakePicture",
    "MediaStore",
    "CameraX",
    "ImageReader",
)

# The picture arrives through the chooser, which needs no permission of ours; a manifest that grew a
# fourth right would mean the upload stopped going through the chooser, and the copy in README.md
# that promises no permission would have to be re-read.
_PERMISSIONS_FOR_A_PHOTO = {"INTERNET", "ACCESS_NETWORK_STATE", "POST_NOTIFICATIONS"}

_NEGATION = re.compile(r"\bне\b|\bнет\b|\bнельзя\b|\bno\b", re.IGNORECASE)
_UPLOAD_MENTION = re.compile(r"загруз\w*", re.IGNORECASE)
_PHOTO_MENTION = re.compile(r"фото\w*|снимк\w*", re.IGNORECASE)
_KOTLIN_CITATION = re.compile(r"([A-Za-z]+\.kt):(\d+)(?:-(\d+))?")
_PYTHON_SET_ENTRY = re.compile(r'"([^"]+)"')
_KOTLIN_MAP_ENTRY = re.compile(r'^\s*"((?:[^"\\]|\\.)+)"\s+to\s', re.MULTILINE)
_VALIDATION_RAISE = re.compile(r'ValidationError\((f?)"((?:[^"\\]|\\.)+)"')


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


def _server_allowed_types() -> set[str]:
    block = re.search(r"ALLOWED_CONTENT_TYPES = \{([^}]*)\}", _text(_PHOTO_SERVICE))
    assert block, "photo_service.py no longer declares ALLOWED_CONTENT_TYPES as a literal set"
    return set(_PYTHON_SET_ENTRY.findall(block.group(1)))


def _client_allowed_types() -> set[str]:
    block = re.search(r"PHOTO_UPLOAD_CONTENT_TYPES = setOf\(([^)]*)\)", _text(_ERROR_TEXT))
    assert block, (
        "BackendErrorText.kt no longer declares PHOTO_UPLOAD_CONTENT_TYPES — the client's own "
        "refusal of a format lost the list it is supposed to match"
    )
    return set(_PYTHON_SET_ENTRY.findall(block.group(1)))


def _kotlin_block(name: str) -> str:
    """The body of one private collection in BackendErrorText.kt, up to its closing paren."""
    lines = _text(_ERROR_TEXT).splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(f"private val {name}")]
    assert starts, f"BackendErrorText.kt lost `private val {name}`"
    body: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if line == ")":
            break
        body.append(line)
    return "\n".join(body)


def _translated_keys() -> set[str]:
    return {match.group(1).lower() for match in _KOTLIN_MAP_ENTRY.finditer(_kotlin_block("translated"))}


def _translated_prefixes() -> set[str]:
    return {match.group(1) for match in _KOTLIN_MAP_ENTRY.finditer(_kotlin_block("translatedPrefixes"))}


def _photo_refusals() -> list[str]:
    """Every message the upload route can answer a photograph with, straight from its raise sites."""
    out: list[str] = []
    for _is_fstring, message in _VALIDATION_RAISE.findall(_text(_PHOTO_SERVICE)):
        # An f-string names data the server counted («Image exceeds {settings…} MB limit.»), so the part a
        # wording can be matched on is its literal opening, trailing space included — the Kotlin prefix
        # that answers it carries that same space. A plain message holds no brace, so it stays whole.
        out.append(message.split("{", 1)[0])
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

    The split is by sentence: the defect was a bare list member («…, загрузка фото.»), and an honest
    note about the same route always negates itself («Снимок можно добавить, но не убрать»). A demand
    is therefore a sentence that mentions uploading and a photograph and says nothing against it.
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


def test_the_client_reaches_the_upload_from_a_screen():
    sites = _presentation_upload_sites()
    assert sites, (
        "the release checklist and README.md say a person can attach a photograph from the profile "
        "tab, and no screen reaches uploadPhoto anymore"
    )
    reached = {api: count for api, count in _picker_hits().items() if count}
    assert reached, (
        "no picker or camera API is left in the client, so the upload has nothing to choose from: "
        f"{sites}"
    )
    assert "PickVisualMedia" in reached, (
        f"a photograph now arrives through {reached} rather than the system's picture chooser; "
        "re-read the copy in README.md that promises no permission and no camera"
    )


def test_a_photograph_still_costs_the_client_no_permission_and_no_camera():
    assert _manifest_permissions() == _PERMISSIONS_FOR_A_PHOTO, (
        "the APK gained a permission beyond the three this tree explains. The chooser needs none, so "
        "a fourth right means the picture is being taken some other way and the documents that say so "
        f"have to be re-read: {sorted(_manifest_permissions())}"
    )
    shooting = {api: count for api, count in _picker_hits().items() if count and api != "PickVisualMedia"}
    assert not shooting, (
        f"the client touches {shooting}; README.md states there is no camera in the app and that a "
        "picture comes from the chooser alone"
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


def test_the_guard_asks_the_checklist_back_when_the_screen_disappears(monkeypatch):
    """Half of this guard would be invisible without the flip, so the flip is simulated here.

    Both probes that decide whether the client can take a photograph are pointed at a client that
    cannot — no caller in ``presentation/``, no chooser anywhere — and the shipped §8 is read
    unchanged. It must then carry a device demand for the upload, which is exactly the failure
    ``test_the_checklist_asks_for_the_upload_only_when_the_client_can_perform_it`` would raise on
    that flipped tree: the checklist is allowed to ask only as long as the screen exists.
    """
    monkeypatch.setitem(globals(), "_presentation_upload_sites", lambda: [])
    monkeypatch.setitem(globals(), "_picker_hits", lambda: {api: 0 for api in _PICKER_APIS})
    assert not _client_can_take_a_photo(), "the simulated client stayed reachable"
    demands = _upload_demands(_checklist_items(_release_section("8")))
    assert demands, (
        "the shipped §8 stopped demanding the device check of an upload it can name, so the flip "
        "test proves nothing: the item has to be restored first"
    )


def test_the_checklist_names_the_client_path_it_asks_to_check():
    section = _release_section("8")
    assert "/users/me/photo" in section, (
        "§8 no longer names the route whose upload it asks to check on a device"
    )
    assert "presentation/" in section, (
        "§8 names the route but not the screen that reaches it; the path the operator is checking "
        "has to be named where the check lives"
    )


def test_the_release_doc_keeps_the_photo_question_that_is_still_open():
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
        "§11 does not keep the photograph question that is still open — no screen removes or "
        "reorders a picture, and no route does either — naming the route, the absent caller in "
        "presentation/ and the document that owns the gap"
    )


def test_the_client_refuses_exactly_the_formats_the_server_refuses():
    server = _server_allowed_types()
    client = _client_allowed_types()
    assert server == client, (
        f"the client sends {sorted(client)} while the pipeline re-encodes {sorted(server)}: one "
        "of the two lists moved, and a picture the other list refuses is either a wasted uplink or "
        "a photograph the app would not send at all"
    )


def test_every_photo_refusal_the_server_can_raise_has_russian_copy():
    keys = _translated_keys()
    prefixes = _translated_prefixes()
    uncovered = [
        message
        for message in _photo_refusals()
        if message.lower() not in keys and not any(message.startswith(prefix) for prefix in prefixes)
    ]
    assert not uncovered, (
        f"the upload route refuses {uncovered} in English and the client has no Russian wording for "
        "it; whatever falls through is answered by a status family, not by what the photo pipeline "
        "actually objected to"
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
            if "Снимок можно добавить" in block
        ),
        "",
    )
    assert bullet, "README.md no longer states what the app does and does not let a person do with a photo"
    for file_name, start, end in _KOTLIN_CITATION.findall(bullet):
        candidates = list(_CLIENT_MAIN.rglob(file_name))
        assert candidates, f"README cites {file_name}, which is gone"
        lines = _text(candidates[0]).splitlines()
        window = lines[int(start) - 1 : int(end or start)]
        assert any("uploadPhoto" in line for line in window), (
            f"README cites {file_name}:{start} for the client path and the line moved"
        )
