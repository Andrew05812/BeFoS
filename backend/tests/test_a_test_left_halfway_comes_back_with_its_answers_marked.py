"""A test left halfway reopened as question one with nothing marked, so it was not a left test.

Read off the tree this stage starts from (`69abc74`): ``GET /api/v1/tests`` sent the catalogue and
two counts, ``TestViewModel.load()`` set ``index = 0``, and ``TestScreen`` drew every option card of
the current question the same way — no card carried a mark. The consequence is what the person in the
middle of a test actually meets: leave the app after eight of twenty-one questions, come back, and the
screen offers question one again with no answer marked anywhere. To reach question nine they have to
re-tap the eight they already answered, and the re-tap overwrites their own earlier choice with
whatever they pick now. Going «Назад» from an unmarked question does not show what they had chosen, so
the one question the screen is built to answer — what did I say here — has no answer on screen.

The catalogue route can already tell: it counts the person's stored answers, and those rows name the
option each answer stands on. The checks below pin that the same read marks the cards too, that its
count agrees with the progress route a person sees on their profile, that the categories of the
catalogue are named with their Russian labels and with how far each has come — a category nobody
answered stays listed at zero, because a missing row cannot be told from a finished one — that
re-tapping moves the mark instead of adding an answer, that one person's marks do not travel to
another person's catalogue, and that none of this is paid for with a read per question.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import event

from app.compatibility.traits import TRAIT_CATEGORIES_BY_KEY
from app.core.database import engine

from .conftest import auth_headers, register_and_auth

_EMAILS = ["s83_marked@befos.app", "s83_other@befos.app"]


async def _catalog(client: AsyncClient, token: str) -> dict:
    resp = await client.get("/api/v1/tests", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _answer(client: AsyncClient, token: str, pairs: list[tuple[int, int]]) -> None:
    resp = await client.post(
        "/api/v1/tests/answers",
        json={"answers": [{"question_id": q, "option_id": o} for q, o in pairs]},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text


async def _statements(coro) -> tuple[object, list[str]]:
    """The SQL one request actually issued, so a new read can be told from a new round trip."""
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


async def _person(client: AsyncClient, email: str) -> dict:
    return await register_and_auth(client, email)


async def test_a_stored_answer_marks_the_card_it_belongs_to(client: AsyncClient) -> None:
    """Each of the first three questions comes back carrying the option its answer stands on."""
    creds = await _person(client, _EMAILS[0])
    catalog = await _catalog(client, creds["token"])
    questions = catalog["questions"]
    chosen = [(q["id"], q["options"][i % len(q["options"])]["id"]) for i, q in enumerate(questions[:3])]
    await _answer(client, creds["token"], chosen)

    marked = await _catalog(client, creds["token"])
    by_id = {q["id"]: q for q in marked["questions"]}
    for question_id, option_id in chosen:
        assert by_id[question_id]["selected_option_id"] == option_id, (
            f"question {question_id} was answered with option {option_id} and the catalogue "
            f"marks it {by_id[question_id]['selected_option_id']}"
        )
    for question in questions[3:]:
        assert by_id[question["id"]]["selected_option_id"] is None, (
            f"question {question['id']} was never answered and the catalogue marks it anyway"
        )
    # A mark has to name an option of its own question: an id from another card would highlight
    # nothing on this one and the person would read their answer as missing.
    for question in marked["questions"]:
        mark = question["selected_option_id"]
        if mark is not None:
            options = {o["id"] for o in question["options"]}
            assert mark in options, f"question {question['id']} is marked with a foreign option {mark}"


async def test_the_catalogue_count_agrees_with_the_progress_a_profile_shows(client: AsyncClient) -> None:
    """The two routes that answer «how much have I answered» say the same number."""
    creds = await _person(client, _EMAILS[0])
    before = await _catalog(client, creds["token"])
    resp = await client.get("/api/v1/tests/progress", headers=auth_headers(creds["token"]))
    assert resp.status_code == 200, resp.text
    assert before["answered"] == resp.json()["answered"], (
        f"an untouched test reads {before['answered']} in the catalogue and "
        f"{resp.json()['answered']} in progress"
    )

    questions = before["questions"]
    await _answer(client, creds["token"], [(q["id"], q["options"][0]["id"]) for q in questions[:4]])

    after = await _catalog(client, creds["token"])
    resp = await client.get("/api/v1/tests/progress", headers=auth_headers(creds["token"]))
    assert after["answered"] == resp.json()["answered"] == 4, (
        f"four answers read {after['answered']} in the catalogue and "
        f"{resp.json()['answered']} in progress"
    )


async def test_a_category_nobody_answered_is_still_named(client: AsyncClient) -> None:
    """The section list is the shape of the test, not a list of what has been filled in."""
    creds = await _person(client, _EMAILS[0])
    catalog = await _catalog(client, creds["token"])
    questions = catalog["questions"]
    first_category = questions[0]["category"]
    await _answer(client, creds["token"], [(q["id"], q["options"][0]["id"]) for q in questions
                                           if q["category"] == first_category])

    named = await _catalog(client, creds["token"])
    categories = {c["key"]: c for c in named["categories"]}
    present = {q["category"] for q in named["questions"]}
    assert set(categories) == present, (
        f"the catalogue asks about {sorted(present)} and answers about {sorted(categories)}"
    )
    for key, entry in categories.items():
        total = sum(1 for q in named["questions"] if q["category"] == key)
        answered = sum(1 for q in named["questions"]
                       if q["category"] == key and q["selected_option_id"] is not None)
        assert entry["total"] == total, f"{key} claims {entry['total']} of {total} questions"
        assert entry["answered"] == answered, (
            f"{key} claims {entry['answered']} answered while {answered} cards are marked"
        )
        assert entry["label"], f"{key} travels with an empty label"
        declared = TRAIT_CATEGORIES_BY_KEY.get(key)
        if declared is not None:
            assert entry["label"] == declared.label, (
                f"{key} is named {entry['label']!r} on the wire and {declared.label!r} in the engine"
            )
    untouched = [c for c in named["categories"] if c["answered"] == 0]
    assert untouched, "every category of the catalogue answered itself without anyone tapping"
    for entry in untouched:
        assert entry["total"] > 0, f"{entry['key']} is listed as empty of questions too"


async def test_re_tapping_a_question_moves_its_mark_instead_of_adding_an_answer(client: AsyncClient) -> None:
    """Changing one answer changes that card, and nothing else about the count."""
    creds = await _person(client, _EMAILS[0])
    questions = (await _catalog(client, creds["token"]))["questions"]
    await _answer(client, creds["token"], [(q["id"], q["options"][0]["id"]) for q in questions[:2]])

    stored = await _catalog(client, creds["token"])
    target = stored["questions"][0]
    neighbour = stored["questions"][1]
    first_choice = target["selected_option_id"]
    assert first_choice is not None, "the first answer did not reach its card"
    other = next(o["id"] for o in target["options"] if o["id"] != first_choice)
    await _answer(client, creds["token"], [(target["id"], other)])

    after = await _catalog(client, creds["token"])
    by_id = {q["id"]: q for q in after["questions"]}
    assert by_id[target["id"]]["selected_option_id"] == other, (
        f"the re-tap is not on the card: it still marks "
        f"{by_id[target['id']]['selected_option_id']}"
    )
    assert by_id[neighbour["id"]]["selected_option_id"] == neighbour["selected_option_id"], (
        "answering one question moved the mark of another"
    )
    assert after["answered"] == 2, f"the re-tap added an answer instead of replacing one: {after['answered']}"


async def test_one_persons_marks_do_not_travel_to_another_persons_catalogue(client: AsyncClient) -> None:
    """The stored choice is the owner's own answer, not a fact about the catalogue."""
    owner = await _person(client, _EMAILS[0])
    questions = (await _catalog(client, owner["token"]))["questions"]
    await _answer(client, owner["token"], [(q["id"], q["options"][0]["id"]) for q in questions[:3]])

    stranger = await _person(client, _EMAILS[1])
    theirs = await _catalog(client, stranger["token"])
    assert [q["selected_option_id"] for q in theirs["questions"]] == [None] * len(theirs["questions"]), (
        "a person who has not answered a single question received someone else's marks"
    )
    assert theirs["answered"] == 0, f"a fresh account reads {theirs['answered']} answers"
    assert theirs["total"] == len(questions), (
        "the two people were sent catalogues of different size, so their marks cannot be compared"
    )


async def test_the_marks_cost_no_read_per_question(client: AsyncClient) -> None:
    """Marking the catalogue reuses the answer set it already counted — one read, not one per card."""
    creds = await _person(client, _EMAILS[0])
    empty, bare = await _statements(_catalog(client, creds["token"]))
    questions = empty["questions"]
    await _answer(client, creds["token"], [(q["id"], q["options"][0]["id"]) for q in questions[:5]])

    marked, with_answers = await _statements(_catalog(client, creds["token"]))
    assert any("test_answers" in statement for statement in with_answers), (
        "the catalogue stopped reading the answers it is supposed to mark"
    )
    answer_reads = [s for s in with_answers if "test_answers" in s]
    assert len(answer_reads) == 1, (
        f"the answers are read {len(answer_reads)} times where one read marks every card: "
        f"{answer_reads}"
    )
    assert len(with_answers) == len(bare), (
        f"five stored answers changed the number of statements from {len(bare)} to "
        f"{len(with_answers)} — the marking grows with the answers"
    )
