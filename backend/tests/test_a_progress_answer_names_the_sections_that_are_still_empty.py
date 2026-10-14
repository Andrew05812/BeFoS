"""A band of the compatibility screen could say «нет данных» and stop there, leaving the person
to guess which part of the questionnaire would have filled it — and the only route that knows the
sections also had to carry every question text and every option to say so.

``GET /api/v1/tests/progress`` answered with four numbers about the whole test: how many answers
exist, how many questions there are, the percent, whether it is finished. A screen sitting on one
empty band needs none of that and needs something the route did not have: which section is empty,
what it is called in Russian, and how much of it is left. Asking the catalogue route for it works
and costs twenty-one question texts plus their options, which is why the profile and the
compatibility screen had no cheap way to name the gap.

The counts below pin that the progress route names every section the catalogue actually asks
about, that its list is row-for-row the list ``GET /api/v1/tests`` prints for the same person, so
the two screens cannot show two different shapes of one test, that a section nobody answered keeps
its row at zero instead of vanishing, that the body a submission answers with carries the same
sections as a later GET, and that naming them did not add a read: the route pays one question read
and one answer read, the same two ``COUNT``s it used to pay.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import event

from app.compatibility.traits import TRAIT_CATEGORIES_BY_KEY
from app.core.database import engine

from .conftest import auth_headers, register_and_auth

_EMAILS = ["s84_sections@befos.app", "s84_second@befos.app"]


async def _catalog(client: AsyncClient, token: str) -> dict:
    resp = await client.get("/api/v1/tests", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _progress(client: AsyncClient, token: str) -> dict:
    resp = await client.get("/api/v1/tests/progress", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _answer(client: AsyncClient, token: str, pairs: list[tuple[int, int]]) -> dict:
    resp = await client.post(
        "/api/v1/tests/answers",
        json={"answers": [{"question_id": q, "option_id": o} for q, o in pairs]},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _statements(coro):
    """The SQL one request actually issued, so a new number can be told from a new round trip."""
    seen: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(" ".join(statement.lower().split()))

    listener = record
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        result = await coro
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    return result, seen


async def test_an_untouched_progress_still_names_every_section(client: AsyncClient) -> None:
    """A person who has answered nothing is told which sections that leaves empty."""
    creds = await register_and_auth(client, _EMAILS[0])
    questions = (await _catalog(client, creds["token"]))["questions"]
    progress = await _progress(client, creds["token"])

    sections = progress["categories"]
    assert sections, "the progress answer carries no sections at all"
    assert [s["key"] for s in sections] == list(dict.fromkeys(q["category"] for q in questions)), (
        f"progress names {sections}, the catalogue asks {sorted({q['category'] for q in questions})}"
    )
    for entry in sections:
        assert entry["answered"] == 0, f"{entry['key']} counts {entry['answered']} answers nobody tapped"
        assert entry["total"] > 0, f"{entry['key']} is listed with no questions of its own"
        assert entry["label"], f"{entry['key']} travels with an empty label"
        declared = TRAIT_CATEGORIES_BY_KEY.get(entry["key"])
        if declared is not None:
            assert entry["label"] == declared.label, (
                f"{entry['key']} is named {entry['label']!r} on the wire and "
                f"{declared.label!r} in the engine"
            )
    assert progress["answered"] == 0 and progress["completed"] is False


async def test_the_two_routes_that_count_sections_count_them_the_same_way(client: AsyncClient) -> None:
    """The screen reading the catalogue and the screen reading progress cannot show two shapes."""
    creds = await register_and_auth(client, _EMAILS[0])
    questions = (await _catalog(client, creds["token"]))["questions"]
    first_category = questions[0]["category"]
    await _answer(client, creds["token"],
                  [(q["id"], q["options"][0]["id"]) for q in questions if q["category"] == first_category][:3])

    catalogue = await _catalog(client, creds["token"])
    progress = await _progress(client, creds["token"])
    assert progress["categories"] == catalogue["categories"], (
        f"the catalogue prints {catalogue['categories']} and progress prints {progress['categories']} "
        "for the same person at the same moment"
    )
    by_key = {s["key"]: s for s in progress["categories"]}
    entry = by_key[first_category]
    assert 0 < entry["answered"] < entry["total"], (
        f"a part-answered section reads {entry['answered']} of {entry['total']} — the list cannot "
        "tell a gap from a finish"
    )
    answered_cards = sum(1 for q in catalogue["questions"] if q["selected_option_id"] is not None)
    assert sum(s["answered"] for s in progress["categories"]) == answered_cards, (
        "the sections sum to a different number of answers than the marks on the cards"
    )


async def test_a_finished_section_stops_offering_itself_as_the_gap(client: AsyncClient) -> None:
    """Answering the rest of a section moves its count, and the row stays where it was."""
    creds = await register_and_auth(client, _EMAILS[0])
    questions = (await _catalog(client, creds["token"]))["questions"]
    first_category = questions[0]["category"]
    of_section = [q for q in questions if q["category"] == first_category]
    await _answer(client, creds["token"],
                  [(q["id"], q["options"][0]["id"]) for q in of_section])

    progress = await _progress(client, creds["token"])
    entry = next(s for s in progress["categories"] if s["key"] == first_category)
    assert entry["answered"] == entry["total"] == len(of_section), (
        f"a section answered to the last question reads {entry['answered']} of {entry['total']}"
    )
    empties = [s for s in progress["categories"] if s["answered"] < s["total"]]
    assert all(s["key"] != first_category for s in empties), (
        "a finished section is still offered as work left to do"
    )


async def test_the_response_to_a_tap_carries_the_same_sections_as_the_next_get(client: AsyncClient) -> None:
    """The client may repaint its section list from the submission it just made."""
    creds = await register_and_auth(client, _EMAILS[1])
    questions = (await _catalog(client, creds["token"]))["questions"]
    body = await _answer(client, creds["token"], [(q["id"], q["options"][0]["id"]) for q in questions[:2]])
    later = await _progress(client, creds["token"])

    assert body["categories"], "the submission stopped naming sections at all"
    assert body["categories"] == later["categories"], (
        f"a submission answers {body['categories']} and the next read answers {later['categories']}"
    )
    assert body["answered"] == 2 and body["remaining"] == body["total"] - 2


async def test_naming_the_sections_costs_the_two_reads_the_counts_already_paid(client: AsyncClient) -> None:
    """One read of the catalogue and one of the answers: the number grew, the round trips did not."""
    creds = await register_and_auth(client, _EMAILS[1])
    empty, bare = await _statements(_progress(client, creds["token"]))
    assert empty["categories"], "nothing to charge for — the route stopped naming sections"

    questions = (await _catalog(client, creds["token"]))["questions"]
    await _answer(client, creds["token"], [(q["id"], q["options"][0]["id"]) for q in questions[:5]])
    _, with_answers = await _statements(_progress(client, creds["token"]))

    question_reads = [s for s in with_answers if "from test_questions" in s]
    answer_reads = [s for s in with_answers if "from test_answers" in s]
    assert len(question_reads) == 1, (
        f"the sections are counted from {len(question_reads)} catalogue reads"
    )
    assert len(answer_reads) == 1, (
        f"the answers are counted {len(answer_reads)} times where one read fills every section"
    )
    assert len(with_answers) == len(bare), (
        f"five answers moved the progress route from {len(bare)} statements to {len(with_answers)}"
    )
