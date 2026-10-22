"""An account that can be erased in one tap has no way to take its own rows out first (stage 121).

`DELETE /api/v1/users/me` is the most final verb this app owns. `SafetyService.delete_account`
(`backend/app/services/safety_service.py:155-212`) anonymises the profile, deletes the photographs
and the files behind them, drops `test_answers`, `test_results`, `compatibility_profiles` and
`activity_preferences`, empties the deck, purges the whole social graph and revokes every session —
and the screen that asks for it says so out loud: «Аккаунт удалится сразу. Восстановить его не
получится» (`SettingsScreen.kt:126`). What no route in `backend/app/api/v1/` ever did was answer the
question that belongs one tap before that one: what were mine?

This file names the door that answers it — `GET /api/v1/users/me/export` — and holds it to three
promises. It answers for the owner alone. Its sections are the rows the doors the app already reads
are holding at the same moment, not a second calculation of them, so a person comparing the file
against their screens finds one story. And it carries the owner's rows without carrying the keys:
no password hash, no refresh-token material, no partner's private remark, and no silent change to
what the app holds — reading one's own data out must not mark the pair's backlog as read.

A ceiling belongs here too. A long-lived account holds thousands of chat lines, and a door that
answers "everything" with an unbounded read is a door that will be refused by the first proxy that
stands in front of it. So each section is capped, and a section that was capped says it was — the
same rule the list doors follow with `has_more`, told here in the one shape a file can carry.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models import User

from .conftest import (
    answer_all_questions,
    auth_headers,
    complete_onboarding,
    register_and_auth,
)

EXPORT = "/api/v1/users/me/export"
ME = "/api/v1/users/me"
INTERESTS = ["volunteering", "cinema", "board_games"]


def _whole_hour(hours_ahead: int) -> datetime:
    now = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)
    return now.replace(minute=0, second=0, microsecond=0)


async def _ready(client: AsyncClient, email: str, name: str) -> dict:
    """One person as the app knows them: an account, a finished questionnaire, a scored profile."""
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, interests=list(INTERESTS))
    await answer_all_questions(client, creds["token"])
    scored = await client.post("/api/v1/tests/complete", headers=auth_headers(creds["token"]))
    assert scored.status_code == 200, scored.text
    return creds


async def _pair(client: AsyncClient, a: dict, b: dict) -> str:
    await client.post(f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"]))
    second = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    assert second.status_code in (200, 201), second.text
    return second.json()["match_id"]


async def _arrange(client: AsyncClient, a: dict, b: dict, match_id: str) -> int:
    """Take one idea through the two taps a pair actually makes, and return its number."""
    page = await client.get(
        f"/api/v1/matches/{match_id}/recommendations?force=true", headers=auth_headers(a["token"])
    )
    assert page.status_code == 200, page.text
    idea = page.json()["recommendations"][0]["activity"]["id"]
    sent = await client.post(
        f"/api/v1/matches/{match_id}/recommendations/{idea}/select", headers=auth_headers(a["token"])
    )
    assert sent.status_code in (200, 204), sent.text
    when = _whole_hour(48)
    offered = await client.put(
        f"/api/v1/matches/{match_id}/recommendations/{idea}/time",
        json={"when": when.isoformat()},
        headers=auth_headers(a["token"]),
    )
    assert offered.status_code == 204, offered.text
    accepted = await client.post(
        f"/api/v1/matches/{match_id}/recommendations/{idea}/time/accept",
        json={"when": when.isoformat()},
        headers=auth_headers(b["token"]),
    )
    assert accepted.status_code == 204, accepted.text
    return idea


async def _send(client: AsyncClient, token: str, match_id: str, body: str) -> dict:
    resp = await client.post(
        f"/api/v1/matches/{match_id}/messages",
        json={"body": body},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _door(client: AsyncClient, token: str, path: str) -> dict:
    resp = await client.get(path, headers=auth_headers(token))
    assert resp.status_code == 200, f"{path}: {resp.text}"
    return resp.json()


async def _export(client: AsyncClient, token: str):
    return await client.get(EXPORT, headers=auth_headers(token))


async def _document(client: AsyncClient, token: str) -> dict:
    resp = await _export(client, token)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _life(client: AsyncClient, tag: str) -> dict:
    """One account with something of everything of its own, and a stranger who has nothing.

    The arrangement, the pair's lines, the block and the complaint are all written through the doors
    the app itself owns, so the document is compared against rows the product put there rather than
    against rows this file slipped in behind the API's back.
    """
    a = await _ready(client, f"s121_{tag}_a@befos.app", "Аня")
    b = await _ready(client, f"s121_{tag}_b@befos.app", "Боря")
    stranger = await _ready(client, f"s121_{tag}_c@befos.app", "Вера")
    match_id = await _pair(client, a, b)
    await _arrange(client, a, b, match_id)
    await _send(client, a["token"], match_id, "Привет, это Аня")
    await _send(client, b["token"], match_id, "И привет, это Боря")
    blocked = await client.post(
        f"/api/v1/users/{stranger['user_id']}/block", headers=auth_headers(a["token"])
    )
    assert blocked.status_code == 200, blocked.text
    complained = await client.post(
        f"/api/v1/users/{stranger['user_id']}/report",
        json={"reason": "harassment", "details": "Оскорбления в чате"},
        headers=auth_headers(b["token"]),
    )
    assert complained.status_code == 200, complained.text
    return {"a": a, "b": b, "stranger": stranger, "match_id": match_id}


async def test_the_door_opens_for_its_owner_and_stays_shut_for_everybody_else(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The answer belongs to the bearer of the token and to nobody else.

    Anonymous and another account's token are the two callers this door must refuse: the first has
    no rows to name, the second would be reading a stranger's life out of the database. The second
    refusal is the one worth a check, because the answer carries no addressee in its body — nothing
    in the request names an account, so the only account that can appear in the file is the token's.
    """
    life = await _life(client, "owner")
    own = await _export(client, life["a"]["token"])
    assert own.status_code == 200, own.text
    assert own.headers["content-type"].startswith("application/json"), own.headers["content-type"]

    anonymous = await client.get(EXPORT)
    assert anonymous.status_code == 401, f"a caller without a token was served: {anonymous.status_code}"

    mine = own.json()
    assert [p["match_id"] for p in mine["pairs"]] == [life["match_id"]], (
        f"the owner's own pair is missing from their file: {mine['pairs']}"
    )

    other = await _document(client, life["stranger"]["token"])
    assert other["pairs"] == [], f"a stranger was handed a pair it is not in: {other['pairs']}"
    assert life["match_id"] not in repr(other), "the stranger's file names a pair it holds no row of"
    assert life["a"]["user_id"] not in repr(other["chats"]), (
        "a stranger's document carries the lines somebody else wrote"
    )
    assert other["account"]["user_id"] != mine["account"]["user_id"]


async def test_the_profile_section_is_the_row_the_profile_door_answers(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The file must not be a second calculation of the same person.

    Every field the document names about the profile is compared with what `GET /users/me` answers
    one call later, so a document that quietly re-derived an age, a city or a percent would be
    caught by the door that already owns the answer.
    """
    life = await _life(client, "profile")
    document = await _document(client, life["a"]["token"])
    me = await _door(client, life["a"]["token"], ME)

    profile = document["profile"]
    for field in (
        "name", "age", "city", "gender", "about", "dating_goal", "age_min", "age_max",
        "gender_preference", "city_preference", "lifestyle", "is_hidden",
    ):
        assert profile[field] == me[field], f"`{field}` tells {profile[field]!r}, the door says {me[field]!r}"
    assert [i["slug"] for i in profile["interests"]] == [i["slug"] for i in me["interests"]], (
        "the interests in the file are not the set the profile door answers with"
    )
    assert profile["birth_date"] == "1996-05-10", (
        f"the stored date the person was asked for is not the one the file carries: {profile['birth_date']}"
    )
    assert document["account"]["email"] == life["a"]["email"], (
        "the file names somebody else's address as the reader's"
    )
    assert document["account"]["user_id"] == me["user_id"]
    assert document["account"]["is_moderator"] == me["is_moderator"]


async def test_the_questionnaire_section_holds_the_answers_and_what_the_engine_made_of_them(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The answers are the person's own words; the scores are the engine's read of them.

    Both come from rows this account wrote. `GET /tests/progress` owns the count of answered
    questions and `GET /tests/profile` owns the bands and the axes the result screen prints, so the
    file is checked against both. The scores are compared as the screen shows them — the percent is
    `round(score * 100)` of the stored float, and the file deliberately carries the float, because
    the rounding belongs to the screen and a document is meant to outlive it.
    """
    life = await _life(client, "test")
    document = await _document(client, life["a"]["token"])
    progress = await _door(client, life["a"]["token"], "/api/v1/tests/progress")
    built = await _door(client, life["a"]["token"], "/api/v1/tests/profile")

    answers = document["questionnaire"]["answers"]
    assert len(answers) == progress["answered"], (
        f"the file holds {len(answers)} answers while the app says this person answered "
        f"{progress['answered']}"
    )
    assert all(a["question"] and a["option"] for a in answers), (
        "an answer with neither the question nor the word chosen is not the person's answer"
    )

    stored = {c["category"]: c["score"] for c in document["questionnaire"]["categories"]}
    printed = {c["category"]: c["score"] for c in built["categories"]}
    assert set(stored) == set(printed), f"{sorted(stored)} against the screen's {sorted(printed)}"
    for category, value in stored.items():
        assert int(round(value * 100)) == printed[category], (
            f"`{category}` is stored as {value} in the file while the screen prints "
            f"{printed[category]} from the same row"
        )

    axes = document["questionnaire"]["compatibility"]["vector"]
    for axis in built["axes"]:
        assert axes[axis["category"]][axis["trait"]] == axis["value"], (
            f"the axis {axis['category']}/{axis['trait']} differs between file and screen"
        )
    assert document["questionnaire"]["compatibility"]["version"] >= 1, (
        "a vector with no version cannot say which model scored it"
    )


async def test_the_taps_and_the_deck_are_the_rows_the_discovery_doors_hold(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Both halves of a gesture, the passes, and the memory of who was ever offered.

    The three doors answer what a person may be shown again — stage 116 pushed a tap that had become
    a pair out of «кого я выбрал», because that relationship lives in the pair list now. A file is
    not a screen: the tap was made and stays made, so every card a door answers is in the file and
    the row the door filters out is in it too. The deck rows are the same argument in its purest
    form — no door ever hands them over, and they are the app's memory about this person.
    """
    life = await _life(client, "taps")
    # The deck memory is written by the only gesture that fills it: reading a page of candidates. A
    # like writes no queue row (stage 26), and after the pair formed and the stranger was blocked
    # there is nobody left to offer, so a fourth person is needed for the queue to hold anything.
    stranger_d = await _ready(client, "s121_taps_d@befos.app", "Гром")
    life["deck_peer"] = stranger_d["user_id"]
    feed = await _door(client, life["a"]["token"], "/api/v1/discover?limit=8")
    document = await _document(client, life["a"]["token"])

    given = await _door(client, life["a"]["token"], "/api/v1/discover/liked")
    received = await _door(client, life["a"]["token"], "/api/v1/discover/liked-me")
    passed = await _door(client, life["a"]["token"], "/api/v1/discover/passed")
    in_file_given = {t["user_id"] for t in document["taps"]["given"]}
    in_file_received = {t["user_id"] for t in document["taps"]["received"]}

    assert {t["user_id"] for t in given["likes"]} <= in_file_given, (
        "a tap the screen still lists is missing from the file"
    )
    assert {t["user_id"] for t in received["likes"]} <= in_file_received, (
        "a tap the inbox still lists is missing from the file"
    )
    assert {t["user_id"] for t in passed["passed"]} <= {
        t["user_id"] for t in document["taps"]["passed"]
    }, "a pass the passed-list names is missing from the file"

    assert life["b"]["user_id"] in in_file_given, (
        "the tap that became a pair vanished from the file the moment the pair formed: the screen "
        "may hide it, the record may not"
    )
    assert life["b"]["user_id"] in in_file_received, (
        "the other half's tap vanished with the pair it formed"
    )
    assert all(
        isinstance(t["compatibility"], (int, float)) or t["compatibility"] is None
        for t in document["taps"]["given"]
    ), "a tap without its stored number is not the row the person made"

    assert document["deck"], "the deck's memory — who was ever offered — is missing from the file"
    offered = {c["user_id"] for c in feed["items"]}
    assert offered, "the deck answered with no candidates, so this check would prove nothing"
    assert life["deck_peer"] in offered, (
        f"the fresh person the deck was asked to offer is not in its page: {sorted(offered)}"
    )
    assert offered <= {row["candidate_id"] for row in document["deck"]}, (
        "the page offered people the file claims nobody was ever queued"
    )
    assert all(row["candidate_id"] != life["a"]["user_id"] for row in document["deck"]), (
        "the queue names the reader as one of their own candidates"
    )
    assert all(row["rank"] is not None and row["status"] in ("ready", "seen") for row in document["deck"]), (
        f"a queue row without its rank or its state is not the memory the deck keeps: {document['deck'][:3]}"
    )


async def test_the_pair_and_its_lines_arrive_as_the_pair_reads_them(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The conversation is handed over exactly as the chat door answers it, and keeps what it hides.

    Both halves' lines are in it — a conversation belongs to two people, and the one reading the file
    can already read every line of it on screen — and the order is the order the history page returns
    (`chat_repo.list_messages` reverses its descending window before handing it back, so the page is
    ascending). Plan lines are in it too, because the pair's plan wrote them into this same
    conversation. A line taken back by its author (`DELETE …/messages/{id}`, stage 111) leaves the
    page and stays in the row — the file is the one that has to say it was written and then withdrawn,
    because that is what happened.
    """
    life = await _life(client, "chat")
    document = await _document(client, life["a"]["token"])
    matches = await _door(client, life["a"]["token"], "/api/v1/matches")
    history = await _door(client, life["a"]["token"], f"/api/v1/matches/{life['match_id']}/messages")

    assert [p["match_id"] for p in document["pairs"]] == [m["match_id"] for m in matches["matches"]], (
        "the file names a different list of pairs than the list the app opens"
    )
    chat = next(c for c in document["chats"] if c["match_id"] == life["match_id"])
    assert [line["body"] for line in chat["lines"]] == [m["body"] for m in history["messages"]], (
        "the lines in the file are not the lines the pair's history answers with, in its order"
    )
    assert {line["sender_id"] for line in chat["lines"]} == {
        life["a"]["user_id"], life["b"]["user_id"]
    }, "the file lost one half of the conversation"
    assert any(line["kind"] != "text" for line in chat["lines"]), (
        "the lines the pair's plan wrote are missing from the transcript in the file"
    )

    typed = next(line for line in chat["lines"] if line["is_own"] and line["kind"] == "text")
    withdrawn = await client.delete(
        f"/api/v1/matches/{life['match_id']}/messages/{typed['id']}",
        headers=auth_headers(life["a"]["token"]),
    )
    assert withdrawn.status_code == 204, withdrawn.text

    after = await _document(client, life["a"]["token"])
    page = await _door(client, life["a"]["token"], f"/api/v1/matches/{life['match_id']}/messages")
    kept = next(c for c in after["chats"] if c["match_id"] == life["match_id"])
    assert typed["id"] not in {m["id"] for m in page["messages"]}, (
        "the withdrawn line is still on the page, which is not what stage 111 settled"
    )
    holder = next((line for line in kept["lines"] if line["id"] == typed["id"]), None)
    assert holder is not None and holder["recalled"] is True, (
        f"the file dropped or mislabelled the withdrawn line: {holder}"
    )


async def test_the_arrangement_arrives_with_the_words_the_pair_wrote_about_it(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A plan in the file is the plan on the screen, with the history that made it.

    The list door owns the shared fields; the detail door owns this person's own remark and the
    lines the chat holds about the arrangement. The file carries all three, and it carries the
    reader's remark rather than the partner's, which is the one private field of the family.
    """
    life = await _life(client, "plan")
    document = await _document(client, life["a"]["token"])
    plans = await _door(client, life["a"]["token"], "/api/v1/plans")
    assert plans["plans"], "the pair arranged nothing, so this check proves nothing"

    assert [p["id"] for p in document["plans"]] == [p["id"] for p in plans["plans"]], (
        "the file's arrangements are not the ones the screen of «Наши планы» lists"
    )
    stored = document["plans"][0]
    detail = await _door(client, life["a"]["token"], f"/api/v1/plans/{stored['id']}")
    assert stored["status"] == detail["plan"]["status"], "the file tells another status than the card"
    assert stored["note"] == detail["plan"]["note"], "the shared remark differs between file and card"
    assert stored["my_note"] == detail["my_note"], "this person's own remark is not the one they wrote"
    assert [e["id"] for e in stored["journal"]] == [e["id"] for e in detail["events"]], (
        "the history the file carries is not the history the chat holds about this plan"
    )


async def test_the_partners_private_remark_is_not_in_the_file(
    client: AsyncClient, session: AsyncSession
) -> None:
    """One field of this family belongs to a single half of the pair, and it is not handed over.

    `my_note` of the detail read is private to its author (stage 107), so a document built for Аня
    must not carry what Боря wrote for himself. The text is written here and searched for in the
    serialized answer, because a field that arrived under another name would still be a leak.
    """
    life = await _life(client, "private")
    plans = await _door(client, life["a"]["token"], "/api/v1/plans")
    plan_id = plans["plans"][0]["id"]
    secret = f"только моё {uuid.uuid4()}"
    written = await client.patch(
        f"/api/v1/plans/{plan_id}", json={"my_note": secret}, headers=auth_headers(life["b"]["token"])
    )
    assert written.status_code == 200, written.text

    document = await _document(client, life["a"]["token"])
    assert secret not in repr(document), "the partner's private remark travelled in somebody else's file"
    assert document["plans"][0]["my_note"] != secret, "the file put the partner's words under the reader's name"


async def test_the_blocks_and_the_complaints_are_the_rows_the_owner_wrote(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The block list is the owner's own, and a complaint is theirs until it is decided.

    The decision is named — open, dismissed, actioned — and the hand that moved it is not: the
    moderator's identity and their comment belong to the queue, not to the person who filed.
    """
    life = await _life(client, "safety")
    document = await _document(client, life["a"]["token"])
    blocks = await _door(client, life["a"]["token"], "/api/v1/users/me/blocks")
    assert [b["user_id"] for b in document["blocks"]] == [
        b["user_id"] for b in blocks["blocked"]
    ], "the file's blocked list is not the list the screen of «Кого я заблокировал» answers with"

    filed = await _document(client, life["b"]["token"])
    complaints = filed["complaints"]
    assert len(complaints) == 1, f"one complaint was written, the file carries {len(complaints)}"
    assert complaints[0]["reason"] == "harassment", complaints[0]
    assert complaints[0]["details"] == "Оскорбления в чате", complaints[0]
    assert complaints[0]["status"] == "open", complaints[0]

    moderator = await register_and_auth(client, "s121_moderator@befos.app")
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(User).where(User.id == uuid.UUID(moderator["user_id"])).values(is_moderator=True)
        )
        await s.commit()
    review = await client.post(
        f"/api/v1/reports/{complaints[0]['id']}/review",
        json={"status": "resolved", "comment": f"решение {uuid.uuid4()}"},
        headers=auth_headers(moderator["token"]),
    )
    assert review.status_code == 200, review.text

    after = await _document(client, life["b"]["token"])
    row = after["complaints"][0]
    assert row["status"] == "resolved", "the decision the queue holds never reached the file"
    assert [r["to_status"] for r in row["history"]] == ["resolved"], row["history"]
    assert not any("moderator" in r for row in [row] for r in row["history"][0]), (
        f"the hand that decided travelled with the decision: {row['history'][0]}"
    )
    assert "решение" not in repr(row["history"]), "the moderator's comment is in the complainant's file"


async def test_the_file_hands_over_nothing_that_opens_a_door_or_a_wallet(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Rows about a person are not the keys that unlock them.

    The password hash, the refresh-token hash and the token strings themselves are all rows of this
    account's tables, and all three are refused: a file that a person forwards to somebody is a file
    whose contents must not be a way in.
    """
    life = await _life(client, "keys")
    signed_in = await client.post(
        "/api/v1/auth/login",
        json={"email": life["a"]["email"], "password": "Test12345"},
        headers={"User-Agent": "pixel-7/export-check"},
    )
    assert signed_in.status_code == 200, signed_in.text
    pair = signed_in.json()["tokens"]

    document = await _document(client, life["a"]["token"])
    text = repr(document)
    for forbidden in (pair["refresh_token"], pair["access_token"], "token_hash", "password_hash"):
        assert forbidden not in text, f"the file carries `{forbidden}`"
    async with AsyncSessionLocal() as s:
        row = await s.execute(select(User).where(User.id == uuid.UUID(life["a"]["user_id"])))
        stored_hash = row.scalar_one().password_hash
    assert stored_hash not in text, "the stored password hash travelled in the export"
    assert all("expires_at" in card for card in document["sessions"]), (
        "a session row without its expiry is not a row the owner can act on"
    )
    assert any(
        card["device"] == "pixel-7/export-check" for card in document["sessions"]
    ), f"the second sign-in never reached the file: {document['sessions']}"


async def test_an_account_that_has_never_arranged_anything_still_gets_a_document(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Emptiness is an answer, not a refusal.

    A person who registered and walked away holds a profile row and nothing else. The door answers
    with every section named and empty, because the screen beside it has to be able to say what the
    file holds without inventing a second story about an account with no rows.
    """
    fresh = await register_and_auth(client, "s121_fresh@befos.app")
    document = await _document(client, fresh["token"])

    for section in ("profile", "photos", "questionnaire", "taps", "deck", "pairs", "chats", "plans",
                    "blocks", "complaints", "sessions"):
        assert section in document, f"a fresh account's document does not name `{section}` at all"
    assert document["pairs"] == [] and document["chats"] == [] and document["plans"] == []
    assert document["taps"] == {"given": [], "received": [], "passed": []}
    assert document["questionnaire"]["answers"] == []
    assert document["counts"]["pairs"] == 0
    assert document["counts"]["sessions"] == len(document["sessions"])
    assert document["limits"]["truncated"] == [], "an empty document claims to have cut something"


async def test_a_section_that_hit_its_ceiling_says_so_instead_of_looking_complete(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cap that is not named is a silent loss, which is the one thing a file must not be.

    The ceiling is lowered to two rows for this call — the same knob the product will ship with,
    only within reach of a test — and the pair holds more lines than that. The section carries two
    lines, names itself as cut, and the door the app reads still answers all of them: the cap is a
    property of this document, not a deletion of anything.
    """
    life = await _life(client, "ceiling")
    await _send(client, life["a"]["token"], life["match_id"], "третья строка")
    await _send(client, life["a"]["token"], life["match_id"], "четвёртая строка")
    from app.services import export_service

    monkeypatch.setattr(export_service, "ROWS_PER_SECTION", 2)

    document = await _document(client, life["a"]["token"])
    history = await _door(client, life["a"]["token"], f"/api/v1/matches/{life['match_id']}/messages")
    chat = next(c for c in document["chats"] if c["match_id"] == life["match_id"])

    assert len(chat["lines"]) == 2, f"the ceiling was asked to hold two lines, it holds {len(chat['lines'])}"
    assert "chats" in document["limits"]["truncated"], (
        f"a capped section that does not name itself is a lie about completeness: {document['limits']}"
    )
    assert len(history["messages"]) >= 2, "the pair's own history lost rows to a read that capped another"
    assert document["counts"]["chats"] == len(history["messages"]), (
        "`counts` counted the capped rows rather than the rows that stand: "
        f"{document['counts']['chats']} against {len(history['messages'])}"
    )


async def test_reading_the_file_out_leaves_the_app_exactly_where_it_stood(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The door reads. That is the whole of what it is allowed to do.

    Two promises, both measured rather than asserted from intent: no statement inside the window is
    an `insert`, an `update` or a `delete`, and the unread counter the pair list carries is the same
    after the export as before it — the chat door marks the backlog read when the pair opens it
    (`chat.py:31-40`), and a file pulled in the background must not quietly empty somebody's badge.
    """
    life = await _life(client, "readonly")
    await _send(client, life["b"]["token"], life["match_id"], "строка, которую Аня ещё не читала")

    before = await _door(client, life["a"]["token"], "/api/v1/matches")
    unread_before = {m["match_id"]: m["unread"] for m in before["matches"]}

    statements: list[str] = []

    def before_cursor_execute(conn, cursor, stmt, parameters, context, executemany):
        statements.append(" ".join(stmt.lower().split()))

    engine = session.sync_session.get_bind()
    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        answered = await _export(client, life["a"]["token"])
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)

    assert answered.status_code == 200, answered.text
    writes = [s for s in statements if s.lstrip().startswith(("insert", "update", "delete"))]
    assert not writes, f"the export wrote inside its own window: {writes}"

    after = await _door(client, life["a"]["token"], "/api/v1/matches")
    unread_after = {m["match_id"]: m["unread"] for m in after["matches"]}
    assert unread_after == unread_before, (
        f"pulling the file consumed the pair's unread rows: {unread_before} against {unread_after}"
    )


async def test_the_erased_account_gets_no_document_and_no_second_chance_at_one(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The order this whole stage exists for: take the rows first, then close the account.

    Before the erasure the door answers; after it the same token answers nothing, because
    `delete_account` revokes every session — and a deleted account must not stay readable through a
    door nobody thought to close.
    """
    life = await _life(client, "erased")
    token = life["a"]["token"]
    assert (await _export(client, token)).status_code == 200

    erased = await client.delete("/api/v1/users/me", headers=auth_headers(token))
    assert erased.status_code == 200, erased.text

    refused = await _export(client, token)
    assert refused.status_code in (401, 403), (
        f"an erased account still opened its own file: {refused.status_code}"
    )


def test_the_door_is_mounted_once_and_names_the_family_it_belongs_to() -> None:
    """One route, on the family that already owns everything about this account.

    The double mount is the failure this catches: `users.py` and `safety.py` both serve `/users/me`,
    and a door mounted twice answers from whichever FastAPI reaches first while the other one rots.
    """
    from app.main import create_app

    paths = [
        (sorted(route.methods), route.path)
        for route in create_app().routes
        if getattr(route, "path", "").endswith("/users/me/export")
    ]
    assert len(paths) == 1, f"the export door is mounted {len(paths)} times: {paths}"
    methods, path = paths[0]
    assert methods == ["GET"], f"{path} answers {methods}: a file handed over must not be a write"
