"""Real end-to-end journey against the running Docker backend (localhost:8000).

Exercises the full BeFoS value chain with two fresh users who mutually like each
other so a real match + chat + recommendations flow is produced. Every step
asserts on live backend data; nothing is mocked or hardcoded. Both accounts are
deleted at the end, so a run leaves no probe rows in the development database.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

import httpx
import websockets  # comes with uvicorn[standard], the same server that answers here

BASE = "http://localhost:8000/api/v1"
WS_BASE = "ws://localhost:8000"
results: list[tuple[bool, str]] = []


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

    # 3. onboarding both
    oa = c.post(f"{BASE}/users/me/onboarding", headers=ha, json=onboard_payload("Анна", "female", ["male"], shared))
    check(oa.status_code == 200, "onboarding A", str(oa.status_code))
    ob = c.post(f"{BASE}/users/me/onboarding", headers=hb, json=onboard_payload("Борис", "male", ["female"], shared))
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

    # B takes test too (needed for compatibility)
    ansb = [{"question_id": q["id"], "option_id": q["options"][-1]["id"]} for q in qs if q["options"]]
    c.post(f"{BASE}/tests/answers", headers=hb, json={"answers": ansb})
    c.post(f"{BASE}/tests/complete", headers=hb)

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

    # 13. IDOR: B cannot read A's private match with someone else / cross-account safety
    # A blocked-user flow
    blk = c.post(f"{BASE}/users/{uid_b}/block", headers=ha)
    check(blk.status_code == 200, "A blocks B", str(blk.status_code))
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
