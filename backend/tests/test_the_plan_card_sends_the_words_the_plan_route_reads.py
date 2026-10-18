"""The plan card's two words leave on the wire the route reads them from.

``PATCH /plans/{plan_id}`` has been in the API since stage 95, and ``PlanOut`` has carried ``place``
and ``note`` since then too — the pair's plan screen printed both of them and had no verb for either.
A person could read «Место: Кинотеатр на Петровке» on a card they could not write, which is the same
class of gap stage 99 found on the photograph row: a method declared in three client files and
reachable from no screen is not a feature, and a field printed by a screen that cannot set it is not
either.

Stage 106 gave the card its writing side. What no test set can see on its own is the seam between the
two languages: the Kotlin request's serial names, the Python schema's field names, the route literal
the client calls, and the Russian wording of the refusals that route answers. Each of those can drift
on one side only, and every drift is silent on the side that moved — a renamed field arrives as an
absent one, which this contract reads as «не трогать», so the save looks like it worked while the word
the pair typed never left the phone.

The checks below therefore pair the two halves rather than describe either:

``PlanEditRequest`` (``Dtos.kt``) against ``PlanEditIn`` (``schemas.py``), field for field. The one
field the schema holds and the client does not send is named, because it goes through its own route.

``editPlanWords`` (``ApiService.kt``) against the router's own decorator, and a caller under
``presentation/`` — the reach check that this file's predecessor was written for.

The two refusals a save can actually meet against the literals at their raise sites and against the
keys in ``BackendErrorText.kt``. The other two refusals of ``PlanService.edit`` are deliberately not
demanded here: the client trims what it sends and never puts a blank place or an over-long note on the
wire, so those messages belong to a body this app cannot produce. They are named below so the omission
stays a decision rather than an oversight.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_CLIENT_MAIN = _ROOT / "android" / "app" / "src" / "main"
_PRESENTATION = _CLIENT_MAIN / "java" / "app" / "befos" / "presentation"
_DTOS = _CLIENT_MAIN / "java" / "app" / "befos" / "data" / "model" / "Dtos.kt"
_API_SERVICE = _CLIENT_MAIN / "java" / "app" / "befos" / "data" / "remote" / "ApiService.kt"
_REPOSITORIES = _CLIENT_MAIN / "java" / "app" / "befos" / "domain" / "repository" / "Repositories.kt"
_REPO_IMPL = _CLIENT_MAIN / "java" / "app" / "befos" / "data" / "repository" / "PlanRepositoryImpl.kt"
_ERROR_TEXT = _CLIENT_MAIN / "java" / "app" / "befos" / "core" / "network" / "BackendErrorText.kt"
_PLANS_SCREEN = _PRESENTATION / "plans" / "PlansScreen.kt"
_PLANS_VIEW_MODEL = _PRESENTATION / "plans" / "PlansViewModel.kt"
_PLAN_BUCKETS = _PRESENTATION / "plans" / "PlanBuckets.kt"
_SCHEMA = _ROOT / "backend" / "app" / "schemas" / "schemas.py"
_ROUTE = _ROOT / "backend" / "app" / "api" / "v1" / "plans.py"
_PLAN_SERVICE = _ROOT / "backend" / "app" / "services" / "plan_service.py"

# The refusals a save from this card can meet. `Plan not found.` is the answer a dissolved pair gives
# every plan verb, and the closed plan is the race the card cannot see: the other half cancelling while
# this screen was open. Both have to be readable in Russian, because both are answered by a card the
# person is still looking at.
_SAVE_REFUSALS = (
    "Plan not found.",
    "This plan is closed, so there is nothing left to change.",
)
# Named rather than demanded: reachable only from a body this client does not build. `planWordsEdit`
# trims before it compares, so a field rubbed clean travels as `clear_place`/`clear_note` and never as
# a blank string, and the note's ceiling is held by the schema's own `max_length` before the service
# is ever asked.
_UNREACHABLE_REFUSALS = (
    "A place has to be a place, or it should be left unwritten.",
    "A note to the pair is at most 500 characters.",
)
# The field the schema reads and this card does not write. `my_note` is a person's own remark about
# their plan and leaves through `PUT /plans/{plan_id}/note`, which the shared card shows nobody else.
_CLIENT_SENDS_LESS = {"my_note"}

_KOTLIN_MAP_ENTRY = re.compile(r'^\s*"((?:[^"\\]|\\.)+)"\s+to\s', re.MULTILINE)
_PY_FIELD = re.compile(r"^\s{4}(\w+): [^=]+", re.MULTILINE)
_SERIAL_NAME = re.compile(r'@SerialName\("([^"]+)"\)')
# One property line of a Kotlin data class: either `@SerialName("x") val y:` or a bare `val y:`.
_KOTLIN_PROPERTY = re.compile(r"^\s*(?:@SerialName\(\"([^\"]+)\"\)\s*)?val (\w+)\s*:")


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _class_body(path: pathlib.Path, declaration: str) -> str:
    """The lines of one class, from its header to the next top-level declaration.

    Both halves of this contract are flat data classes, so a header-to-header window is enough to
    collect their fields, and it fails loudly if either class is folded into another file.
    """
    lines = _text(path).splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(declaration)]
    assert starts, f"{path.name} no longer declares `{declaration}` at top level"
    body: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if re.match(r"^(class |def |async def |@|private |public )", line):
            break
        body.append(line)
    return "\n".join(body)


def _kotlin_wire_names() -> set[str]:
    """The names the client's JSON actually puts on the wire for a plan-words save.

    ``explicitNulls = false`` in ``HttpClientFactory.kt`` is what makes an unchanged field absent
    rather than null, and this reads the names, not the nullability: a property the serializer renames
    is a field the server never sees.
    """
    out: set[str] = set()
    for line in _class_body(_DTOS, "data class PlanEditRequest(").splitlines():
        header = _KOTLIN_PROPERTY.match(line)
        if header:
            out.add(header.group(1) or header.group(2))
    return out


def _python_plan_edit_fields() -> set[str]:
    body = _class_body(_SCHEMA, "class PlanEditIn(BaseModel):")
    return {name for name in _PY_FIELD.findall(body)}


def _translated_keys() -> set[str]:
    lines = _text(_ERROR_TEXT).splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("private val translated")]
    assert starts, "BackendErrorText.kt lost `private val translated`"
    body: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if line == ")":
            break
        body.append(line)
    return {match.group(1).lower() for match in _KOTLIN_MAP_ENTRY.finditer("\n".join(body))}


def _presentation_sites(name: str) -> list[str]:
    sites: list[str] = []
    for file in sorted(_PRESENTATION.rglob("*.kt")):
        for number, line in enumerate(_text(file).splitlines(), start=1):
            if name in line:
                sites.append(f"{file.relative_to(_ROOT).as_posix()}:{number}")
    return sites


def test_the_card_sends_exactly_the_fields_the_route_reads():
    client_names = _kotlin_wire_names()
    server_names = _python_plan_edit_fields()
    assert client_names, "PlanEditRequest.kt holds no properties, so the save sends an empty body"
    assert server_names, "PlanEditIn lost its fields, so nothing the client sends can be read"

    unknown = sorted(client_names - server_names)
    assert not unknown, (
        f"the plan card sends {unknown}, which `PlanEditIn` does not name. A field the schema does not "
        "read is dropped on the floor: the person typed a word, the request carried it, and the plan "
        "kept whatever it already held"
    )
    held = sorted(server_names - client_names)
    assert held == sorted(_CLIENT_SENDS_LESS), (
        f"the route reads {held} and the card sends none of them. The one gap this file accepts is "
        "`my_note`, which leaves through `PUT /plans/{plan_id}/note`; a second silent gap is a field "
        "the pair cannot set from the screen that shows it"
    )


def test_the_erase_flags_are_the_clients_to_ask_with():
    """An absent field means «не трогать», so emptying a word needs a flag of its own.

    The card prefills both fields and the client omits the ones that did not move, which leaves no
    request-shaped way to say «remove the place». Both halves have to keep naming the two flags, or the
    erase becomes a no-op the person cannot undo except by typing a space — which the server refuses.
    """
    for flag in ("clear_place", "clear_note"):
        assert flag in _kotlin_wire_names(), f"PlanEditRequest stopped sending {flag}"
        assert flag in _python_plan_edit_fields(), f"PlanEditIn stopped reading {flag}"


def test_the_save_reaches_the_route_from_a_screen():
    """A method that lives only in the data layer is the defect this file exists for.

    Checked on both halves at once, the way stage 99's photo guard does it: the client's call carries
    the PATCH to the plan's own address, the router still declares that address, and something under
    ``presentation/`` actually reaches it.
    """
    api = _text(_API_SERVICE)
    assert "fun editPlanWords(" in api, "ApiService.kt lost the plan-words write altogether"
    after = api.split("fun editPlanWords(", 1)[1]
    # Only the one method's own lines: a later verb that happens to PATCH something else must not be
    # read as this write having kept its verb.
    body = after.split("suspend fun ", 1)[0]
    assert "HttpMethod.Patch" in body, (
        "the plan-words write no longer sends a PATCH; the route answers no other verb, and a PUT "
        "would replace the whole arrangement rather than the two words it holds"
    )
    assert 'endpoint("plans/$planId")' in body, (
        "the plan-words write no longer addresses the plan it was given"
    )

    assert '@router.patch("/{plan_id}"' in _text(_ROUTE), (
        "`editPlanWords` is called from the client while the router no longer declares "
        'PATCH /plans/{plan_id}'
    )
    assert _presentation_sites("editWords"), (
        "no screen or view model reaches editWords, so the pair's plan card can print a place and a "
        "note it has no way to write — the gap this stage was opened to close"
    )
    for name in ("editWords",):
        assert _text(_REPOSITORIES).count(name) and _text(_REPO_IMPL).count(name), (
            f"the domain contract or its implementation lost `{name}`"
        )


def test_the_card_offers_the_save_only_where_it_can_land_and_asks_for_it_by_name():
    """The editor is offered from the buckets the pair still reads as open, and it names the write.

    Hiding a button is not a permission check — the route holds its own refusal below — but a card that
    opened an editor on a closed plan would promise a save the server always refuses. What is checked
    here is the pair of halves: the gate exists and the screen uses it, so the two cannot drift apart
    with one file edited.
    """
    assert "fun canEditPlanWords(" in _text(_PLAN_BUCKETS), (
        "PlanBuckets.kt no longer answers whether the pair may write its own words"
    )
    screen = _text(_PLANS_SCREEN)
    assert "canEditPlanWords(plan)" in screen, (
        "the plan card stopped asking whether the words are still writable before opening the editor"
    )
    assert "onSaveWords" in screen and "vm.saveWords(" in screen, (
        "the editor's save is no longer wired to the view model that sends it"
    )
    assert "fun saveWords(" in _text(_PLANS_VIEW_MODEL), (
        "PlansViewModel.kt no longer holds the save the card calls"
    )


def test_every_refusal_the_card_can_meet_is_readable_in_russian():
    """The screen's copy, the server's literal and the raise site have to agree or say nothing.

    A message the server reworded without the client noticing falls through to a status family, which is
    how «Эта встреча уже закрыта» turns into «Это уже сделано» — a refusal read back as a success. So
    each demanded message is checked twice: still present in ``plan_service.py``, and still keyed in
    ``BackendErrorText.kt``.
    """
    service = _text(_PLAN_SERVICE)
    keys = _translated_keys()
    for message in _SAVE_REFUSALS:
        assert message in service, (
            f"`{message}` is no longer raised from plan_service.py; the pair's card can still be "
            "answered by a sentence this file has not read"
        )
        assert message.lower() in keys, (
            f"the plan card's save is refused with «{message}» and the client has no Russian wording "
            "for it, so the refusal is answered by a status family instead of by what the plan objected to"
        )
    for message in _UNREACHABLE_REFUSALS:
        assert message in service, (
            f"`{message}` was expected to stay a refusal this client cannot reach and is gone from "
            "plan_service.py; re-read whether the erase flags still do their job"
        )
