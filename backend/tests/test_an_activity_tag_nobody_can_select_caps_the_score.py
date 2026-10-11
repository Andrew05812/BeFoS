from __future__ import annotations

"""An activity is scored against its own tag list, so a tag nobody can name is a permanent cut.

`_interest_match` divides the pair's coverage by ``len(act_set)`` — the activity's own list — and
that component carries weight 0.40, the largest in the recommendation score. Two consequences
follow, and the two are easy to confuse:

* A tag that exists in the interest catalogue but that this particular pair did not name is a real
  difference between the pair and the activity. It has to lower the card, and it does.
* A tag that is not in the catalogue at all cannot be named by anybody, on any screen. It lowers
  the card for every pair, forever, and no edit to any profile can lift it back. Seven of the 25
  shipped activities carried such a tag (``nature`` on four of them, ``food`` on two, ``art`` on
  one) — the *category* an interest belongs to, written where a *slug* was expected.

The first rule is kept by the control below; the second is what the rest of this file guards.
"""

import pytest
from httpx import AsyncClient

from .conftest import answer_all_questions, auth_headers, complete_onboarding, register_and_auth
from app.recommendations.engine import ActivitySignal, UserSignal, _interest_match
from app.seed_data.activities_catalog import ACTIVITIES
from app.seed_data.interests_catalog import INTERESTS

# A thing a person can actually pick: the picker reads the `interests` table, which is seeded from
# this catalogue. An interest *category* name (``nature``, ``food``, ``art``) is not in it — those
# three are among the ten groups the 40 selectable interests are sorted into, not interests itself.
SELECTABLE = {slug for slug, _name, _category in INTERESTS}


def _signals() -> dict[str, ActivitySignal]:
    """The shipped catalogue as the engine sees it, keyed by slug.

    Ids are the enumerate index because `recommend` breaks a score tie by ``activity_id``, and a
    hash-based id would make the page order change between runs of the same code.
    """
    by_slug: dict[str, ActivitySignal] = {}
    for aid, (slug, title, _description, category, tags, cities, energy, social, _cost) in enumerate(
        ACTIVITIES, start=1
    ):
        by_slug[slug] = ActivitySignal(
            activity_id=aid,
            slug=slug,
            title=title,
            category=category,
            interests=list(tags),
            cities=list(cities),
            energy=energy,
            social=social,
        )
    return by_slug


def _assembled(tags: set[str]) -> UserSignal:
    """One half of the best pair a person can actually assemble for this card.

    Everything the card lists that the picker offers, and nothing that it does not — no profile on
    no screen can name a word the interest catalogue never carries. Both halves get the same set,
    and the city and the goal are ones every card accepts, so coverage is all that is left to move
    the number.
    """
    return UserSignal(interests=tags & SELECTABLE, city="Москва", dating_goal="relationship")


def test_every_activity_tag_is_an_interest_a_person_can_pick():
    """The root invariant: the denominator has to be reachable.

    Seven rows failed this when the stage started. The assertion names the offenders rather than
    just counting them, because the fix is to drop the word from that row's list, not to add a new
    interest to the catalogue — `hiking_trip` is already about nature, and its own ``category``
    column says so.
    """
    unreachable = {
        spec[0]: sorted(set(spec[4]) - SELECTABLE)
        for spec in ACTIVITIES
        if set(spec[4]) - SELECTABLE
    }
    assert unreachable == {}, (
        "these activities are tagged with words the interest picker never offers, so no pair can "
        f"ever cover them and their score is capped for everybody: {unreachable}"
    )


def test_no_activity_is_left_without_a_tag_two_people_can_share():
    """Dropping the dead tag must not have emptied a list or left a word in it twice.

    A control on the shape of the repair: it is green on the shipped catalogue too, so a green run
    of this file does not rest on it.
    """
    broken = {
        spec[0]: spec[4]
        for spec in ACTIVITIES
        if not spec[4] or len(set(spec[4])) != len(spec[4])
    }
    assert broken == {}, f"an activity has to carry at least one tag, named once: {broken}"


def test_the_best_pair_a_person_can_assemble_reaches_the_ceiling():
    """The component, over the whole real catalogue: full coverage must pay the full weight.

    This is where the shipped catalogue fails, and it fails on exactly seven rows: 0.5 for
    `volunteering`, which listed one readable tag and one unreadable, 0.667 for the four rows that
    lost one tag of three, and 0.75 for the two that lost one of four. The dead tag sits in the
    denominator while nothing can put it in the numerator.
    """
    capped = []
    for slug, act in _signals().items():
        pair = _assembled(set(act.interests))
        interest, _reasons = _interest_match(act, pair, pair)
        if interest < 1.0:
            capped.append((slug, round(interest, 4), sorted(set(act.interests) - SELECTABLE)))
    assert capped == [], f"no pair can reach the ceiling of these cards: {capped}"


def test_a_tag_the_pair_did_not_name_still_lowers_its_card():
    """The other rule, which the fix must not break: unreachable and unchosen are not the same.

    `photo_walk` lists three tags and all three are things a person can pick. A pair naming one of
    them covers a third of the list, and a third of the list is a third of the component — 0.333.
    Green on both catalogues, because both leave a real, selectable tag unnamed: that a card can be
    covered partially is the rule, not the defect this stage repairs.
    """
    act = _signals()["photo_walk"]
    assert set(act.interests) <= SELECTABLE, "the control needs a list a person could fully name"
    assert len(act.interests) == 3
    one = _assembled({"photography"})
    assert _interest_match(act, one, one)[0] == pytest.approx(1 / 3)
    whole = _assembled(set(act.interests))
    assert _interest_match(act, whole, whole)[0] == pytest.approx(1.0)


# ---------- against the API ----------


async def _ready(client: AsyncClient, email: str, name: str, interests: list[str]) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, interests=interests)
    await answer_all_questions(client, creds["token"])
    return creds


@pytest.fixture
async def volunteering_pair(client: AsyncClient):
    """A pair that names every tag `volunteering` lists, and nothing that would pad the score.

    Three interests because onboarding asks for at least three. `cinema` and `board_games` are the
    whole tag lists of two other activities, so the pair fully covers those cards too and the page
    has three cards that should reach the same ceiling — but the fixture names nothing else, so no
    card is given coverage it did not have to earn.
    """
    interests = ["volunteering", "cinema", "board_games"]
    a = await _ready(client, "cap_a@befos.app", "Аня", interests)
    b = await _ready(client, "cap_b@befos.app", "Боря", interests)
    await client.post(
        f"/api/v1/users/{b['user_id']}/like", json={}, headers=auth_headers(a["token"])
    )
    mutual = await client.post(
        f"/api/v1/users/{a['user_id']}/like", json={}, headers=auth_headers(b["token"])
    )
    assert mutual.status_code in (200, 201), mutual.text
    return a, mutual.json()["match_id"]


async def test_the_page_the_endpoint_stores_pays_the_interest_weight_in_full(
    client: AsyncClient, volunteering_pair
):
    """The ceiling as the product returns it, for the card that lost the most.

    `volunteering` listed two tags and one of them was unreadable, so the best pair there is got
    0.5 of the component: half of the 40 points it is worth. Everything else on that request is
    fixed by the fixture and does not depend on the card: the activity ships `cities = []`, so
    location is 1.0; both people answered the questionnaire the same way, so their lifestyle vectors
    are identical and that component is 1.0; and `relationship` × `relationship` is 1.0 in the goal
    table. That leaves 0.40 + 0.15 + 0.15 + 0.10 = 0.80 guaranteed before any leisure signal, so
    the card cannot come back below 80. Measured: 91 on this repair, 71 on the shipped list.
    """
    a, match_id = volunteering_pair
    resp = await client.get(
        f"/api/v1/matches/{match_id}/recommendations?force=true",
        headers=auth_headers(a["token"]),
    )
    assert resp.status_code == 200, resp.text
    cards = {c["activity"]["slug"]: c for c in resp.json()["recommendations"]}
    assert "volunteering" in cards, (
        f"the pair covers this card completely, yet the page does not carry it: {sorted(cards)}"
    )
    card = cards["volunteering"]
    assert card["score"] >= 80, (
        f"a pair naming every tag of the card was paid {card['score']} of the 100 it promises; "
        "the interest component is being divided by a tag nobody can select"
    )
    assert any("Волонтёрство" in r for r in card["reasons"]), card["reasons"]


async def test_the_interest_weight_is_what_a_covering_pair_earns(
    client: AsyncClient, volunteering_pair
):
    """The size of the component, read off two pages of one pair: no coverage to full is 40 points.

    The same two people and the same card, requested once while they name every tag it lists and
    once after they name none. Everything the other components see is identical across the two
    pages: the city, the answers (equal vectors, so the same lifestyle number on both requests),
    the goal, and leisure, which is a property of the card rather than of the pair. The only thing
    that moves is the interest component, and it is worth 0.40 — 40 of the 100 the endpoint
    promises.

    Measured on the shipped tag lists: 71 and 51, a gap of 20, because the covering pair could not
    reach more than half of the card. Measured on this repair: 91 and 51.
    """
    a, match_id = volunteering_pair
    headers = auth_headers(a["token"])
    covered = await client.get(
        f"/api/v1/matches/{match_id}/recommendations?force=true", headers=headers
    )
    assert covered.status_code == 200, covered.text
    covered_card = {
        c["activity"]["slug"]: c for c in covered.json()["recommendations"]
    }.get("volunteering")
    assert covered_card is not None, covered.json()["recommendations"]

    for email in ("cap_a@befos.app", "cap_b@befos.app"):
        login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "Test12345"}
        )
        assert login.status_code == 200, login.text
        token = login.json()["tokens"]["access_token"]
        silent = await client.patch(
            "/api/v1/users/me", json={"interests": []}, headers=auth_headers(token)
        )
        assert silent.status_code == 200, silent.text

    silent_page = await client.get(
        f"/api/v1/matches/{match_id}/recommendations?force=true", headers=headers
    )
    assert silent_page.status_code == 200, silent_page.text
    silent_cards = {c["activity"]["slug"]: c for c in silent_page.json()["recommendations"]}
    silent_card = silent_cards.get("volunteering")
    assert silent_card is not None, (
        "a pair naming nothing still has to be shown the card, or the comparison below cannot be "
        f"made: {sorted(silent_cards)}"
    )
    assert covered_card["score"] - silent_card["score"] == 40, (
        f"the interest component paid {covered_card['score'] - silent_card['score']} of its 40 "
        "points for a pair that went from naming every tag of the card to naming none"
    )
