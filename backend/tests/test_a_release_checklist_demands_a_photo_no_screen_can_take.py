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

Stage 100 grew the same promise to the rest of the row. Three more routes take a photograph's own
number — ``DELETE /users/me/photo/{photo_id}``, ``POST /users/me/photo/{photo_id}/primary`` and
``PATCH /users/me/photo/order`` — and the profile tab is what calls them, so the reach and
refusal-coverage checks below widened with them: a number that belongs to a stranger is refused with
the one message ``profile_service.py`` keeps for it, and that message has to be readable in Russian
too.

What remains open after that is stated in §8 and §11 rather than in the client: no sentence of this
app promises a ceiling on how many photographs an account holds — the route takes a picture until the
person stops sending them — and ``e2e_journey.py`` still never touches one, so the row a person now
manages is covered by the two test sets and not by the live path.

The citation check is scoped to the bullets that name the photograph row. §8 gained a second client
path with stage 101 — the blocked list and its removal, cited on the settings screen — and a screen
sentence like «Разблокировать …?» is a line an operator reads, not a write; the settings bullets are
policed for their own symbols by
``test_a_block_made_by_mistake_can_be_seen_and_taken_back.py``.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_CLIENT_MAIN = _ROOT / "android" / "app" / "src" / "main"
_PRESENTATION = _CLIENT_MAIN / "java" / "app" / "befos" / "presentation"
_ERROR_TEXT = _CLIENT_MAIN / "java" / "app" / "befos" / "core" / "network" / "BackendErrorText.kt"
_TESTS = _ROOT / "backend" / "tests"
_BACKEND_APP = _ROOT / "backend" / "app"
_ROUTE = _ROOT / "backend" / "app" / "api" / "v1" / "users.py"
_PHOTO_SERVICE = _ROOT / "backend" / "app" / "services" / "photo_service.py"
_PROFILE_SERVICE = _ROOT / "backend" / "app" / "services" / "profile_service.py"
_PROFILE_SCREEN = _PRESENTATION / "profile" / "ProfileScreen.kt"
_PROFILE_VIEW_MODEL = _PRESENTATION / "profile" / "ProfileViewModel.kt"
_RELEASE = _ROOT / "docs" / "RELEASE.md"
_README = _ROOT / "README.md"

# The three writes stage 100 gave the owner of a photograph row, with the route each one is the
# client's half of. A method that lives only in `ApiService.kt` is the defect this file exists for.
_MANAGEMENT_ROUTES = {
    "deletePhoto": 'router.delete("/me/photo/{photo_id}"',
    "makePhotoPrimary": 'router.post("/me/photo/{photo_id}/primary"',
    "reorderPhotos": 'router.patch("/me/photo/order"',
}

# The four writes one person performs on their own photograph row: stage 99 added the first, stage 100
# the rest. Every citation the release checklist and README.md carry for this path has to still name
# one of them, and between them the checklist has to name all four.
_PHOTO_WRITES = ("uploadPhoto", *_MANAGEMENT_ROUTES)

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
# The three decisions stage 100 gave the owner of a photograph row. A checklist item that demands a
# device check of the row has to name all three, or it asks about a row the screen no longer offers.
_REMOVAL_MENTION = re.compile(r"удал\w*|убер\w*|убрат\w*", re.IGNORECASE)
_HEAD_MENTION = re.compile(r"главн\w*", re.IGNORECASE)
_ORDER_MENTION = re.compile(r"перестав\w*|порядк\w*", re.IGNORECASE)
_KOTLIN_CITATION = re.compile(r"([A-Za-z]+\.kt):(\d+)(?:-(\d+))?")
_PYTHON_SET_ENTRY = re.compile(r'"([^"]+)"')
_KOTLIN_MAP_ENTRY = re.compile(r'^\s*"((?:[^"\\]|\\.)+)"\s+to\s', re.MULTILINE)
_VALIDATION_RAISE = re.compile(r'ValidationError\((f?)"((?:[^"\\]|\\.)+)"')
# A photograph's number is refused two ways: the order the person sent is wrong (422) or the row it
# names is not theirs (404). Both are messages about a photograph, so both owe the screen Russian.
_PHOTO_ROW_RAISE = re.compile(r'(?:ValidationError|NotFoundError)\(\s*(f?)"((?:[^"\\]|\\.)+)"')
_KOTLIN_FUN = re.compile(r"\s*(?:private |internal |override )?fun (\w+)")
# The two columns every photograph row is read by. Only one function in the backend is allowed to
# write them; a second writer is precisely how an order and its head come apart.
_ROW_COLUMN_WRITE = re.compile(r"\.(position|is_primary)\s*=(?!=)")


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _presentation_sites(name: str) -> list[str]:
    """Every place the client's screens or view models reach one repository method."""
    sites: list[str] = []
    for file in sorted(_PRESENTATION.rglob("*.kt")):
        for number, line in enumerate(_text(file).splitlines(), start=1):
            if name in line:
                sites.append(f"{file.relative_to(_ROOT)}:{number}")
    return sites


def _presentation_upload_sites() -> list[str]:
    """Every place the client's screens or view models reach the upload method."""
    return _presentation_sites("uploadPhoto")


def _kotlin_enclosing_fun(lines: list[str], index: int) -> str | None:
    """The name of the member function one line of Kotlin sits in.

    Walking back to the nearest `fun` is enough here: no method in the files this guard reads declares
    a local function, so the closest header above a call is the function that sends it.
    """
    for number in range(index, -1, -1):
        header = _KOTLIN_FUN.match(lines[number])
        if header and not lines[number].lstrip().startswith("//"):
            return header.group(1)
    return None


def _kotlin_fun_body(path: pathlib.Path, name: str) -> list[str]:
    """The lines of one member function, header to the line before the next header."""
    lines = _text(path).splitlines()
    starts = [
        i
        for i, line in enumerate(lines)
        if line.lstrip().startswith(f"fun {name}(") or line.lstrip().startswith(f"private fun {name}(")
    ]
    assert starts, f"{path.name} lost `fun {name}`"
    start = starts[0]
    tail = [
        i
        for i in range(start + 1, len(lines))
        if lines[i].lstrip().startswith("fun ") or lines[i].lstrip().startswith("private fun ")
    ]
    return lines[start : tail[0] if tail else len(lines)]


def _photo_row_writers() -> list[str]:
    """Every backend line that assigns a photograph's `position` or `is_primary`."""
    out: list[str] = []
    for file in sorted(_BACKEND_APP.rglob("*.py")):
        for number, line in enumerate(_text(file).splitlines(), start=1):
            if _ROW_COLUMN_WRITE.search(line):
                out.append(f"{file.relative_to(_ROOT).as_posix()}:{number}")
    return out


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
    """Every message the photograph routes can answer a photograph with, from their raise sites.

    The upload's refusals live in the pipeline, ``photo_service.py``; the three writes that own the
    row's order and its head live in ``profile_service.py``. Both halves are collected here, because
    both are answers about a photograph and the screen has to read either of them in Russian.
    """
    out: list[str] = []
    for _is_fstring, message in _VALIDATION_RAISE.findall(_text(_PHOTO_SERVICE)):
        # An f-string names data the server counted («Image exceeds {settings…} MB limit.»), so the part a
        # wording can be matched on is its literal opening, trailing space included — the Kotlin prefix
        # that answers it carries that same space. A plain message holds no brace, so it stays whole.
        out.append(message.split("{", 1)[0])
    row_text = _text(_PROFILE_SERVICE)
    for _is_fstring, message in _PHOTO_ROW_RAISE.findall(row_text):
        if "photo" in message.lower():
            out.append(message.split("{", 1)[0])
    # A number that is not the caller's is refused by one constant, raised from three places; the file
    # keeps it beside its imports, so the raise-site scan above never sees its text.
    if "_MISSING_PHOTO_MESSAGE" in row_text:
        held = re.search(r'_MISSING_PHOTO_MESSAGE = "([^"]+)"', row_text)
        assert held, (
            "profile_service.py raises `_MISSING_PHOTO_MESSAGE` without declaring the literal beside "
            "it, so this guard cannot tell what a stranger's photograph number is answered with"
        )
        out.append(held.group(1))
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
    note about the same route always negates itself («проверка здесь не снята»). A demand is therefore
    a sentence that mentions uploading and a photograph and says nothing against it.
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


def _row_demands(items: list[str]) -> list[str]:
    """Items of §8 that ask for the photograph row to be managed on a device.

    All three decisions have to be named together, in the item that sends somebody to a device: a
    checklist that asks the operator to delete a photograph and to set its head, but not to move it,
    lets the order go unverified while ``README.md`` promises the whole row. The counts item names all
    three too — as tests that exist — so the device word is what separates it from a demand.
    """
    return [
        item
        for item in items
        if "устройств" in item.lower()
        and _REMOVAL_MENTION.search(item)
        and _HEAD_MENTION.search(item)
        and _ORDER_MENTION.search(item)
    ]


def _client_manages_the_row() -> bool:
    route = _text(_ROUTE)
    return all(_presentation_sites(name) for name in _MANAGEMENT_ROUTES) and all(
        declaration in route for declaration in _MANAGEMENT_ROUTES.values()
    )


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


def test_the_client_reaches_every_write_to_the_photo_row_from_a_screen():
    """A route the owner of a photograph cannot reach is the defect this file was written for.

    Stage 99 closed that gap for the upload; stage 100 promised the same three ways round the rest of
    the row, so each write is checked on both halves at once: a caller under ``presentation/`` and the
    route literal it is the client's half of.
    """
    route = _text(_ROUTE)
    for name, declaration in _MANAGEMENT_ROUTES.items():
        sites = _presentation_sites(name)
        assert sites, (
            f"no screen or view model reaches {name}, so the profile tab cannot manage the row — "
            "the checklist item and README.md that say a person owns their photograph row are wrong "
            "again"
        )
        assert declaration in route, (
            f"{name} is called from {sites} but {route.relative_to(_ROOT)} no longer declares "
            f"{declaration}; the client is reaching for a route that is not there"
        )


def test_the_screen_asks_before_it_removes_a_photograph():
    """Deletion is the one write to the row that cannot be undone, so it owes a confirmation.

    The guard is structural on both sides of the pair: the view model sends the removal only from the
    function that reads the held number back, the two functions that open and close the question touch
    no repository, and the screen still asks the question in a dialog that names what removal does to
    the row's head.
    """
    lines = _text(_PROFILE_VIEW_MODEL).splitlines()
    senders = [i for i, line in enumerate(lines) if "profileRepository.deletePhoto" in line]
    assert senders, (
        "ProfileViewModel.kt no longer sends a photograph removal at all — the screen would be asking "
        "a question with nothing behind it"
    )
    from_confirm = [i for i in senders if _kotlin_enclosing_fun(lines, i) == "confirmDeletePhoto"]
    assert len(senders) == len(from_confirm), (
        f"a removal leaves ProfileViewModel.kt at {senders} while only `confirmDeletePhoto` may send "
        "one; a delete that does not wait for the answer is a photograph the person did not agree to "
        "lose"
    )
    for name in ("askDeletePhoto", "cancelDeletePhoto"):
        body = "\n".join(_kotlin_fun_body(_PROFILE_VIEW_MODEL, name))
        assert "profileRepository." not in body and "writeRow" not in body, (
            f"`{name}` now reaches the repository; the question and its refusal have to hold the "
            f"number in the view state only, or the row is written before the person answers:\n{body}"
        )
    assert "cancelDeletePhoto" in _text(_PROFILE_SCREEN), (
        "the profile screen dropped the refusal half of the question, leaving «Удалить фото?» with "
        "one answer"
    )

    screen = _text(_PROFILE_SCREEN)
    assert "AlertDialog" in screen, (
        "the removal question is no longer a dialog: a confirmation the person can scroll past is not "
        "a confirmation"
    )
    assert _REMOVAL_MENTION.search(screen) and _HEAD_MENTION.search(screen), (
        "the screen stopped naming what removal does to the row's head — losing the first photograph "
        "hands the flag to the next one, and the question has to say so before the answer"
    )


def test_position_and_is_primary_have_exactly_one_writer():
    """The order and its head drift apart the moment a second place is allowed to set them.

    ``_write_photo_order`` renumbers a whole row and lights the flag on its head in one pass; any other
    assignment in the backend is a write that can leave a photograph outside the row it belongs to, or a
    head the row does not lead with.
    """
    writers = _photo_row_writers()
    assert writers, (
        "nothing in the backend assigns a photograph's `position` or `is_primary` anymore, so "
        "PHOTO_DISPLAY_ORDER reads columns nobody maintains"
    )
    service = _PROFILE_SERVICE.relative_to(_ROOT).as_posix()
    lines = _text(_PROFILE_SERVICE).splitlines()
    start = next(
        i
        for i, line in enumerate(lines)
        if line.lstrip().startswith("async def _write_photo_order")
    )
    tail = [
        i
        for i in range(start + 1, len(lines))
        if lines[i].lstrip().startswith(("async def ", "def ", "class "))
    ]
    allowed = {f"{service}:{number}" for number in range(start + 1, (tail[0] if tail else len(lines)) + 1)}
    outside = [site for site in writers if site not in allowed]
    assert not outside, (
        f"{outside} write a photograph's order or its head outside `_write_photo_order`; the two "
        "columns have to come out of one list in one pass or they can disagree"
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
        and "e2e_journey.py" in item
        and "README" in item
    ]
    assert named, (
        "§11 does not keep the photograph question that is still open — the row is managed now, but "
        "nothing bounds how many photographs an account holds and the live path never touches one — "
        "naming the routes, the live path that skips them and the document that shares the gap"
    )


def test_the_checklist_asks_for_the_row_management_only_when_the_client_can_perform_it():
    items = _checklist_items(_release_section("8"))
    assert items, "RELEASE.md §8 has no checklist items to guard"
    demands = _row_demands(items)
    if _client_manages_the_row():
        assert demands, (
            "the profile tab can delete, promote and reorder a photograph now, and the release "
            "checklist still does not ask anybody to look at any of it on a device"
        )
        return
    assert not demands, (
        "the checklist asks for row management no client can perform: " + " | ".join(demands)
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
    # §8 grew a second client path with stage 101 — the blocked list and its removal, cited on the
    # settings screen. Those bullets are policed by test_a_block_made_by_mistake_can_be_seen_and_taken_back.py,
    # which knows the symbols of that row. This file keeps demanding its own: a bullet that names the
    # photograph row has to cite lines that still carry one of the four writes that row is made of.
    bullets = [
        bullet
        for bullet in section.split("- [ ]")
        if "сним" in bullet and _KOTLIN_CITATION.search(bullet)
    ]
    assert bullets, "§8 no longer cites the client path of a photograph row at all"
    checked = 0
    named: set[str] = set()
    for bullet in bullets:
        for file_name, start, end in _KOTLIN_CITATION.findall(bullet):
            candidates = list(_CLIENT_MAIN.rglob(file_name))
            assert candidates, f"§8 cites {file_name}, which is not in the client anymore"
            lines = _text(candidates[0]).splitlines()
            last = int(end or start)
            assert last <= len(lines), f"§8 cites {file_name}:{last}, the file has {len(lines)} lines"
            window = lines[int(start) - 1 : last]
            writes = {name for name in _PHOTO_WRITES if any(name in line for line in window)}
            assert writes, (
                f"§8 cites {file_name}:{start}-{last} as a photograph path, and that window no longer "
                "carries any of the four writes a photograph row is made of — the line moved and the "
                "citation followed nothing"
            )
            named |= writes
            checked += 1
    assert checked >= 3, f"§8 cites {checked} Kotlin lines; the client path lost its citations"
    assert named == set(_PHOTO_WRITES), (
        f"§8 cites the client path for {sorted(named)} only, so one of the four writes a person "
        "performs on their photograph row has no line the operator can be sent to"
    )

    readme = _text(_README)
    bullets = [block for block in readme.split("- **") if _PHOTO_MENTION.search(block)]
    assert bullets, "README.md no longer states what the app does and does not let a person do with a photo"
    for bullet in bullets:
        for file_name, start, end in _KOTLIN_CITATION.findall(bullet):
            candidates = list(_CLIENT_MAIN.rglob(file_name))
            assert candidates, f"README cites {file_name}, which is gone"
            lines = _text(candidates[0]).splitlines()
            window = lines[int(start) - 1 : int(end or start)]
            assert any(name in line for name in _PHOTO_WRITES), (
                f"README cites {file_name}:{start} for the client path and the line moved"
            )


def test_the_readme_promises_the_row_it_can_manage():
    """The storefront sentence and the shipped screen have to agree about the row.

    Stage 99 let README.md promise an upload and nothing else; a person who read «показывает то, что
    сервер принял» and then wanted the picture back had no button to find. The promises below are the
    three decisions stage 100 added, and they are checked against the copy rather than against a
    screenshot — the row itself is what the screen has to keep agreeing with.
    """
    readme = _text(_README)
    blocks = re.split(r"\n(?=(?:- )?\*\*)", readme)
    promised = [
        block
        for block in blocks
        if _PHOTO_MENTION.search(block)
        and _REMOVAL_MENTION.search(block)
        and _HEAD_MENTION.search(block)
        and _ORDER_MENTION.search(block)
    ]
    assert promised, (
        "README.md never tells a person they can remove a photograph, choose which one leads the row "
        "or set its order, although the profile tab now does all three"
    )
    assert any("/users/me/photo/order" in block for block in promised), (
        "the sentence that promises the row does not name the route that writes it, so a reader cannot "
        "check the promise against the API"
    )
