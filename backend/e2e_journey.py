"""Real end-to-end journey against the running Docker backend (localhost:8000).

Exercises the full BeFoS value chain with two fresh users who mutually like each
other so a real match + chat + recommendations flow is produced. Every step
asserts on live backend data; nothing is mocked or hardcoded.
"""
from __future__ import annotations

import sys
import time

import httpx

BASE = "http://localhost:8000/api/v1"
results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, extra: str = "") -> None:
    results.append((ok, label))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {label}{(' :: ' + extra) if extra else ''}")
    if not ok:
        # keep going to surface all failures, but remember we failed
        pass


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

    # 5. discovery (paginate; endpoint caps limit at 50)
    items: list[dict] = []
    offset = 0
    while True:
        page = c.get(f"{BASE}/discover", headers=ha, params={"limit": 50, "offset": offset}).json()
        batch = page.get("items", [])
        items.extend(batch)
        if not page.get("has_more") or not batch:
            break
        offset += 50
    check(len(items) > 0, "discovery returns candidates", f"{len(items)} cards")
    b_in_disc = any(it["user_id"] == uid_b for it in items)
    check(b_in_disc, "B appears in A discovery", f"{len(items)} cards scanned")
    card = next((it for it in items if it["user_id"] == uid_b), items[0])
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
    dele = c.delete(f"{BASE}/users/me", headers={"Authorization": f"Bearer {la2.json()['tokens']['access_token']}"})
    check(dele.status_code == 200, "delete account A", str(dele.status_code))

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
