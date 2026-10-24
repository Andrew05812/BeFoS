"""A person's own word about a plan reaches the door that reads it, from the phone.

`PUT /plans/{plan_id}/note` and `GET /plans/{plan_id}`'s `my_note` have been in the API since stage 95:
the field lives on the member row, is read back only to its author, and never enters the pair's shared
card or their journal — the three facts `docs/DATABASE.md` gives for storing it at all. The phone
carried neither half. `PlanDetailDto` named `plan` and `events` and let `my_note` fall on the floor,
`ApiService` had no verb for the note route, and no screen spoke of a private remark. A person who
wanted to leave themselves a line about a meeting — «взять билеты», «подъезд с торца» — had no door in
the product, while the product already held the shelf it would land on.

That is the same shape stage 99 found on the photograph row and stage 106 named in this file's
predecessor: a method declared in the data layer and reachable from no screen is not a feature. So the
checks below pair the two languages rather than describe either one, field by field and call by call:

`PlanPersonalNoteIn` (``schemas.py``) against `PlanNoteRequest` (``Dtos.kt``) — the wire names.

`savePlanNote` (``ApiService.kt``) against the router's own decorator, and a caller under
``presentation/`` — the reach check this genre keeps failing without.

`my_note` in the detail answer against `myNote` in the client's DTO and against the domain contract,
so the word that was written can be read back without a second request.

The two ceilings on the length of the remark: the schema's `max_length` and the client's own limit are
read here as numbers and compared, because a phone that sends 900 characters meets a refusal it never
warned the person about.

The privacy rule is checked where it is decided — on the server's own read for the *other* half —
rather than by trusting the field's name.
"""
from __future__ import annotations

import pathlib
import re

from httpx import AsyncClient

from .conftest import auth_headers
from .test_a_pair_can_agree_on_when_to_meet import _page, _pair, _ready, _send
from .test_a_pairs_plan_is_one_thing_that_every_screen_moves import _detail, _my_plans

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_CLIENT_MAIN = _ROOT / "android" / "app" / "src" / "main"
_PRESENTATION = _CLIENT_MAIN / "java" / "app" / "befos" / "presentation"
_DTOS = _CLIENT_MAIN / "java" / "app" / "befos" / "data" / "model" / "Dtos.kt"
_API_SERVICE = _CLIENT_MAIN / "java" / "app" / "befos" / "data" / "remote" / "ApiService.kt"
_REPOSITORIES = _CLIENT_MAIN / "java" / "app" / "befos" / "domain" / "repository" / "Repositories.kt"
_REPO_IMPL = _CLIENT_MAIN / "java" / "app" / "befos" / "data" / "repository" / "PlanRepositoryImpl.kt"
_ERROR_TEXT = _CLIENT_MAIN / "java" / "app" / "befos" / "core" / "network" / "BackendErrorText.kt"
_PLAN_NOTE = _PRESENTATION / "plans" / "PlanNote.kt"
_PLAN_HISTORY_SCREEN = _PRESENTATION / "plans" / "PlanHistoryScreen.kt"
_PLAN_HISTORY_MODEL = _PRESENTATION / "plans" / "PlanHistoryViewModel.kt"
_SCHEMA = _ROOT / "backend" / "app" / "schemas" / "schemas.py"
_ROUTE = _ROOT / "backend" / "app" / "api" / "v1" / "plans.py"

_KOTLIN_PROPERTY = re.compile(r"^\s*(?:@SerialName\(\"([^\"]+)\"\)\s*)?val (\w+)\s*:")
_PY_FIELD = re.compile(r"^\s{4}(\w+): [^=]+", re.MULTILINE)


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _class_body(path: pathlib.Path, declaration: str) -> str:
    lines = _text(path).splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(declaration)]
    assert starts, f"{path.name} no longer declares `{declaration}` at top level"
    body: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if re.match(r"^(class |def |async def |@|private |public |data class |interface )", line):
            break
        body.append(line)
    return "\n".join(body)


def _kotlin_wire_names(declaration: str) -> set[str]:
    out: set[str] = set()
    for line in _class_body(_DTOS, declaration).splitlines():
        header = _KOTLIN_PROPERTY.match(line)
        if header:
            out.add(header.group(1) or header.group(2))
    return out


def _python_fields(declaration: str) -> set[str]:
    return {name for name in _PY_FIELD.findall(_class_body(_SCHEMA, declaration))}


def _presentation_sites(name: str) -> list[str]:
    sites: list[str] = []
    for file in sorted(_PRESENTATION.rglob("*.kt")):
        for number, line in enumerate(_text(file).splitlines(), start=1):
            if name in line:
                sites.append(f"{file.relative_to(_ROOT).as_posix()}:{number}")
    return sites


def _schema_note_limit() -> int:
    body = _class_body(_SCHEMA, "class PlanPersonalNoteIn(BaseModel):")
    found = re.search(r"max_length=(\d+)", body)
    assert found, "`PlanPersonalNoteIn` no longer states its own ceiling, so there is nothing to pair"
    return int(found.group(1))


def _client_note_limit() -> int:
    body = _text(_PLAN_NOTE)
    found = re.search(r"PLAN_NOTE_LIMIT\s*=\s*(\d+)", body)
    assert found, "PlanNote.kt no longer names the ceiling the person is warned by"
    return int(found.group(1))


def test_the_own_word_leaves_on_the_wire_the_route_reads_it_from():
    client_names = _kotlin_wire_names("data class PlanNoteRequest(")
    server_names = _python_fields("class PlanPersonalNoteIn(BaseModel):")
    assert client_names, "PlanNoteRequest holds no properties, so the write sends an empty body"
    assert client_names == server_names, (
        f"the phone sends {sorted(client_names)} and the route reads {sorted(server_names)}; a field "
        "the schema does not name is dropped in silence, and the person sees their word saved and gone"
    )


def test_the_door_is_a_put_to_the_plans_own_note_address():
    api = _text(_API_SERVICE)
    assert "fun savePlanNote(" in api, "ApiService.kt lost the private-note write altogether"
    body = api.split("fun savePlanNote(", 1)[1].split("suspend fun ", 1)[0]
    assert "HttpMethod.Put" in body, (
        "the note no longer arrives as a PUT; the route answers no other verb, and the word would be "
        "written to an address that does not take it"
    )
    assert 'endpoint("plans/$planId/note")' in body, "the note no longer addresses its own plan"
    assert '@router.put("/{plan_id}/note"' in _text(_ROUTE), (
        "the client calls PUT /plans/{plan_id}/note while the router no longer declares it"
    )


def test_the_own_word_is_reachable_from_a_screen():
    """A method that lives only in the data layer is the defect this file exists for."""
    assert _presentation_sites("saveNote"), (
        "no screen or view model reaches saveNote, so the plan holds a private remark nobody can write"
    )
    assert _presentation_sites("myNote"), (
        "the word that was written is read back by no page: the phone would write a note it can never "
        "show its author again"
    )
    for name in ("saveNote", "history"):
        assert _text(_REPOSITORIES).count(name) and _text(_REPO_IMPL).count(name), (
            f"the domain contract or its implementation lost `{name}`"
        )


def test_the_detail_answer_carries_the_ones_own_word_into_the_domain():
    """One read already asks for the plan and its journal; the remark has to ride with it.

    `my_note` travels inside the same answer, so opening the page costs no second request and cannot
    show a chronology while the person's own word sits somewhere else.
    """
    assert "my_note" in _kotlin_wire_names("data class PlanDetailDto("), (
        "PlanDetailDto dropped `my_note` again: the page would write the word and never read it back"
    )
    assert re.search(r'@SerialName\("my_note"\)\s+val myNote', _text(_DTOS)), (
        "the client's own word is no longer read under the name the server writes it"
    )
    impl = _text(_REPO_IMPL)
    assert "myNote" in impl, "the repository throws the answer's private word away"


def test_the_ceiling_the_person_is_warned_by_is_the_one_the_server_holds():
    server = _schema_note_limit()
    client = _client_note_limit()
    assert server == client, (
        f"the route refuses at {server} characters and the phone warns at {client}: the person either "
        "types a word the server will not keep or is stopped short of one it would"
    )


def test_the_refusal_this_door_answers_is_readable_in_russian():
    keys = {
        line.split(" to ", 1)[0].strip().strip('"').lower()
        for line in _text(_ERROR_TEXT).splitlines()
        if " to " in line and line.strip().startswith('"')
    }
    for refusal in ("Plan not found.",):
        assert refusal.lower() in keys, (
            f"`{refusal}` is answered by this door and the phone would show its English text"
        )


def test_the_page_names_the_word_as_private_and_says_how_long_it_may_be():
    """Privacy is a sentence the page tells its reader, not only a comment in the schema.

    The server decides who may see the field; the page has to say it, or a person reads the line they
    typed as another note the pair shares and weighs their words differently. The ceiling is named for
    the same reason: a field that stops accepting text without saying so reads as a broken keyboard.

    No gate on the plan's status is asked for here, and none exists: `PlanService.set_personal_note`
    refuses nothing but an absent member row, because a person's own remark about a meeting that was
    called off or already happened is still theirs to keep and still theirs to take back.
    """
    page = _text(_PLAN_HISTORY_SCREEN) + _text(_PLAN_NOTE) + _text(_PLAN_HISTORY_MODEL)
    assert "партнёр" in page.lower(), (
        "the private remark no longer says on its face whose eyes it is kept from"
    )
    assert "PLAN_NOTE_LIMIT" in page, "the page no longer names the ceiling it stops the person at"
    assert "fun saveNote(" in _text(_PLAN_HISTORY_MODEL), (
        "PlanHistoryViewModel.kt no longer holds the write the page calls"
    )
    assert "vm.saveNote(" in _text(_PLAN_HISTORY_SCREEN) or "vm::saveNote" in _text(
        _PLAN_HISTORY_SCREEN
    ), (
        "the editor's save is no longer wired to the view model that sends it"
    )


# ---------- what the shape the phone builds actually does to the pair's record ----------
#
# The static halves above say the two languages name the same field; these two say the field arrives
# with the meaning the phone means. `explicitNulls = false` in the client's serializer is what makes an
# emptied remark travel as an *absent* field, and a route that read an absent field as «не трогать»
# would leave the person rubbing the field clean and reading their old word back on the next visit.


async def _plan_of_a_pair(client: AsyncClient, a: dict, b: dict) -> str:
    """A pair that has taken one idea up, and the name the plan screen gives that arrangement."""
    match_id = await _pair(client, a, b)
    cards = await _page(client, a["token"], match_id, force=True)
    idea = cards[0]["activity"]["id"]
    assert await _send(client, a["token"], match_id, idea) == 204
    plans = await _my_plans(client, a["token"])
    assert len(plans) == 1, plans
    return plans[0]["id"]


async def test_the_empty_body_the_phone_sends_for_an_erasure_erases_the_word(
    client: AsyncClient,
) -> None:
    a = await _ready(client, "s124_note_a@befos.app", "Оля")
    b = await _ready(client, "s124_note_b@befos.app", "Рома")
    plan_id = await _plan_of_a_pair(client, a, b)

    written = await client.put(
        f"/api/v1/plans/{plan_id}/note",
        json={"note": "взять билеты"},
        headers=auth_headers(a["token"]),
    )
    assert written.status_code == 204, written.text
    assert (await _detail(client, a["token"], plan_id))["my_note"] == "взять билеты"

    erased = await client.put(
        f"/api/v1/plans/{plan_id}/note", json={}, headers=auth_headers(a["token"])
    )
    assert erased.status_code == 204, erased.text
    assert (await _detail(client, a["token"], plan_id))["my_note"] is None
    # The other half's read answers their own word, which nobody wrote: erasing one person's remark
    # cannot reach the other person's row, and cannot reach the note the pair shares either.
    partner = await _detail(client, b["token"], plan_id)
    assert partner["my_note"] is None
    assert partner["plan"]["note"] is None


async def test_a_word_the_phone_would_not_send_is_still_refused_by_the_route(
    client: AsyncClient,
) -> None:
    """The client holds its own ceiling; the route holds the same one, and both answers are checked.

    A screen that stopped the person at 500 characters is a courtesy, not a permission. The refusal
    staying in the schema is what keeps a second client — or a hand-built request — from writing a
    remark this page cannot show whole.
    """
    a = await _ready(client, "s124_long_a@befos.app", "Соня")
    b = await _ready(client, "s124_long_b@befos.app", "Тимур")
    plan_id = await _plan_of_a_pair(client, a, b)

    refused = await client.put(
        f"/api/v1/plans/{plan_id}/note",
        json={"note": "а" * (_client_note_limit() + 1)},
        headers=auth_headers(a["token"]),
    )
    assert refused.status_code == 422, refused.text

    kept = await _my_plans(client, a["token"])
    assert kept[0]["id"] == plan_id, "a refused note moved the arrangement it was written on"
