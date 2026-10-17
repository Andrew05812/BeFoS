"""A block that was put down by mistake has to be findable, and the app has to hold both halves of it.

``docs/USER_FLOWS.md`` and the account-deletion copy both treat a block as something a person does on
purpose. Measured on the tree before stage 101, it was also something a person could not take back:
``backend/app/api/v1/safety.py`` mounted ``POST /users/{user_id}/block`` and nothing undid it, and no
route answered the question «whom did I block?» — so a mistaken tap on the wrong card left the person
with no list to read and no write to send. The client said the same thing out loud: one line of
``PublicProfileScreen.kt`` promised «Разблокирование вернёт анкету в подбор, но не пару и не
сообщения.» while nothing in ``presentation/`` could reach such a route.

Stage 101 added the pair — ``DELETE /users/{user_id}/block`` and ``GET /users/me/blocks`` — and gave
the settings screen a section that reads the list and a dialog that sends the removal. This file keeps
the promise honest in the way ``test_a_release_checklist_demands_a_photo_no_screen_can_take.py`` keeps
the photograph row honest: by reading the sources. The JVM-only client tests prove what a view model
does with an answer it is handed; they never render a composable, so which screen holds the tap, which
path that tap walks and whether the words beside it still describe the product are facts this backend
suite can check and the client suite cannot.

The last check reads ``docs/RELEASE.md`` §8 rather than the client: the checklist now sends an operator
to named lines of the settings screen, and a line number that no longer carries the sentence it is
cited for is the defect the photograph file was written for. Here the anchors are the settings row's
own — the two repository calls, the dialog, the retry, the list, the screen-reader caption — because
several of those citations name copy an operator has to recognise on the screen rather than a request
it performs.

Ten checks follow. Each one is about a coupling that breaks silently: a write declared in
``ApiService.kt`` whose caller is deleted still compiles, a route renamed on one side of the wire still
starts, an untranslated refusal still returns 200 from the server while putting English on a Russian
screen, and a list schema that grows a field leaves the client reading null. What they cannot check is
stated in ``docs/RELEASE.md`` §8 instead: no test in this repository renders the section, paints the
dialog, or taps a row on a device.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_CLIENT_MAIN = _ROOT / "android" / "app" / "src" / "main"
_PRESENTATION = _CLIENT_MAIN / "java" / "app" / "befos" / "presentation"
_SETTINGS_SCREEN = _PRESENTATION / "settings" / "SettingsScreen.kt"
_SETTINGS_VIEW_MODEL = _PRESENTATION / "settings" / "SettingsViewModel.kt"
_API_SERVICE = _CLIENT_MAIN / "java" / "app" / "befos" / "data" / "remote" / "ApiService.kt"
_DTOS = _CLIENT_MAIN / "java" / "app" / "befos" / "data" / "model" / "Dtos.kt"
_ERROR_TEXT = _CLIENT_MAIN / "java" / "app" / "befos" / "core" / "network" / "BackendErrorText.kt"
_TESTS = _ROOT / "backend" / "tests"
_ROUTE = _ROOT / "backend" / "app" / "api" / "v1" / "safety.py"
_ROUTERS = _ROOT / "backend" / "app" / "api" / "router.py"
_SAFETY_SERVICE = _ROOT / "backend" / "app" / "services" / "safety_service.py"
_SCHEMAS = _ROOT / "backend" / "app" / "schemas" / "schemas.py"
_RELEASE_DOC = _ROOT / "docs" / "RELEASE.md"

# The two halves of the undo, named as the client declares them and as the server mounts them. A
# method that lives only in `ApiService.kt` and a route the client never reach are the same defect
# seen from either side of the wire, and both are what the checks below are here to catch.
_BLOCKS_LIST = "blockedUsers"
_RELEASE = "unblock"
_ROUTE_LITERALS = {
    _RELEASE: '@router.delete("/users/{user_id}/block"',
    _BLOCKS_LIST: '@router.get("/users/me/blocks"',
}

# A block is undone from the dialog and from nowhere else, so the write has exactly one sender in the
# view model and the read has exactly one function that owns it.
_RELEASE_SENDER = "confirmUnblock"
_LIST_READER = "loadBlocks"

# The sentences the section is made of. Each is checked by its literal text rather than by a
# description of it: a screen that stops saying «Вы пока никого не блокировали.» has either taken the
# empty answer out or renamed it, and both are visible from here.
_SCREEN_STRINGS = (
    "Кого вы заблокировали",
    "Не удалось проверить, кого вы заблокировали.",
    "Вы пока никого не блокировали.",
    "Разблокировать",
)

_KOTLIN_FUN = re.compile(r"\s*(?:private |internal |override |suspend )*fun (\w+)")
_KOTLIN_MAP_ENTRY = re.compile(r'^\s*"((?:[^"\\]|\\.)+)"\s+to\s', re.MULTILINE)
# The settings citations §8 sends an operator to. A single number reads as a one-line window, so a
# bullet that names a two-line citation without a dash is pointing at one line rather than a range.
_KOTLIN_CITATION = re.compile(r"([A-Za-z]+\.kt):(\d+)(?:-(\d+))?")
# The anchors a settings bullet's cited lines have to still name: the two repository calls, the dialog
# the write leaves from, the reader «Повторить» calls, the list the rows are drawn from, the caption
# a screen reader speaks, the name that caption speaks, the placeholder the read leaves on screen while
# it is out, and the sentence that builds a row's second line. An empty window here means the copy
# moved and the citation followed nothing.
_BLOCK_ANCHORS = (
    _RELEASE,
    _BLOCKS_LIST,
    _RELEASE_SENDER,
    "confirmUnblock",
    _LIST_READER,
    "state.blocked",
    "contentDescription",
    "blockedRowWord",
    "user.name",
    "SkeletonBlock",
)
_PYTHON_RAISE = re.compile(r'(?:ValidationError|NotFoundError)\(\s*(f?)"((?:[^"\\]|\\.)+)"')
# A block that cannot be released is one thing; a sentence saying releasing it is impossible is
# another. The pattern is deliberately narrow: it fires only when the same line names the release
# and refuses it, which is what the stale client copy did before stage 101 corrected it.
_FOREVER_CLAIM = re.compile(
    r"(?:разблокир\w*|отменить.{0,20}блокиров\w*|снятие блока)", re.IGNORECASE
)
_DENIAL = re.compile(r"нельзя|невозможно|не можно|нет способа|навсегда|невероятно", re.IGNORECASE)


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _presentation_sites(name: str) -> list[str]:
    """Every place the client's screens or view models reach one repository method."""
    sites: list[str] = []
    for file in sorted(_PRESENTATION.rglob("*.kt")):
        for number, line in enumerate(_text(file).splitlines(), start=1):
            if name in line:
                sites.append(f"{file.relative_to(_ROOT).as_posix()}:{number}")
    return sites


def _enclosing_fun(lines: list[str], index: int) -> str | None:
    """The member function one line of Kotlin sits in, walking back to the nearest header."""
    for number in range(index, -1, -1):
        header = _KOTLIN_FUN.match(lines[number])
        if header and not lines[number].lstrip().startswith("//"):
            return header.group(1)
    return None


def _fun_body(path: pathlib.Path, name: str) -> list[str]:
    """The lines of one Kotlin member function, header to the line before the next header.

    Matching tolerates ``suspend`` and visibility modifiers because the client's API methods are
    declared as ``suspend fun``; a header walk that demanded ``fun name(`` exactly would report a
    renamed file rather than a renamed modifier, which is the wrong diagnosis to print.
    """
    lines = _text(path).splitlines()
    header = re.compile(rf"^\s*(?:private |internal |public |override |suspend )*fun {name}\(")
    starts = [i for i, line in enumerate(lines) if header.match(line)]
    assert starts, f"{path.name} no longer declares `fun {name}`"
    start = starts[0]
    tail = [
        i
        for i in range(start + 1, len(lines))
        if re.match(r"^\s*(?:private |internal |public |override |suspend )*fun \w+\(", lines[i])
    ]
    return lines[start : tail[0] if tail else len(lines)]


def _async_service_method(name: str) -> str:
    """The body of one ``SafetyService`` method, header to the header of the next one."""
    lines = _text(_SAFETY_SERVICE).splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip().startswith(f"async def {name}(")]
    assert starts, f"safety_service.py no longer declares `async def {name}`"
    start = starts[0]
    tail = [
        i
        for i in range(start + 1, len(lines))
        if lines[i].startswith("    async def ") or lines[i].startswith("    def ")
    ]
    return "\n".join(lines[start : tail[0] if tail else len(lines)])


def _translated_keys() -> set[str]:
    return {match.group(1).lower() for match in _KOTLIN_MAP_ENTRY.finditer(_kotlin_block("translated"))}


def _translated_prefixes() -> set[str]:
    return {match.group(1) for match in _KOTLIN_MAP_ENTRY.finditer(_kotlin_block("translatedPrefixes"))}


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


def _schema_fields(class_name: str) -> list[str]:
    """The annotated fields of one Pydantic model, in the order the server declares them."""
    block = re.search(rf"class {class_name}\(BaseModel\):(.*?)(?=\nclass )", _text(_SCHEMAS), re.S)
    assert block, f"schemas.py no longer declares `{class_name}` as a top-level BaseModel"
    return [
        match.group(1)
        for match in re.finditer(r"^\s{4}(\w+):\s", block.group(1), re.M)
        if not match.group(1).startswith("model_")
    ]


def _data_class_body(name: str) -> str:
    """The parameter list of one Kotlin data class, up to its closing paren at column zero."""
    lines = _text(_DTOS).splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(rf"^data class {name}\(", line)]
    assert starts, f"Dtos.kt no longer declares `data class {name}`"
    body: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if line == ")":
            break
        body.append(line)
    return "\n".join(body)


def _py_function_body(path: pathlib.Path, name: str) -> str:
    """The source of one Python function, header to the next top-level header."""
    lines = _text(path).splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(f"async def {name}(")]
    assert starts, f"{path.name} no longer declares `async def {name}`"
    start = starts[0]
    tail = [i for i in range(start + 1, len(lines)) if re.match(r"^(async def|def|class) ", lines[i])]
    return "\n".join(lines[start : tail[0] if tail else len(lines)])


def _dto_serial_names(class_name: str) -> list[str]:
    """The wire names one Kotlin DTO declares, in declaration order.

    A field without ``@SerialName`` serialises under its Kotlin name, so both shapes have to be read:
    taking only the annotated ones would let a renamed field look like a missing one.
    """
    names: list[str] = []
    pattern = re.compile(r'@SerialName\("([^"]+)"\)\s+val\s+(\w+)|\bval\s+(\w+)\s*:')
    for match in pattern.finditer(_data_class_body(class_name)):
        names.append(match.group(1) or match.group(3))
    return names


def _route_test_calls(fragment: str, method: str) -> list[str]:
    """Backend test files that send one HTTP method at one path fragment, this guard excluded.

    The call and its path are matched across the line break because the suite writes the longer
    requests as ``client.delete(\\n    f"/api/v1/users/{other['user_id']}/block", ...)``.
    """
    out: list[str] = []
    for file in sorted(_TESTS.glob("test_*.py")):
        if file == pathlib.Path(__file__):
            continue
        if re.search(rf"client\.{method}\((?:[^()]|\n)*?{re.escape(fragment)}", _text(file)):
            out.append(file.name)
    return out


def test_the_undoes_of_a_block_reach_the_server_from_a_screen():
    """A route nobody can tap is the defect this file exists for.

    Both halves are checked the same way the photograph row is: a caller under ``presentation/`` for
    every client method, and the route literal each method is the client's half of.
    """
    route = _text(_ROUTE)
    for name in (_RELEASE, _BLOCKS_LIST):
        sites = _presentation_sites(name)
        assert sites, (
            f"no screen or view model reaches {name}, so the settings screen cannot offer what "
            "USER_FLOWS.md and the block dialog's own copy promise"
        )
        assert _ROUTE_LITERALS[name] in route, (
            f"{name} is called from {sites}, but safety.py no longer declares "
            f"{_ROUTE_LITERALS[name]}; the client is reaching for a route that is not mounted"
        )
    assert "api_router.include_router(safety.router" in _text(_ROUTERS), (
        "safety.py declares the routes but app/api/router.py stopped mounting them, so neither call "
        "the client makes can be answered"
    )


def test_the_client_paths_are_the_routes_the_application_mounts():
    """One sentence per side of the wire: the path and the verb the client sends are the ones mounted.

    The endpoint strings are read out of each method's own body rather than searched across the file,
    because ``users/$userId/block`` is also the path of the block write, and a release that had been
    changed to POST would still be found by a whole-file search.
    """
    for name, method, path in (
        (_RELEASE, "HttpMethod.Delete", "users/$userId/block"),
        (_BLOCKS_LIST, "HttpMethod.Get", "users/me/blocks"),
    ):
        body = "\n".join(_fun_body(_API_SERVICE, name))
        assert method in body, f"ApiService.{name} no longer sends {method}: {body!r}"
        assert f'url(endpoint("{path}"))' in body, (
            f"ApiService.{name} no longer walks `{path}`; re-read it against the literal in safety.py "
            f"({_ROUTE_LITERALS[name]}) before the copy that names the route is corrected"
        )


def test_only_the_dialog_sends_a_release_and_only_its_reader_reads_the_list():
    """The undo is a write with no screen behind it but one question, so it has one sender.

    The same rule holds the photograph deletion: a removal that can be triggered without the answer
    being read back is a state the person never agreed to. Here the second half matters too — the
    retry on the list is a read, and a screen that refreshed the profile to re-read a list would be
    sending a request the section never asked for.
    """
    lines = _text(_SETTINGS_VIEW_MODEL).splitlines()
    senders = [i for i, line in enumerate(lines) if "safetyRepository.unblock" in line]
    assert senders, "SettingsViewModel.kt sends no release at all, while the screen still asks"
    off_dialog = [i for i in senders if _enclosing_fun(lines, i) == _RELEASE_SENDER]
    assert len(senders) == len(off_dialog), (
        f"a release leaves SettingsViewModel.kt at {[i + 1 for i in senders]} while only "
        f"`{_RELEASE_SENDER}` may send one — line {[i + 1 for i in senders if i not in off_dialog]}"
    )

    readers = [i for i, line in enumerate(lines) if "safetyRepository.blockedUsers" in line]
    assert readers, "SettingsViewModel.kt never reads the list it draws"
    in_reader = [i for i in readers if _enclosing_fun(lines, i) == _LIST_READER]
    assert len(readers) == len(in_reader), (
        f"the list is read at {[i + 1 for i in readers]} but only `{_LIST_READER}` owns that read; "
        "a second caller is how a retry stops being one request"
    )


def test_the_settings_screen_holds_the_list_the_dialog_and_the_retry():
    """Every state the section can be in has a sentence in the source that draws it.

    The four strings are the four answers the read can produce or cause: still out, refused, empty,
    and holding rows. The last one has no literal to match — it is the row loop — so it is pinned by
    the tap each row carries instead, which is what a screen without the loop would lose.
    """
    screen = _text(_SETTINGS_SCREEN)
    for string in _SCREEN_STRINGS:
        assert string in screen, f"SettingsScreen.kt lost «{string}»"
    assert "vm.askUnblock" in screen and "state.confirmUnblock" in screen, (
        "the screen no longer asks before releasing: the write would be one tap from a list row"
    )
    assert "vm::loadBlocks" in screen, (
        "«Повторить» no longer calls the read it belongs to, so the section offers a retry that "
        "cannot re-read anything"
    )
    assert "contentDescription" in screen, (
        "a release button with no description of whom it releases leaves a screen reader saying "
        "«Разблокировать» with nobody named"
    )


def test_the_release_paints_the_rows_the_server_holds():
    """The write and the read are the same question, so the answer is a list and the screen uses it.

    A release that returned a bare ok would leave the row the tap named dropped locally and standing
    on the server — which is exactly what happens when a second device, or a block that was already
    gone, is the one telling the truth.
    """
    route_body = _py_function_body(_ROUTE, "unblock_user")
    assert "service.unblock" in route_body and "BlockedUsersResponse" in route_body, (
        "DELETE /users/{user_id}/block no longer answers with the surviving list"
    )
    api_body = "\n".join(_fun_body(_API_SERVICE, _RELEASE))
    assert "ApiResult<BlockedUsersDto>" in api_body, (
        "ApiService.unblock stopped decoding the list the route answers with"
    )
    lines = _text(_SETTINGS_VIEW_MODEL).splitlines()
    updates = [i for i, line in enumerate(lines) if "blocked = result.data" in line]
    assert updates, (
        "SettingsViewModel.kt no longer paints the list from the answer it got, so a screen after a "
        "release is showing rows it hoped for"
    )


def test_every_refusal_the_block_pair_answers_is_readable_in_russian():
    """The API contract is English and the product is Russian; both halves of the pair owe a line.

    The block write already had its refusals translated. The release adds two of its own and the read
    can fail the same way any route can, so each message raised by either method is checked against
    the client's own table — a refusal that is missing there reaches the screen as the status family's
    generic line, which on this path reads as an advice the person cannot follow.
    """
    keys = _translated_keys()
    prefixes = _translated_prefixes()
    for method in ("block", "unblock"):
        for _is_fstring, message in _PYTHON_RAISE.findall(_async_service_method(method)):
            lowered = message.lower()
            covered = lowered in keys or any(message.startswith(prefix) for prefix in prefixes)
            assert covered, (
                f"safety_service.{method} refuses with «{message}», which BackendErrorText.kt does "
                "not know — the screen would show a status line instead of what the server said"
            )


def test_a_refused_release_is_not_the_generic_not_found():
    """A block this account never placed is not a deleted account, and the copy has to know that.

    Both messages answer 404 with a list to re-read, so the pair would collapse into the status line
    «Этого здесь нет — возможно, анкету или чат удалили.» if the table only had the fallback. That
    sentence sends a person to look for a profile that is still there.
    """
    release_refusal = next(
        (
            message
            for _is_fstring, message in _PYTHON_RAISE.findall(_async_service_method("unblock"))
            if "not blocked" in message.lower()
        ),
        None,
    )
    assert release_refusal, (
        "unblock no longer refuses a block the caller never placed, so this check's premise is gone — "
        "re-read the route before changing the copy"
    )
    copy = _kotlin_block("translated")
    value = re.search(rf'"{re.escape(release_refusal.lower())}"\s+to\s+"([^"]+)"', copy)
    assert value, f"«{release_refusal}» has no Russian line keyed to it"
    assert "блокир" in value.group(1), (
        f"the refusal of a release reads «{value.group(1)}», which does not name the block it is "
        "about; the person cannot tell it from a deleted profile"
    )


def test_the_card_the_server_answers_is_the_card_the_screen_reads():
    """One row, two descriptions of it, and no field either side can invent.

    The client shows a name, an age, a city and a photograph, and drops a row whose moment it cannot
    read rather than drawing a date it made up. A field added on one side and not the other is a
    silently null column — the screen would say «—» about something the server was sending.
    """
    server = _schema_fields("BlockedUserSummary")
    client = _dto_serial_names("BlockedUserDto")
    assert server == client, (
        f"BlockedUserSummary answers {server} while BlockedUserDto reads {client}; the two lists of "
        "one row have drifted apart"
    )
    for field in ("user_id", "name", "age", "city", "photo_url", "blocked_at"):
        assert field in server, f"{field} left the card the list route answers with"


def test_both_routes_are_called_by_a_backend_test():
    """The guard above reads sources; the routes themselves are answered by the stage-101 suite.

    This is the check that keeps the two halves of the stage from becoming one static file and one
    live file that never meet: a path fragment has to appear in a request a real test sends.
    """
    reads = _route_test_calls("/users/me/blocks", "get")
    writes = [name for name in _route_test_calls("/block", "delete") if "undo" in name or "block" in name]
    assert reads, "no backend test reads GET /users/me/blocks"
    assert writes, "no backend test sends DELETE /users/{user_id}/block"


def test_no_client_sentence_still_calls_a_block_forever():
    """The copy written while no route undid a block is a defect the moment one exists.

    ``PublicProfileScreen.kt`` told the person «Разблокирование вернёт анкету в подбор, но не пару и
    не сообщения.» before any such route was mounted — advice with nowhere to follow it. The line is
    now true and names the settings section, so the check is that no sentence in the client both names
    the release and denies it, on any screen rather than the one this stage touched.
    """
    offenders: list[str] = []
    for file in sorted(_CLIENT_MAIN.rglob("*.kt")):
        for number, line in enumerate(_text(file).splitlines(), start=1):
            if _FOREVER_CLAIM.search(line) and _DENIAL.search(line):
                offenders.append(f"{file.relative_to(_ROOT).as_posix()}:{number}: {line.strip()}")
    assert not offenders, (
        "a client sentence still says a block cannot be released, while the settings section offers "
        f"the release: {offenders}"
    )


def test_the_release_doc_cites_lines_that_still_hold_the_settings_row():
    """§8 sends an operator to named lines of the settings screen; those lines have to still hold it.

    The photograph file demands that every citation names one of its four writes. The settings bullets
    also cite sentences a person reads — the question, the empty answer, the caption — and a write
    symbol is not in those lines, so the anchor here is the row's own vocabulary: the two repository
    calls, the dialog the write leaves from, the reader the retry calls, the list the rows are drawn
    from, and the two strings that build a row. A window naming none of them is a citation that
    followed nothing.
    """
    release = _text(_RELEASE_DOC)
    start = release.find("\n## 8.")
    assert start >= 0, "docs/RELEASE.md lost section 8"
    tail = release[start + 1 :]
    stop = tail.find("\n## ")
    section = tail[:stop] if stop >= 0 else tail
    bullets = [
        bullet
        for bullet in section.split("- [ ]")
        if ("«Настройки»" in bullet or "заблокированных" in bullet or "блокировки" in bullet)
        and _KOTLIN_CITATION.search(bullet)
    ]
    assert bullets, (
        "§8 no longer cites a line of the settings screen; the checklist stopped naming the path an "
        "operator has to tap"
    )
    named: set[str] = set()
    for bullet in bullets:
        for file_name, start_line, end_line in _KOTLIN_CITATION.findall(bullet):
            if not file_name.startswith("Settings"):
                continue
            candidates = list(_CLIENT_MAIN.rglob(file_name))
            assert candidates, f"§8 cites {file_name}, which is not in the client anymore"
            lines = _text(candidates[0]).splitlines()
            last = int(end_line or start_line)
            assert last <= len(lines), (
                f"§8 cites {file_name}:{last}, but the file has {len(lines)} lines"
            )
            window = "\n".join(lines[int(start_line) - 1 : last])
            anchors = {name for name in _BLOCK_ANCHORS if name in window}
            assert anchors, (
                f"§8 cites {file_name}:{start_line}-{last} as the settings row, and that window names "
                f"none of the anchors the row is made of — the copy moved and the citation followed "
                "nothing"
            )
            named |= anchors
    assert _RELEASE in named and _BLOCKS_LIST in named, (
        f"§8 cites the settings path for {sorted(named)} only, so either the read of the list or the "
        "release itself has no line the operator can be sent to"
    )
