"""The queue stage 102 wrote on the server has a screen on the other side of the wire, and both halves
have to still describe one product.

``backend/app/api/v1/moderation.py`` mounted ``GET /reports``, ``GET /reports/{id}`` and
``POST /reports/{id}/review`` behind ``get_moderator`` in stage 102, and stage 103 gave them a client:
``android/app/src/main/java/app/befos/presentation/moderation/ModerationScreen.kt`` paints the queue, and
``SettingsScreen.kt`` offers the door to it to the account whose own answer says it holds the role. Before
stage 103 the queue could only be walked with ``curl`` — ``docs/OPERATIONS.md`` §14 sent an operator to
``UPDATE users SET is_moderator`` and to three routes no screen reached, and the promise that a complaint
gets read rather than merely stored was a promise about somebody's command line.

This file keeps that promise honest the way ``test_a_block_made_by_mistake_can_be_seen_and_taken_back.py``
keeps the block pair honest: by reading the sources. The JVM-only client tests prove what a view model does
with an answer it is handed; they never render a composable, so which screen holds the tap, which path that
tap walks, whether every refusal the moderation surface answers has Russian copy waiting for it, and
whether the words on the chips still name the statuses the server actually accepts are facts this suite can
check and the client suite cannot.

What they cannot check is stated in ``docs/RELEASE.md`` §8 instead: no test in this repository renders the
queue, opens the dialog, fits it under the keyboard, or taps a chip on a device. Two of the checks below are
about the opposite failure — a screen that would need no server at all — because the stage's brief forbids a
fixed panel showing static data, and a guard is the only place that prohibition can be enforced from.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_CLIENT_MAIN = _ROOT / "android" / "app" / "src" / "main"
_KOTLIN = _CLIENT_MAIN / "java" / "app" / "befos"
_PRESENTATION = _KOTLIN / "presentation"
_MODERATION_SCREEN = _PRESENTATION / "moderation" / "ModerationScreen.kt"
_MODERATION_VIEW_MODEL = _PRESENTATION / "moderation" / "ModerationViewModel.kt"
_SETTINGS_SCREEN = _PRESENTATION / "settings" / "SettingsScreen.kt"
_SETTINGS_VIEW_MODEL = _PRESENTATION / "settings" / "SettingsViewModel.kt"
_LABELS = _PRESENTATION / "common" / "Labels.kt"
_ROUTES = _PRESENTATION / "navigation" / "Routes.kt"
_NAV_HOST = _PRESENTATION / "navigation" / "BeFosNavHost.kt"
_API_SERVICE = _KOTLIN / "data" / "remote" / "ApiService.kt"
_REPO_IMPL = _KOTLIN / "data" / "repository" / "ModerationRepositoryImpl.kt"
_DTOS = _KOTLIN / "data" / "model" / "Dtos.kt"
_ERROR_TEXT = _KOTLIN / "core" / "network" / "BackendErrorText.kt"
_TESTS = _ROOT / "backend" / "tests"
_MOD_ROUTE = _ROOT / "backend" / "app" / "api" / "v1" / "moderation.py"
_ROUTER = _ROOT / "backend" / "app" / "api" / "router.py"
_MOD_SERVICE = _ROOT / "backend" / "app" / "services" / "moderation_service.py"
_DEPS = _ROOT / "backend" / "app" / "auth" / "deps.py"
_SCHEMAS = _ROOT / "backend" / "app" / "schemas" / "schemas.py"
_ENUMS = _ROOT / "backend" / "app" / "models" / "enums.py"

# The three halves of the moderation surface, named as the client declares each call, as the queue
# screen's own repository words it, and as the path each request walks. The literals are read off
# `moderation.py`, whose router carries `prefix="/reports"` — so the list route is the bare empty path
# and only the other two name the complaint they act on.
_QUEUE = (
    ("reports", "moderation.page", '@router.get("", response_model=ReportsPage)', "reports"),
    ("reportDetail", "moderation.detail", '@router.get("/{report_id}", response_model=ReportDetail)', "reports/$reportId"),
    ("reviewReport", "moderation.review", '@router.post("/{report_id}/review", response_model=ReviewResult)', "reports/$reportId/review"),
)

_PY_RAISE = re.compile(
    r'raise (?:ValidationError|NotFoundError|ConflictError|ForbiddenError)\(\s*(f?)"((?:[^"\\]|\\.)+)"'
)
_KOTLIN_MAP_ENTRY = re.compile(r'^\s*"((?:[^"\\]|\\.)+)"\s+to\s', re.MULTILINE)
_KOTLIN_FUN = re.compile(r"^\s*(?:private |internal |public |override |suspend )*fun (\w+)\(")
_ENUM_MEMBER = re.compile(r'^\s+[A-Z_]+ = "([^"]+)"', re.MULTILINE)


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _presentation_sites(fragment: str) -> list[str]:
    """Every place the client's screens or view models reach one repository call."""
    sites: list[str] = []
    for file in sorted(_PRESENTATION.rglob("*.kt")):
        for number, line in enumerate(_text(file).splitlines(), start=1):
            if fragment in line:
                sites.append(f"{file.relative_to(_ROOT).as_posix()}:{number}")
    return sites


def _fun_body(path: pathlib.Path, name: str) -> str:
    """The lines of one Kotlin member function, header to the line before the next header."""
    lines = _text(path).splitlines()
    starts = [i for i, line in enumerate(lines) if _KOTLIN_FUN.match(line) and _KOTLIN_FUN.match(line).group(1) == name]
    assert starts, f"{path.name} no longer declares `fun {name}`"
    start = starts[0]
    tail = [i for i in range(start + 1, len(lines)) if _KOTLIN_FUN.match(lines[i])]
    return "\n".join(lines[start : tail[0] if tail else len(lines)])


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


def _fun_body_python(path: pathlib.Path, name: str) -> str:
    """The source of one Python function, header to the next top-level header."""
    lines = _text(path).splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(rf"^(?:async )?def {name}\(", line)]
    assert starts, f"{path.name} no longer declares `def {name}`"
    start = starts[0]
    tail = [i for i in range(start + 1, len(lines)) if re.match(r"^(?:async )?(def|class) ", lines[i])]
    return "\n".join(lines[start : tail[0] if tail else len(lines)])


def _kotlin_const(name: str, path: pathlib.Path) -> int:
    """One integer constant from a Kotlin file, read rather than assumed."""
    match = re.search(rf"\bval {name}\b[^=\n]*=\s*(\d+)\b", _text(path))
    assert match, f"{path.name} no longer declares an integer `val {name}`"
    return int(match.group(1))


def _python_constant(name: str) -> int:
    match = re.search(rf"^{name} = (\d+)", _text(_MOD_SERVICE), re.MULTILINE)
    assert match, f"moderation_service.py no longer declares `{name} = <number>`"
    return int(match.group(1))


def _status_order() -> list[str]:
    """The statuses in the order the server's own enum declares them."""
    block = re.search(r"class ReportStatus\(StrEnum\):(.*?)(?=\n\nclass )", _text(_ENUMS), re.S)
    assert block, "models/enums.py no longer declares `class ReportStatus(StrEnum)`"
    return _ENUM_MEMBER.findall(block.group(1))


def _schema_fields(class_name: str) -> list[str]:
    """The annotated fields of one Pydantic model, with its parent's fields in front of them.

    ``ReportDetail`` extends ``ReportCard``, and the JSON the route answers carries both halves as one
    object; reading only the class's own lines would report the card's fields as missing from the DTO.

    Matches to the end of the file as well as to the next class, because the last model in the
    module has no next class to stop it — reading only up to ``\nclass`` would report the tail of
    the file as undeclared rather than as the model it is.
    """
    block = re.search(
        rf"class {class_name}\((\w+)\):(.*?)(?=\nclass |\Z)", _text(_SCHEMAS), re.S
    )
    assert block, f"schemas.py no longer declares `{class_name}` as a top-level model"
    parent, body = block.group(1), block.group(2)
    own = [
        match.group(1)
        for match in re.finditer(r"^\s{4}(\w+):\s", body, re.M)
        if not match.group(1).startswith("model_")
    ]
    return _schema_fields(parent) + own if parent != "BaseModel" else own


def _schema_fields_text(class_name: str) -> str:
    """The body of one Pydantic model, so a field can be looked for without re-listing them all."""
    block = re.search(
        rf"class {class_name}\((\w+)\):(.*?)(?=\nclass |\Z)", _text(_SCHEMAS), re.S
    )
    assert block, f"schemas.py no longer declares `{class_name}` as a top-level model"
    return block.group(2)


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


_MODULE_CONSTANT = re.compile(r'^([A-Z][A-Z0-9_]*) = "([^"]*)"$', re.MULTILINE)


def _inline_constants(text: str) -> str:
    """One test file's module-level string constants, written back at the places that use them.

    The stage-102 suite builds its queue paths from ``QUEUE = "/api/v1/reports"`` — both as a bare
    argument and inside f-strings like ``f"{QUEUE}/{report_id}"`` — so matching only whole literals
    would read a live, database-backed route call as a file that never sends one. The assignment
    line itself keeps its name, so a renamed constant still stops matching rather than matching
    something the file no longer calls.
    """
    for name, value in _MODULE_CONSTANT.findall(text):
        text = text.replace("{" + name + "}", value)
        text = re.sub(rf"\b{name}\b(?! *=)", f'"{value}"', text)
    return text


def _route_test_calls(fragment: str, method: str) -> list[str]:
    """Backend test files that send one HTTP method at one path fragment, this guard excluded."""
    out: list[str] = []
    for file in sorted(_TESTS.glob("test_*.py")):
        if file == pathlib.Path(__file__):
            continue
        text = _inline_constants(_text(file))
        if re.search(rf"client\.{method}\((?:[^()]|\n)*?{re.escape(fragment)}", text):
            out.append(file.name)
    return out


def test_the_three_queue_calls_walk_routes_the_application_mounts():
    """A screen with no route behind it, and a route with no caller, are the same defect twice.

    Stage 102 left the second half mounted and unreachable; stage 103 adds the first. Each triple is
    checked from both ends and from the middle, because a method that compiles unused is exactly how a
    queue screen with a dead tap ships.
    """
    route = _text(_MOD_ROUTE)
    for api_name, repo_call, literal, path in _QUEUE:
        body = _fun_body(_API_SERVICE, api_name)
        assert f'url(endpoint("{path}"))' in body, (
            f"ApiService.{api_name} no longer walks `{path}`, while moderation.py mounts "
            f"{literal}; the client is reaching for a route that is not there"
        )
        assert api_name in _text(_REPO_IMPL), (
            f"ModerationRepositoryImpl.kt no longer calls ApiService.{api_name}, so the queue's "
            "repository has a method the screen asks for and nothing answers"
        )
        sites = _presentation_sites(repo_call)
        assert sites, (
            f"no screen or view model reaches {repo_call}, so the moderation queue the brief asks for "
            f"is still only walkable by hand against {literal}"
        )
        assert literal in route, f"moderation.py no longer declares {literal}"
    assert "api_router.include_router(moderation.router" in _text(_ROUTER), (
        "moderation.py declares the routes but app/api/router.py stopped mounting them"
    )


def test_every_refusal_the_moderation_surface_answers_is_readable_in_russian():
    """The API contract is English and the product is Russian, and the queue is a screen now.

    While the routes could only be reached from a terminal, an untranslated refusal was an annoyance for
    whoever ran the command. With a screen in front of a moderator, the same refusal becomes the generic
    line for its status family — «Доступ запрещён.» in front of a door the account was told it holds —
    so every message raised by the service, and the guard's own refusal, needs copy.
    """
    keys = _translated_keys()
    prefixes = _translated_prefixes()
    messages = [message for _is_f, message in _PY_RAISE.findall(_text(_MOD_SERVICE))]
    guard = _PY_RAISE.findall(_fun_body_python(_DEPS, "get_moderator"))
    messages += [message for _is_f, message in guard]
    assert len(messages) >= 8, (
        f"the moderation surface now answers only {len(messages)} refusals, which is fewer than the "
        "surface was built with — re-read the service before trusting this check"
    )
    for message in messages:
        covered = message.lower() in keys or any(message.startswith(prefix) for prefix in prefixes)
        assert covered, (
            f"the moderation surface refuses with «{message}», which BackendErrorText.kt does not "
            "know — the queue would show a status line instead of what the server said"
        )


def test_the_role_refusal_says_who_it_is_refusing():
    """A queue that answers «Доступ запрещён.» about its own door leaves the reader no next step.

    The guard's message is one sentence about a role, and the account asking is the one that was just
    told it holds that role by `/users/me`. The copy has to name the moderator, because anything else
    reads as a session that expired — the advice the app already gives for four other refusals.
    """
    refusal = next(
        (message for _is_f, message in _PY_RAISE.findall(_fun_body_python(_DEPS, "get_moderator"))),
        None,
    )
    assert refusal, "deps.py's get_moderator no longer refuses with a message this check can read"
    copy = _kotlin_block("translated")
    value = re.search(rf'"{re.escape(refusal.lower())}"\s+to\s+"([^"]+)"', copy)
    assert value, f"«{refusal}» has no Russian line keyed to it"
    assert "модератор" in value.group(1), (
        f"the refusal of the queue reads «{value.group(1)}», which does not name the role it is about; "
        "an operator cannot tell it from an expired session"
    )


def test_the_status_words_are_the_statuses_the_server_accepts():
    """The chips and the decision buttons are built from one table, and that table is the enum's.

    ``ReportStatusLabels`` names the filter chips the queue draws and the words the history rows print.
    A status the server accepts and the table lacks would reach a moderator as a bare slug; one the table
    invents would offer a filter that can only ever answer empty — both are drift this check stops.
    """
    table = re.search(r"val ReportStatusLabels = linkedMapOf\((.*?)\)", _text(_LABELS), re.S)
    assert table, "Labels.kt no longer declares `val ReportStatusLabels = linkedMapOf(...)`"
    pairs = re.findall(r'"([^"]+)"\s+to\s+"([^"]+)"', table.group(1))
    keys = [key for key, _label in pairs]
    labels = [label for _key, label in pairs]
    assert keys == _status_order(), (
        f"ReportStatusLabels names {keys} while models/enums.py declares {_status_order()}; the queue "
        "and the API are describing different lifecycles"
    )
    assert len(set(labels)) == len(labels), f"two statuses share one word on the chips: {labels}"
    for key, label in pairs:
        assert label != key, f"«{key}» has no Russian word and would be drawn as its own slug"


def test_the_screen_reads_the_routes_instead_of_holding_a_copy_of_them():
    """The brief forbids a fixed panel showing static data, and this is where that can be checked.

    The queue is drawn from the repository through the view model, and its chips come from the server's
    answer rather than from a list the client keeps. Both halves are pinned: a screen that constructed a
    ``ReportCard`` would be showing a complaint that never arrived, and a dialog that built its own list
    of statuses would be offering a tap the write route was always going to refuse.
    """
    screen = _text(_MODERATION_SCREEN)
    assert "ModerationViewModel(it.moderationRepository)" in screen, (
        "ModerationScreen.kt no longer builds its view model from the queue's repository, so what it "
        "draws is not read from the server"
    )
    for forbidden in ("ReportCard(", "ReportDetail(", "listOf(card("):
        assert forbidden not in screen, (
            f"ModerationScreen.kt constructs {forbidden.rstrip('(')} itself — the queue would be "
            "showing data no route answered with"
        )
    assert "detail.allowedNextStatuses" in screen, (
        "the decision chips are no longer drawn from the answer's own choices, so the screen keeps a "
        "second copy of the transition table"
    )
    assert "ReportStatusLabels" in screen, (
        "the filter chips no longer come from the table that mirrors the server's statuses"
    )


def test_the_comment_bound_and_the_page_size_are_the_server_s_own_numbers():
    """Two numbers live on the server, and the client repeats both — so both can drift silently.

    A ceiling on the note higher than ``MAX_COMMENT`` turns a long account of a bad evening into a
    validation error the reader cannot fix; a page above ``MAX_PAGE`` is refused before it is read. Both
    come back as English contract text through the table above, so the fix belongs here, at the numbers.
    """
    assert _kotlin_const("MaxReviewComment", _MODERATION_VIEW_MODEL) == _python_constant("MAX_COMMENT"), (
        "ModerationViewModel.MaxReviewComment no longer equals moderation_service.MAX_COMMENT"
    )
    limit = _kotlin_const("PageLimit", _REPO_IMPL)
    max_page = _python_constant("MAX_PAGE")
    assert 0 < limit <= max_page, (
        f"ModerationRepositoryImpl asks for {limit} rows while the route refuses anything over "
        f"{max_page}; the first page of the queue would be one refusal"
    )


def test_the_rows_the_moderation_routes_answer_are_the_rows_the_screen_reads():
    """Four objects, two descriptions each, and no field either side can invent.

    The queue card, its page, the complaint's detail and one history row are all read from the server's
    answer, and a field added on one side only becomes a silently null column on the other — a moderator
    would be deciding a complaint whose note or whose date they cannot see. The names are compared as
    sets: ``ReportDetail`` answers the card's fields and its own as one object, and the client's DTO
    declares them in the order it reads them, which is not the order the two were written in.
    """
    for schema, dto in (
        ("ReportedAccountSummary", "ReportedAccountDto"),
        ("ReporterSummary", "ReporterDto"),
        ("ReportCard", "ReportCardDto"),
        ("ReportsPage", "ReportsPageDto"),
        ("ReportReviewRow", "ReportReviewRowDto"),
        ("ReportDetail", "ReportDetailDto"),
        ("ReviewResult", "ReviewResultDto"),
    ):
        server = _schema_fields(schema)
        client = _dto_serial_names(dto)
        assert len(server) == len(set(server)) and len(client) == len(set(client)), (
            f"{schema} / {dto} names a field twice, so the sets below hide which half has two"
        )
        assert set(server) == set(client), (
            f"{schema} answers {sorted(server)} while {dto} reads {sorted(client)}; the two lists of "
            "one row have drifted apart"
        )


def test_the_settings_entry_is_a_door_and_not_the_permission():
    """Hiding an entry is not authorisation, and the brief says so twice.

    The section is drawn when the account's own answer names the role, and it navigates to the one route
    that screen has. The permission stays where stage 102 put it: all three routes read the flag off the
    account row per request, so a moderator who reaches the queue by any other way than that button — or
    an ordinary account that reaches it by editing the client — gets the same answer from the server.
    """
    settings = _text(_SETTINGS_SCREEN)
    assert "if (state.isModerator)" in settings, (
        "SettingsScreen.kt no longer draws the queue's entry from the role the server answered"
    )
    assert "onOpenModeration" in settings, "the settings screen offers no tap that opens the queue"
    nav = _text(_NAV_HOST)
    assert "Routes.MODERATION" in nav and "ModerationScreen(" in nav, (
        "the queue's route is no longer registered, so the entry navigates to nothing"
    )
    assert 'const val MODERATION = "moderation"' in _text(_ROUTES), (
        "Routes.kt no longer names the moderation route the navigation host walks"
    )
    route = _text(_MOD_ROUTE)
    assert route.count("Depends(get_moderator)") == 3, (
        "the moderation surface no longer stands behind the role guard on all three routes; hiding "
        "the entry would then be the only thing keeping an ordinary account out"
    )


def test_the_role_the_entry_is_drawn_from_is_the_role_the_profile_route_answers():
    """The button is painted from one field, so that field has to be the server's, not a guess.

    ``ProfileOut`` carries ``is_moderator`` for the account's own read, the DTO decodes it, and the view
    model copies the answer into the state the section gates on. A link broken at any of the three leaves
    the settings screen offering the queue to somebody it is not for, or hiding it from a moderator.
    """
    assert "is_moderator: bool" in _schema_fields_text("ProfileOut"), (
        "ProfileOut no longer answers the role, so the client cannot draw the entry from the server"
    )
    assert 'is_moderator' in _data_class_body("ProfileDto"), (
        "ProfileDto stopped decoding the role the profile route answers with"
    )
    assert "isModerator = result.data.isModerator" in _text(_SETTINGS_VIEW_MODEL), (
        "SettingsViewModel no longer paints the role from the answer it got"
    )


def test_all_three_routes_are_answered_by_a_live_backend_test():
    """The guard above reads sources; the routes themselves are answered by the stage's own suites.

    This is the check that keeps the two halves of a stage from becoming one static file and one live
    file that never meet: a path has to appear in a request a real test sends against a real database.
    """
    pages = _route_test_calls("/api/v1/reports?", "get") + _route_test_calls('"/api/v1/reports"', "get")
    details = _route_test_calls("/api/v1/reports/", "get")
    reviews = _route_test_calls("/review", "post")
    assert pages, "no backend test reads GET /api/v1/reports"
    assert details, "no backend test reads GET /api/v1/reports/{report_id}"
    assert reviews, "no backend test sends POST /api/v1/reports/{report_id}/review"
