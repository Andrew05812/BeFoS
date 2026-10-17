"""Real end-to-end journey against the running Docker backend (localhost:8000).

Exercises the full BeFoS value chain with two fresh users who mutually like each
other so a real match + chat + recommendations flow is produced. A third account is
created, given the moderator role the way the operator does it, and used to walk one
complaint from the tap that writes it to the decision that closes it. Every step
asserts on live backend data; nothing is mocked or hardcoded. All three accounts are
deleted at the end, so a run leaves no probe rows in the development database.
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import time
import uuid

import httpx
import websockets  # comes with uvicorn[standard], the same server that answers here

BASE = "http://localhost:8000/api/v1"
WS_BASE = "ws://localhost:8000"
results: list[tuple[bool, str]] = []

# The four words the map splits its sections on, and the two units a node's sentence can be written
# in. A scale value («0.90») in an explanation the canvas prints as a percent is the defect stage 75
# found on the live pair, so the journey reads the document with the same eyes the screen does.
_CONNECTIONS = {"harmony", "complementarity", "discussion", "unknown"}
_SCALE_VALUE = re.compile(r"\d+[.,]\d+")


def check(ok: bool, label: str, extra: str = "") -> None:
    results.append((ok, label))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {label}{(' :: ' + extra) if extra else ''}")
    if not ok:
        # keep going to surface all failures, but remember we failed
        pass


class Peer:
    """One end of the chat as the app sees it: a socket plus frames nobody asked for yet.

    Realtime delivers presence, typing and receipts in no order the test can predict, so
    a frame that is not the one being waited for is parked instead of dropped — dropping
    it would make the next check fail for the wrong reason.
    """

    def __init__(self, ws) -> None:
        self.ws = ws
        self.parked: list[dict] = []

    async def next(self, kind: str, timeout: float = 2.0, **wanted) -> dict | None:
        for index, frame in enumerate(self.parked):
            if frame.get("type") == kind and all(frame.get(k) == v for k, v in wanted.items()):
                return self.parked.pop(index)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                raw = await asyncio.wait_for(self.ws.recv(), remaining)
            except (asyncio.TimeoutError, TimeoutError):
                return None
            except websockets.exceptions.ConnectionClosed:
                # The room ending is an answer to the question "did this frame arrive";
                # it must fail the check, not the whole journey.
                return None
            try:
                frame = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(frame, dict):
                continue
            if frame.get("type") == kind and all(frame.get(k) == v for k, v in wanted.items()):
                return frame
            self.parked.append(frame)

    async def nothing(self, kind: str, seconds: float = 1.0, **wanted) -> bool:
        return await self.next(kind, seconds, **wanted) is None


async def _refusal(uri: str) -> str:
    """Why this socket did not open, or 'accepted' when it did."""
    try:
        async with websockets.connect(uri, open_timeout=5):
            return "accepted"
    except websockets.exceptions.InvalidStatus as exc:
        return f"handshake {exc.response.status_code}"
    except websockets.exceptions.ConnectionClosed as exc:
        return f"closed {getattr(exc.rcvd, 'code', 'unknown')}"


def socket_refused(uri: str) -> str:
    return asyncio.run(_refusal(uri))


def realtime(match_id: str, uid_a: str, uid_b: str, tok_a: str, tok_b: str, stranger_tok: str, c: httpx.Client) -> None:
    """Ask the live socket what the REST history already confirmed.

    REST proves the row exists. Only a socket proves that the second client is told about
    it without refetching, that a retried send does not appear twice, and that a token
    whose owner no longer belongs to the pair gets no room.
    """
    ha = {"Authorization": f"Bearer {tok_a}"}
    hb = {"Authorization": f"Bearer {tok_b}"}

    async def drive() -> None:
        uri_a = f"{WS_BASE}/ws/chat/{match_id}?token={tok_a}"
        uri_b = f"{WS_BASE}/ws/chat/{match_id}?token={tok_b}"
        async with websockets.connect(uri_a, open_timeout=5) as ws_a, websockets.connect(uri_b, open_timeout=5) as ws_b:
            a, b = Peer(ws_a), Peer(ws_b)

            seen = await b.next("presence", user_id=uid_a)
            check(seen is not None and seen.get("online") is True, "B is told A came online", str(seen))
            seen = await a.next("presence", user_id=uid_b)
            check(seen is not None and seen.get("online") is True, "A is told B came online", str(seen))

            reuse = "e2e-retry-1"
            body = "Привет по сокету."
            frame = {"type": "message", "body": body, "client_msg_id": reuse}
            await ws_a.send(json.dumps(frame))
            inbound = await b.next("message", body=body)
            check(inbound is not None, "a socket send reaches the peer without a reload", str(inbound))
            ack = await a.next("message", body=body)
            same_id = inbound is not None and ack is not None and ack.get("id") == inbound.get("id")
            check(same_id, "the sender is answered with the stored id", str(ack))

            await ws_a.send(json.dumps(frame))
            replayed = await a.next("message", id=(inbound or {}).get("id"))
            check(replayed is not None, "a retried send is answered under the same id", str(replayed))
            quiet = await b.nothing("message")
            check(quiet, "a retried send is not shown to the peer twice")

            await ws_a.send("this is not json")
            err = await a.next("error")
            check(err is not None, "a malformed frame is answered, not fatal", str(err))

            await ws_a.send(json.dumps({"type": "typing", "typing": True}))
            typing = await b.next("typing", user_id=uid_a, typing=True)
            check(typing is not None and await a.nothing("error", 0.6) is True,
                  "the socket survives it and relays typing", str(typing))

            rest = c.post(f"{BASE}/matches/{match_id}/messages", headers=hb,
                          json={"body": "Отправлено по REST."})
            delivered = await a.next("message", body="Отправлено по REST.")
            check(rest.status_code in (200, 201) and delivered is not None,
                  "a REST send is relayed into the open room", str(delivered))

            await ws_b.send(json.dumps({"type": "read"}))
            receipt = await a.next("read", user_id=uid_b)
            read_back = [m for m in c.get(f"{BASE}/matches/{match_id}/messages", headers=ha,
                                          params={"limit": 50}).json()["messages"] if m["is_own"]]
            check(receipt is not None and all(m["is_read"] for m in read_back),
                  "a socket read is both shown and stored", str(receipt))

        refused = await _refusal(f"{WS_BASE}/ws/chat/{match_id}?token={stranger_tok}")
        check(refused != "accepted", "a stranger holding a valid token gets no room", refused)
        refused = await _refusal(f"{WS_BASE}/ws/chat/{match_id}?token=not-a-token")
        check(refused != "accepted", "a token that does not verify gets no room", refused)

    try:
        asyncio.run(drive())
    except Exception as exc:  # a socket that will not open is a failure, not a traceback
        check(False, "both members hold a socket on the pair", f"{type(exc).__name__}: {exc}")


def agreed_hour_reaches_the_chat(match_id: str, tok_a: str, tok_b: str, activity_id: int,
                                 title: str, first: str, moved: str, c: httpx.Client) -> None:
    """Ask the live pair whether the hour they land on is said in their conversation.

    A card answers the tap and a stored row answers the page reload; only a second client proves the
    conversation itself carries the plan. So the half that names the hour and the half that agrees
    are driven over REST while the other screen sits open on a socket, and every step is read back
    from both histories: a proposal that speaks too early, an agreement that arrives twice, a promise
    that moved without the chat being told about it, and an old hour that keeps posing as current all
    fail here rather than on a phone.

    The last two checks ask the question the plan entity exists to answer: the line in the chat and
    the row in each half's list of plans have to be the same arrangement, named by the same id. Two
    screens that each kept their own copy of a pair's plan would pass every check above.
    """
    ha = {"Authorization": f"Bearer {tok_a}"}
    hb = {"Authorization": f"Bearer {tok_b}"}
    time_url = f"{BASE}/matches/{match_id}/recommendations/{activity_id}/time"
    accept_url = f"{time_url}/accept"

    def plan_lines(headers: dict) -> list[dict]:
        history = c.get(f"{BASE}/matches/{match_id}/messages", headers=headers).json()["messages"]
        return [m for m in history if m.get("kind") != "text"
                and (m.get("plan") or {}).get("activity_id") == activity_id]

    async def drive() -> None:
        uri_b = f"{WS_BASE}/ws/chat/{match_id}?token={tok_b}"
        async with websockets.connect(uri_b, open_timeout=5) as ws_b:
            b = Peer(ws_b)
            opened = plan_lines(ha)
            check([m["kind"] for m in opened] == ["plan_proposed"],
                  "A putting the idea to the pair is said in the conversation", str(opened)[:140])

            proposed = await asyncio.to_thread(c.put, time_url, headers=ha, json={"when": first})
            check(proposed.status_code == 204, "A names an hour for the card", str(proposed.status_code))
            lines = plan_lines(ha)
            check(await b.nothing("message", 1.0)
                  and [m["id"] for m in lines] == [m["id"] for m in opened],
                  "one half naming an hour says nothing in the conversation yet", str(lines)[:140])

            agreed = await asyncio.to_thread(c.post, accept_url, headers=hb, json={"when": first})
            check(agreed.status_code == 204, "B agrees to the hour", str(agreed.status_code))
            frame = await b.next("message", 3.0)
            check(frame is not None and frame.get("kind") == "plan_agreed"
                  and (frame.get("plan") or {}).get("is_latest") is True,
                  "an open chat hears the agreement without a reload", str(frame)[:140])

            lines_a, lines_b = plan_lines(ha), plan_lines(hb)
            check([m["kind"] for m in lines_a] == ["plan_proposed", "plan_agreed"]
                  and [m["kind"] for m in lines_b] == ["plan_proposed", "plan_agreed"]
                  and lines_a[-1]["id"] == lines_b[-1]["id"],
                  "both screens read the same one agreement line",
                  f"{[m['kind'] for m in lines_a]}")
            plan = lines_a[-1]["plan"]
            check(plan.get("activity_title") == title and "19:00" in str(plan.get("when"))
                  and "UTC" in lines_a[-1]["body"],
                  "the line names the idea, the hour and the clock it is named in", str(plan)[:140])

            retapped = await asyncio.to_thread(c.post, accept_url, headers=hb, json={"when": first})
            check(retapped.status_code == 204 and len(plan_lines(ha)) == 2,
                  "a second agreement on the same hour says nothing twice", str(len(plan_lines(ha))))

            moved_up = await asyncio.to_thread(c.put, time_url, headers=ha, json={"when": moved})
            check(moved_up.status_code == 204, "A moves the agreed hour", str(moved_up.status_code))
            ended = await b.next("message", 3.0)
            check(ended is not None and ended.get("kind") == "plan_voided",
                  "the chat is told the promise ended", str(ended)[:140])
            asked = await b.next("message", 3.0)
            check(asked is not None and asked.get("kind") == "plan_rescheduled"
                  and "21:00" in str((asked.get("plan") or {}).get("when")),
                  "the moved hour is said as a question the other half answers", str(asked)[:140])

            landing = await asyncio.to_thread(c.post, accept_url, headers=hb, json={"when": moved})
            check(landing.status_code == 204, "B agrees to the moved hour", str(landing.status_code))
            lines_a = plan_lines(ha)
            newest = [m for m in lines_a if (m.get("plan") or {}).get("is_latest")]
            check(len(newest) == 1 and newest[0]["kind"] == "plan_agreed"
                  and "21:00" in str(newest[0]["plan"]["when"])
                  and all(m["plan"]["is_latest"] is False for m in lines_a if m is not newest[0]),
                  "the hour they moved off stops posing as current", str(newest)[:140])

            # The chat, the card and the pair's list of plans are three screens over one arrangement,
            # so the line the chat carries has to name the plan the list answers with.
            listed = await asyncio.to_thread(
                c.get, f"{BASE}/matches/{match_id}/plans", headers=ha)
            plans = listed.json().get("plans", []) if listed.status_code == 200 else []
            check(listed.status_code == 200 and len(plans) == 1
                  and plans[0]["id"] == newest[0]["plan"]["plan_id"]
                  and plans[0]["status"] == "planned"
                  and "21:00" in str(plans[0]["starts_at"]),
                  "the arrangement the chat names is the arrangement the plan list carries",
                  str(plans)[:160])
            mine = await asyncio.to_thread(c.get, f"{BASE}/plans", headers=hb)
            check(mine.status_code == 200
                  and [p["id"] for p in mine.json().get("plans", [])] == [plans[0]["id"]],
                  "the other half's screen of plans reaches the same one plan",
                  str(mine.json())[:160])

    try:
        asyncio.run(drive())
    except Exception as exc:  # a socket that will not open is a failure, not a traceback
        check(False, "the pair's agreement is said in their conversation", f"{type(exc).__name__}: {exc}")


def _grant_moderator(user_id: str) -> str:
    """Run the operator's own promotion step, on the container this journey is already talking to.

    The product has no route that hands the role out — a public way to register a moderator would
    be the front door of the queue it is meant to guard — so the walk follows the documented step
    and sets the flag with SQL on one probe account that the run deletes again at the end. The text
    psql answers with is checked rather than trusted, because a statement that updated nobody would
    otherwise look like a moderator who simply had nothing to read.
    """
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", user_id):
        return "refused: not a user id"
    done = subprocess.run(
        ["docker", "exec", "befos_postgres", "psql", "-U", "befos", "-d", "befos", "-tA",
         "-c", f"UPDATE users SET is_moderator = true WHERE id = '{user_id}'"],
        capture_output=True, text=True, timeout=30,
    )
    return (done.stdout + done.stderr).strip()


def complaint_reaches_a_moderator(c, ha: dict, hb: dict, uid_a: str, uid_b: str,
                                  email_d: str, pw: str) -> dict:
    """Walk one complaint from the tap that writes it to the hand that is allowed to close it.

    REST says the row exists; only this walk says who may read it. The ordinary account that wrote
    the complaint is turned away from the queue before and after the decision, the moderator's card
    is read for what it must not carry, and every move leaves a history row behind it.
    """
    written = c.post(f"{BASE}/users/{uid_b}/report", headers=ha,
                     json={"reason": "harassment", "details": "E2E: one sentence that was not a question."})
    check(written.status_code == 200 and written.json() == {"reported": True, "reason": "harassment"},
          "a complaint is written", f"{written.status_code} {str(written.json())[:80]}")

    twice = c.post(f"{BASE}/users/{uid_b}/report", headers=ha, json={"reason": "harassment"})
    check(twice.status_code == 409 and "already reported" in twice.json()["error"]["message"],
          "the same tap twice writes no second complaint", str(twice.status_code))

    invented = c.post(f"{BASE}/users/{uid_b}/report", headers=ha, json={"reason": "villainy"})
    refused_reason = invented.json().get("error", {}).get("message", "")
    check(invented.status_code == 422 and "Invalid report reason" in refused_reason,
          "a reason the server does not know is refused by naming its list", refused_reason[:120])

    about_self = c.post(f"{BASE}/users/{uid_a}/report", headers=ha, json={"reason": "spam"})
    check(about_self.status_code == 422, "a complaint about yourself is not a complaint", str(about_self.status_code))

    queue_for_a = c.get(f"{BASE}/reports", headers=ha)
    check(queue_for_a.status_code == 403, "the person who complained is not shown the queue",
          str(queue_for_a.status_code))
    anon_queue = c.get(f"{BASE}/reports")
    check(anon_queue.status_code == 401, "the queue is not open to an anonymous reader", str(anon_queue.status_code))
    # A number that belongs to nobody is answered 403, not 404: the door is closed before the
    # number is looked at, so the moderation surface cannot be used to ask which complaints exist.
    invented_id = str(uuid.uuid4())
    review_for_a = c.post(f"{BASE}/reports/{invented_id}/review", headers=ha,
                          json={"status": "resolved", "comment": "E2E: an ordinary account deciding."})
    check(review_for_a.status_code == 403, "an ordinary account decides nothing, named number or not",
          str(review_for_a.status_code))

    rd = c.post(f"{BASE}/auth/register", json={"email": email_d, "password": pw, "password_confirm": pw})
    uid_d = rd.json()["user"]["id"]
    hd = {"Authorization": f"Bearer {rd.json()['tokens']['access_token']}"}
    granted = _grant_moderator(uid_d)
    check(granted == "UPDATE 1", "the operator's step makes one account a moderator, and only one", granted[:80])

    # The token above was minted before the flag was set and still opens the queue: the role is read
    # off the row per request, which is also how taking it away stops a stolen token at once.
    page = c.get(f"{BASE}/reports", params={"status": "open"}, headers=hd)
    cards = page.json().get("reports", []) if page.status_code == 200 else []
    card = next((r for r in cards
                 if r["reported"]["user_id"] == uid_b and r["reporter"]["user_id"] == uid_a), None)
    check(page.status_code == 200 and card is not None,
          "the queue a token from before the role reads names both halves of it", f"{len(cards)} open")
    if card is None:
        return {"uid_d": uid_d, "hd": hd, "report_id": None}

    shown = json.dumps(card, ensure_ascii=False)
    check(set(card["reported"]) == {"user_id", "name", "age", "city", "is_deleted", "is_hidden", "is_moderator"},
          "the card names the account, not the life behind it", str(sorted(card["reported"]))[:120])
    check(not re.search(r'"(email|about|birth_date|photo|phone)"', shown),
          "nothing on the card reaches past what a decision needs", shown[:120])

    rid = card["id"]
    rushed = c.post(f"{BASE}/reports/{rid}/review", headers=hd, json={"status": "resolved"})
    check(rushed.status_code == 422 and "needs a comment" in rushed.json()["error"]["message"],
          "a complaint cannot be closed without saying why", str(rushed.status_code))
    untouched = c.get(f"{BASE}/reports/{rid}", headers=hd).json()
    check(untouched.get("status") == "open" and untouched.get("reviews") == [],
          "a refused decision moved nothing and wrote no history", str([untouched.get("status"),
                                                                        len(untouched.get("reviews", []))]))

    moved = c.post(f"{BASE}/reports/{rid}/review", headers=hd,
                   json={"status": "reviewed", "comment": "E2E: read by the moderator."})
    check(moved.status_code == 200 and moved.json()["status"] == "reviewed",
          "open becomes reviewed", f"{moved.status_code} {str(moved.json())[:60]}")
    closed = c.post(f"{BASE}/reports/{rid}/review", headers=hd,
                    json={"status": "resolved", "comment": "E2E: the account was warned."})
    check(closed.status_code == 200 and closed.json()["status"] == "resolved",
          "reviewed becomes resolved", f"{closed.status_code} {str(closed.json())[:60]}")

    again = c.post(f"{BASE}/reports/{rid}/review", headers=hd,
                   json={"status": "resolved", "comment": "E2E: a second closing."})
    check(again.status_code == 409, "a closed complaint does not close twice", str(again.status_code))
    back = c.post(f"{BASE}/reports/{rid}/review", headers=hd,
                  json={"status": "open", "comment": "E2E: take the decision back."})
    check(back.status_code == 422, "a decision the history already records is not rewritten",
          str(back.json())[:100])

    detail = c.get(f"{BASE}/reports/{rid}", headers=hd).json()
    chain = [(r["from_status"], r["to_status"]) for r in detail["reviews"]]
    check(chain == [("open", "reviewed"), ("reviewed", "resolved")],
          "the history is the moves, in the order they happened", str(chain))
    check(all(r["moderator_id"] == uid_d and r["comment"] for r in detail["reviews"]),
          "every row of the history names the hand and says what it thought", str(len(detail["reviews"])))

    about_d = c.post(f"{BASE}/users/{uid_d}/report", headers=hb,
                     json={"reason": "other", "details": "E2E: a complaint about the moderator."})
    check(about_d.status_code == 200, "another account can complain about a moderator", str(about_d.status_code))
    d_cards = [r for r in c.get(f"{BASE}/reports", params={"status": "open"}, headers=hd).json().get("reports", [])
               if r["reported"]["user_id"] == uid_d]
    decided = c.post(f"{BASE}/reports/{d_cards[0]['id']}/review", headers=hd,
                     json={"status": "dismissed", "comment": "E2E: deciding about myself."}) if d_cards else None
    check(bool(d_cards) and decided.status_code == 403,
          "a moderator cannot close a complaint about their own account",
          str(decided.json())[:100] if decided else "no complaint about the moderator in the queue")

    after = c.get(f"{BASE}/reports", headers=ha)
    check(after.status_code == 403,
          "the person who complained is still not told what became of it", str(after.status_code))
    return {"uid_d": uid_d, "hd": hd, "report_id": rid}


def onboard_payload(name: str, gender: str, pref: list[str], interests: list[str]) -> dict:
    return {
        "name": name,
        "birth_date": "1995-04-12",
        "city": "Москва",
        "gender": gender,
        "about": f"E2E profile for {name}.",
        "dating_goal": "relationship",
        "interests": interests,
        "lifestyle": {"smoking": "never", "activity_level": "active"},
        "age_min": 22,
        "age_max": 45,
        "gender_preference": pref,
    }


def main() -> int:
    c = httpx.Client(timeout=30.0, trust_env=False)
    stamp = int(time.time())
    email_a = f"e2e.a.{stamp}@befosmail.com"
    email_b = f"e2e.b.{stamp}@befosmail.com"
    pw = "Str0ngPass!23"

    # 0. health
    h = c.get(f"{BASE}/health").json()
    check(h.get("status") == "ok", "health", str(h))
    hdb = c.get(f"{BASE}/health/db").json()
    check(hdb.get("database") == "connected", "health/db", str(hdb))

    # interests catalog (real slugs)
    interests = c.get(f"{BASE}/users/interests").json()["interests"]
    slugs = [i["slug"] for i in interests][:6]
    check(len(slugs) >= 3, "interests catalog", f"{len(interests)} interests")
    shared = slugs[:4]

    # 1. register A + B
    ra = c.post(f"{BASE}/auth/register", json={"email": email_a, "password": pw, "password_confirm": pw})
    check(ra.status_code in (200, 201) and "tokens" in ra.json(), "register A", str(ra.status_code))
    rb = c.post(f"{BASE}/auth/register", json={"email": email_b, "password": pw, "password_confirm": pw})
    check(rb.status_code in (200, 201) and "tokens" in rb.json(), "register B", str(rb.status_code))
    tok_a = ra.json()["tokens"]["access_token"]
    tok_b = rb.json()["tokens"]["access_token"]
    ref_a = ra.json()["tokens"]["refresh_token"]
    uid_a = ra.json()["user"]["id"]
    uid_b = rb.json()["user"]["id"]
    ha = {"Authorization": f"Bearer {tok_a}"}
    hb = {"Authorization": f"Bearer {tok_b}"}

    # duplicate register rejected
    dup = c.post(f"{BASE}/auth/register", json={"email": email_a, "password": pw, "password_confirm": pw})
    check(dup.status_code >= 400, "duplicate register rejected", str(dup.status_code))

    # 2. login A
    la = c.post(f"{BASE}/auth/login", json={"email": email_a, "password": pw})
    check(la.status_code == 200 and "tokens" in la.json(), "login A", str(la.status_code))
    bad = c.post(f"{BASE}/auth/login", json={"email": email_a, "password": "wrongpass1"})
    check(bad.status_code >= 400, "bad password rejected", str(bad.status_code))

    # 3. onboarding both. B names two interests A never picked, on purpose: a pair whose answers
    # overlap only partly is the ordinary case, and it is the only way this live path can show the
    # map's fourth word — an answer one person never gave is an absence, not a difference.
    oa = c.post(f"{BASE}/users/me/onboarding", headers=ha, json=onboard_payload("Анна", "female", ["male"], shared))
    check(oa.status_code == 200, "onboarding A", str(oa.status_code))
    ob = c.post(f"{BASE}/users/me/onboarding", headers=hb,
                json=onboard_payload("Борис", "male", ["female"], shared + slugs[4:6]))
    check(ob.status_code == 200, "onboarding B", str(ob.status_code))

    me = c.get(f"{BASE}/users/me", headers=ha).json()
    check(me.get("name") == "Анна" and me.get("age", 0) > 0, "profile me A", f"{me.get('name')}/{me.get('age')}")

    # 4. tests
    tests = c.get(f"{BASE}/tests", headers=ha).json()
    qs = tests["questions"]
    check(tests["total"] > 0 and len(qs) == tests["total"], "tests list", f"{tests['total']} questions")
    answers = [{"question_id": q["id"], "option_id": q["options"][0]["id"]} for q in qs if q["options"]]
    sa = c.post(f"{BASE}/tests/answers", headers=ha, json={"answers": answers})
    check(sa.status_code == 200, "submit answers A", str(sa.status_code))
    prog = c.get(f"{BASE}/tests/progress", headers=ha).json()
    check(prog["answered"] == prog["total"] and prog["completed"] is True, "progress A complete", str(prog))
    ca = c.post(f"{BASE}/tests/complete", headers=ha)
    cats = ca.json()["categories"]
    check(ca.status_code == 200 and len(cats) >= 5, "complete test A -> categories", f"{len(cats)} categories")

    # 4b. The profile outlives the evening it was made. This is the whole point of stage 89: a person
    # finishes the questionnaire, closes the app, and comes back days later to read the same result.
    # The route carries no identifier, so the read-back has to be the completion's own numbers —
    # bands and axes both, because the screen under the band opens exactly those axes.
    prof = c.get(f"{BASE}/tests/profile", headers=ha)
    body = prof.json()
    check(prof.status_code == 200 and body.get("categories") == cats,
          "profile reads back after the completion", f"{len(body.get('categories', []))} categories")
    check(body.get("axes") == ca.json().get("axes"),
          "read-back names the axes the completion printed", f"{len(body.get('axes', []))} axes")
    check(bool(body.get("updated_at")), "read-back dates the profile", str(body.get("updated_at"))[:19])
    anon = c.get(f"{BASE}/tests/profile")
    check(anon.status_code == 401, "profile refuses an anonymous reader", str(anon.status_code))

    # B takes test too (needed for compatibility)
    ansb = [{"question_id": q["id"], "option_id": q["options"][-1]["id"]} for q in qs if q["options"]]
    c.post(f"{BASE}/tests/answers", headers=hb, json={"answers": ansb})
    c.post(f"{BASE}/tests/complete", headers=hb)

    # Both halves of the pair read the same pathless route and get their own numbers: A answered the
    # first option of every question, B the last, so an identical read-back would mean one token read
    # another person's results.
    prof_b = c.get(f"{BASE}/tests/profile", headers=hb).json()
    check(prof_b.get("categories") != cats and prof_b.get("axes") != body.get("axes"),
          "each reader gets their own profile, not the other's",
          f"A {cats[0]['score']}% vs B {prof_b['categories'][0]['score']}%")

    # 5. discovery (page by cursor; endpoint caps limit at 50)
    items: list[dict] = []
    cursor = None
    seen_ids: set[str] = set()
    while True:
        params: dict = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        page = c.get(f"{BASE}/discover", headers=ha, params=params).json()
        batch = page.get("items", [])
        items.extend(batch)
        seen_ids.update(it["user_id"] for it in batch)
        if not page.get("has_more") or not batch:
            break
        cursor = page.get("next_cursor")
    check(len(items) > 0, "discovery returns candidates", f"{len(items)} cards")
    check(len(items) == len(seen_ids), "no card is served twice across pages", f"{len(items)} cards")
    b_in_disc = any(it["user_id"] == uid_b for it in items)
    check(b_in_disc, "B appears in A discovery", f"{len(items)} cards scanned")
    card = next((it for it in items if it["user_id"] == uid_b), items[0])
    hl = card.get("highlight")
    check(isinstance(hl, str) and len(hl) > 0, "discovery card has data-derived highlight", str(hl)[:60])
    check(0 <= card["compatibility"] <= 100, "card compatibility is real %", str(card["compatibility"]))

    # 6. open public profile
    pub = c.get(f"{BASE}/users/{uid_b}", headers=ha)
    check(pub.status_code == 200 and pub.json().get("name") == "Борис", "public profile B", str(pub.status_code))

    # 7. like (one-directional -> no match yet)
    like1 = c.post(f"{BASE}/users/{uid_b}/like", headers=ha).json()
    check(like1["liked"] is True and like1["match"] is False, "A likes B (no match yet)", str(like1))

    # 8. B likes A -> real match
    like2 = c.post(f"{BASE}/users/{uid_a}/like", headers=hb).json()
    check(like2["match"] is True and like2.get("match_id"), "B likes A -> MATCH", str(like2.get("match_id")))
    match_id = like2.get("match_id")

    # 9. matches list
    ml = c.get(f"{BASE}/matches", headers=ha).json()
    check(any(m["match_id"] == match_id for m in ml["matches"]), "match in A list", f"{len(ml['matches'])} matches")

    # 10. compatibility for the match
    comp = c.get(f"{BASE}/matches/{match_id}/compatibility", headers=ha).json()
    check(
        0 <= comp["overall"] <= 100 and comp["engine_version"] == 1 and len(comp["categories"]) >= 5,
        "compatibility engine",
        f"overall={comp['overall']}% engine=v{comp['engine_version']} cats={len(comp['categories'])}",
    )
    wsum = round(sum(cat["weight"] for cat in comp["categories"]), 6)
    check(abs(wsum - 1.0) < 1e-6, "category weights sum to 1.0", str(wsum))
    check(len(comp["shared_interests"]) > 0, "shared interests present", str(comp["shared_interests"][:4]))

    # determinism: same call -> same overall
    comp2 = c.get(f"{BASE}/matches/{match_id}/compatibility", headers=ha).json()
    check(comp2["overall"] == comp["overall"], "compatibility is deterministic", f"{comp['overall']}=={comp2['overall']}")

    # 10b. the pair map. The canvas both partners open reads this document, so a journey that
    # promises the product chain has no dead ends has to walk into it too: one map for the two of
    # them, the engine's own percent and weight per band, and a node that explains itself in the
    # unit the mark above its sentence prints.
    uni = c.get(f"{BASE}/matches/{match_id}/universe", headers=ha)
    check(uni.status_code == 200, "universe map opens for A", str(uni.status_code))
    ua = uni.json()
    ub = c.get(f"{BASE}/matches/{match_id}/universe", headers=hb).json()
    check(ub == ua, "both partners open one map, not two mirrors", f"{len(ua['layers'])} layers")
    check({ua["a_user_id"], ua["b_user_id"]} == {uid_a, uid_b}, "the two worlds are the two of them",
          f"{ua['a_user_id'][:8]} / {ua['b_user_id'][:8]}")
    check(ua["overall"] == comp["overall"] and ua["engine_version"] == comp["engine_version"],
          "the map arrives with the percent the pair has", f"map={ua['overall']} engine={comp['overall']}")
    band = {cat["category"]: cat for cat in comp["categories"]}
    check(len(ua["layers"]) == len(band) and all(l["category"] in band for l in ua["layers"]),
          "the map shows the bands the engine scored", str([l["category"] for l in ua["layers"]]))
    moved = [(l["category"], l["score"], band[l["category"]]["score"], l["weight"],
              band[l["category"]]["weight"], l["has_data"], band[l["category"]]["has_data"])
             for l in ua["layers"]
             if l["score"] != band[l["category"]]["score"] or l["weight"] != band[l["category"]]["weight"]
             or l["has_data"] != band[l["category"]]["has_data"]]
    check(not moved, "no second engine sits behind the map", str(moved[:3]))
    check(abs(sum(l["weight"] for l in ua["layers"]) - 1.0) < 1e-6,
          "map weights sum to 1.0", str(round(sum(l["weight"] for l in ua["layers"]), 6)))

    nodes = [(l, n) for l in ua["layers"] for n in l["nodes"]]
    check(len(nodes) >= 10, "the map has answers to draw", f"{len(nodes)} nodes")
    scale_offenders = [f"{l['category']}/{n['key']}" for l, n in nodes if _SCALE_VALUE.search(n["evidence"])]
    check(not scale_offenders, "every node explains itself in percents", str(scale_offenders[:3]))
    blank = [f"{l['category']}/{n['key']}" for l, n in nodes if not n["evidence"].strip()]
    check(not blank, "no node opens an empty explanation", str(blank[:3]))
    words = {n["connection"] for _, n in nodes}
    check(words <= _CONNECTIONS, "connection words are the four the screen splits on", str(sorted(words)))
    check("unknown" in words, "the map had an absence to draw on this path", str(sorted(words)))
    mismatched = [f"{l['category']}/{n['key']}" for l, n in nodes
                  if (n["connection"] == "unknown") is n["has_data"]]
    check(not mismatched, "an absence is never drawn as a meeting", str(mismatched[:3]))
    silent_with_number = [f"{l['category']}/{n['key']}" for l, n in nodes
                          if n["connection"] == "unknown" and re.search(r"\d", n["evidence"])]
    check(not silent_with_number, "an absence explains itself without a number", str(silent_with_number[:3]))
    off_scale = [(n["key"], n["a_value"], n["b_value"]) for _, n in nodes
                 if any(v is not None and not 0.0 <= v <= 1.0 for v in (n["a_value"], n["b_value"]))]
    check(not off_scale, "node answers stay on the 0..1 scale", str(off_scale[:3]))
    unnamed = [n["key"] for _, n in nodes if n["label"] == n["key"]]
    check(not unnamed, "every node is named, not keyed", str(unnamed[:3]))
    cov_wrong = [(l["category"], l["coverage"]) for l in ua["layers"]
                 if not 0.0 <= l["coverage"] <= 1.0
                 or abs(l["coverage"] - (sum(1 for n in l["nodes"] if n["has_data"]) / max(1, len(l["nodes"])))) > 1e-6]
    check(not cov_wrong, "coverage counts the compared nodes and sits beside the percent", str(cov_wrong[:3]))

    # 11. chat: A sends, B reads, B replies
    m1 = c.post(f"{BASE}/matches/{match_id}/messages", headers=ha, json={"body": "Привет! Это E2E сообщение."})
    check(m1.status_code in (200, 201) and m1.json()["is_own"] is True, "A sends message", str(m1.status_code))
    hist_b = c.get(f"{BASE}/matches/{match_id}/messages", headers=hb).json()
    check(any(m["body"].startswith("Привет") for m in hist_b["messages"]), "B sees A message", f"{len(hist_b['messages'])} msgs")
    unread = [m for m in hist_b["messages"] if not m["is_own"] and not m["is_read"]]
    check(len(unread) >= 1, "B has unread", str(len(unread)))
    rd = c.post(f"{BASE}/matches/{match_id}/read", headers=hb)
    check(rd.status_code in (200, 204), "B marks read", str(rd.status_code))
    m2 = c.post(f"{BASE}/matches/{match_id}/messages", headers=hb, json={"body": "Привет, Анна! Получено."})
    check(m2.status_code in (200, 201), "B replies", str(m2.status_code))
    hist_a = c.get(f"{BASE}/matches/{match_id}/messages", headers=ha).json()
    check(len(hist_a["messages"]) >= 2, "A sees full thread", f"{len(hist_a['messages'])} msgs")

    # 11b. realtime on the same pair; C exists only to be kept out of the room
    rc = c.post(f"{BASE}/auth/register", json={"email": f"e2e.c.{stamp}@befosmail.com", "password": pw, "password_confirm": pw})
    check(rc.status_code in (200, 201), "register C (a stranger to the pair)", str(rc.status_code))
    tok_c = rc.json()["tokens"]["access_token"]
    realtime(match_id, uid_a, uid_b, tok_a, tok_b, tok_c, c)
    stranger_map = c.get(f"{BASE}/matches/{match_id}/universe",
                         headers={"Authorization": f"Bearer {tok_c}"}).status_code
    check(stranger_map == 404, "the map is not open to a stranger", str(stranger_map))
    cd = c.delete(f"{BASE}/users/me", headers={"Authorization": f"Bearer {tok_c}"})
    check(cd.status_code == 200, "the stranger account is deleted again", str(cd.status_code))

    # 12. recommendations
    recs = c.get(f"{BASE}/matches/{match_id}/recommendations", headers=ha).json()
    rl = recs["recommendations"]
    check(len(rl) > 0 and all("reasons" in r for r in rl), "recommendations with reasons", f"{len(rl)} recs")
    positions = [r["position"] for r in rl]
    check(positions == sorted(positions), "recommendations ordered by position", str(positions[:5]))
    top = rl[0]
    check(len(top["reasons"]) > 0, "top rec has explanation", str(top["reasons"][:2]))
    sel = c.post(f"{BASE}/matches/{match_id}/recommendations/{top['activity']['id']}/select", headers=ha)
    check(sel.status_code in (200, 204), "select recommendation", str(sel.status_code))
    # The write above has a reader now: reopening the tab has to show the card as already
    # proposed, which is what stops the app from sending the same idea into this chat twice.
    reopened = c.get(f"{BASE}/matches/{match_id}/recommendations", headers=ha).json()["recommendations"]
    tapped = [r for r in reopened if r["activity"]["id"] == top["activity"]["id"]]
    check(len(tapped) == 1 and tapped[0]["selected"] is True,
          "the reopened page reads A's tap back", str([r.get("selected") for r in tapped]))

    # 12c. the hour the pair agrees on belongs to the conversation, not only to the card.
    plan_activity_id = top["activity"]["id"]
    plan_title = top["activity"]["title"]
    evening = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 3 * 86400))
    agreed_hour_reaches_the_chat(match_id, tok_a, tok_b, plan_activity_id, plan_title,
                                 f"{evening}T19:00:00+00:00", f"{evening}T21:00:00+00:00", c)

    # 12b. A re-takes the test with the other half of the answers. A pair's percent is a
    # stored number that two screens read, so this is where the stored copy could be caught
    # disagreeing with the compatibility screen, which computes live on every request.
    retook = [{"question_id": q["id"], "option_id": q["options"][-1]["id"]} for q in qs if q["options"]]
    c.post(f"{BASE}/tests/answers", headers=ha, json={"answers": retook})
    comp_now = c.get(f"{BASE}/matches/{match_id}/compatibility", headers=ha).json()
    row = next(m for m in c.get(f"{BASE}/matches", headers=ha).json()["matches"] if m["match_id"] == match_id)
    check(
        row["compatibility"] == comp_now["overall"],
        "match list shows the percent the pair has now",
        f"list={row['compatibility']} live={comp_now['overall']} (was {comp['overall']})",
    )
    # The canvas reads the same live derivation, so a re-take has to move the map and the stored
    # percent together — a map that kept the old document would show the pair a pair that no longer
    # exists.
    map_now = c.get(f"{BASE}/matches/{match_id}/universe", headers=ha).json()
    check(map_now["overall"] == comp_now["overall"],
          "the map follows the re-taken test", f"map={map_now['overall']} live={comp_now['overall']}")

    # 12d. a complaint, from the same pair, into the one door that can read it. The journey has
    # walked the tap that writes a report ever since stage 96; it never walked what happens after it.
    mod = complaint_reaches_a_moderator(c, ha, hb, uid_a, uid_b, f"e2e.d.{stamp}@befosmail.com", pw)

    # 13. IDOR: B cannot read A's private match with someone else / cross-account safety
    # A blocked-user flow
    blk = c.post(f"{BASE}/users/{uid_b}/block", headers=ha)
    check(blk.status_code == 200, "A blocks B", str(blk.status_code))
    maps_after = [c.get(f"{BASE}/matches/{match_id}/universe", headers=h).status_code for h in (ha, hb)]
    check(maps_after == [404, 404], "a dissolved pair has no map left to open", str(maps_after))
    named_after = c.put(f"{BASE}/matches/{match_id}/recommendations/{plan_activity_id}/time",
                        headers=ha, json={"when": f"{evening}T19:00:00+00:00"}).status_code
    check(named_after in (403, 404, 409), "a dissolved pair names no new hour", str(named_after))
    unblk_ok = c.get(f"{BASE}/users/{uid_b}", headers=ha).status_code
    check(unblk_ok in (200, 403, 404), "profile access after block is defined", str(unblk_ok))

    # 14. visibility toggle (backend field is `hidden`)
    vis = c.post(f"{BASE}/users/me/visibility", headers=ha, json={"hidden": True})
    check(vis.status_code == 200, "A hides profile", str(vis.status_code))
    vis2 = c.post(f"{BASE}/users/me/visibility", headers=ha, json={"hidden": False})
    check(vis2.status_code == 200, "A unhides profile", str(vis2.status_code))

    # 15. auth refresh (flat TokenPair) + logout (needs refresh_token body) + login again
    rf = c.post(f"{BASE}/auth/refresh", json={"refresh_token": ref_a})
    check(rf.status_code == 200 and "access_token" in rf.json(), "refresh token", str(rf.status_code))
    lo = c.post(f"{BASE}/auth/logout", headers=ha, json={"refresh_token": ref_a})
    check(lo.status_code in (200, 204), "logout A", str(lo.status_code))
    la2 = c.post(f"{BASE}/auth/login", json={"email": email_a, "password": pw})
    check(la2.status_code == 200, "login A again", str(la2.status_code))

    # 16. unauthorized access rejected
    noauth = c.get(f"{BASE}/users/me")
    check(noauth.status_code in (401, 403), "unauthorized /users/me rejected", str(noauth.status_code))

    # 17. delete account
    tok_a2 = la2.json()["tokens"]["access_token"]
    dele = c.delete(f"{BASE}/users/me", headers={"Authorization": f"Bearer {tok_a2}"})
    check(dele.status_code == 200, "delete account A", str(dele.status_code))

    # 18. an access token does not outlive the account behind it
    refused = socket_refused(f"{WS_BASE}/ws/chat/{match_id}?token={tok_a2}")
    check(refused != "accepted", "a deleted account gets no room", refused)

    # 19. the journey leaves no account behind: both halves of it are probe data
    deb = c.delete(f"{BASE}/users/me", headers=hb)
    check(deb.status_code == 200, "delete account B", str(deb.status_code))

    # 19b. what a complaint keeps after both accounts it names are gone. The row and its history are
    # the record of a decision about a person; an erasure that took them would leave the queue with
    # no way to answer the next complaint about the same name.
    if mod["report_id"]:
        kept = c.get(f"{BASE}/reports/{mod['report_id']}", headers=mod["hd"])
        body = kept.json() if kept.status_code == 200 else {}
        check(kept.status_code == 200 and body.get("status") == "resolved"
              and body.get("reported", {}).get("is_deleted") is True
              and body.get("reported", {}).get("age") is None,
              "the complaint outlives the accounts it names",
              f"{kept.status_code} {str(body.get('reported'))[:120]}")
        check(len(body.get("reviews", [])) == 2, "and the history of the decision outlives them too",
              str(len(body.get("reviews", []))))

        # 19c. the role goes with the account that held it: a deleted moderator opens nothing.
        dd = c.delete(f"{BASE}/users/me", headers=mod["hd"])
        check(dd.status_code == 200, "the moderator probe account is deleted again", str(dd.status_code))
        keyless = c.get(f"{BASE}/reports", headers=mod["hd"])
        check(keyless.status_code == 401, "a deleted account keeps no key to the queue", str(keyless.status_code))

    c.close()
    passed = sum(1 for ok, _ in results if ok)
    total = len(results)
    print(f"\n==== E2E RESULT: {passed}/{total} passed ====")
    failed = [lbl for ok, lbl in results if not ok]
    if failed:
        print("FAILED:", failed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
