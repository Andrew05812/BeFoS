"""The search city an owner names, and the deck that has to answer to it.

The read half of this row shipped years ago: `discovery_service` hands `city_preference` to
`social_repo._preference_conditions`, the candidate query compares `lower(Profile.city)` case-
insensitively, and an index leads with `lower(city)` exactly for that predicate. The write half
never came, so the column sat at NULL for every account the API had touched — `docs/DATABASE.md`
called the whole row «зарезервированная колонка, а не работающая функция», and the operating
handbook measured the city form of the candidate read by hand because no request could produce
it. Stage 104 puts the word into `PATCH /users/me` and into the answer about one's own account,
and this file pins the seam between the two halves.

What is asserted, in order: the owner's answer reads back what was written; naming a city narrows
the deck to that city while the same account without the word saw both; the narrowing binds even
when the deck was already built under the wider answer (the write must drop the stored queue, the
same rule `age_min` has lived by since the deck was first cached); case is not a second filter;
the empty and the whitespace answer both clear the word instead of storing a city nobody lives
in; an absent field is not an answer at all; a card of somebody else says nothing about where
they search; and a city of 121 characters is refused before it reaches the column.
"""

from __future__ import annotations

from httpx import AsyncClient

from .conftest import auth_headers, complete_onboarding, register_and_auth

ME = "/api/v1/users/me"
DECK = "/api/v1/discover"


async def _viewer(client: AsyncClient, email: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name="Ищущий", gender="male")
    return creds


async def _candidate(client: AsyncClient, email: str, name: str, city: str) -> dict:
    creds = await register_and_auth(client, email)
    await complete_onboarding(client, creds["token"], name=name, city=city, gender="female")
    return creds


async def _deck(client: AsyncClient, creds: dict) -> list[dict]:
    response = await client.get(
        DECK, params={"limit": 50}, headers=auth_headers(creds["token"])
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def _patch(client: AsyncClient, creds: dict, body: dict):
    return await client.patch(ME, json=body, headers=auth_headers(creds["token"]))


async def _own_answer(client: AsyncClient, creds: dict) -> dict:
    response = await client.get(ME, headers=auth_headers(creds["token"]))
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_owner_who_never_named_a_city_reads_null_back(client: AsyncClient):
    """Nobody's default is a filter.

    Onboarding does not ask for the search city, so the column stays NULL and the answer has to
    say `null` rather than invent an empty string the deck might read as a city of zero letters.
    """
    creds = await _viewer(client, "s104-none@befos.app")
    assert (await _own_answer(client, creds))["city_preference"] is None


async def test_the_city_an_owner_names_reads_back_from_the_owners_own_answer(client: AsyncClient):
    creds = await _viewer(client, "s104-write@befos.app")
    answer = await _patch(client, creds, {"city_preference": "Тверь"})
    assert answer.status_code == 200, answer.text
    assert answer.json()["city_preference"] == "Тверь"
    assert (await _own_answer(client, creds))["city_preference"] == "Тверь"


async def test_a_deck_answered_without_the_word_shows_both_cities(client: AsyncClient):
    """The premise the narrowing test is read against: both candidates are deckable as-is.

    Same age band, same gender answers, finished onboarding — the only thing that tells them
    apart is the city, and with no search city named neither is held back.
    """
    creds = await _viewer(client, "s104-wide@befos.app")
    tver = await _candidate(client, "s104-tver@befos.app", "Тверянка", "Тверь")
    moscow = await _candidate(client, "s104-moscow@befos.app", "Москвичка", "Москва")

    cards = await _deck(client, creds)
    shown = {card["user_id"] for card in cards}
    assert tver["user_id"] in shown, "the wide deck lost a candidate it was never filtered from"
    assert moscow["user_id"] in shown


async def test_naming_a_city_leaves_the_deck_only_the_cards_of_that_city(client: AsyncClient):
    """The seam this stage exists for: the write reaches the filter the read already had.

    The viewer's city is «Москва» and the preference is «Тверь»: if the deck still answered the
    viewer's own city, the filter would be decoration. The named city is the one that narrows.
    """
    creds = await _viewer(client, "s104-narrow@befos.app")
    tver = await _candidate(client, "s104-tver2@befos.app", "Тверянка", "Тверь")
    await _candidate(client, "s104-moscow2@befos.app", "Москвичка", "Москва")

    assert (await _patch(client, creds, {"city_preference": "Тверь"})).status_code == 200

    cards = await _deck(client, creds)
    shown = {card["user_id"] for card in cards}
    assert tver["user_id"] in shown, "the named city cut out its own candidate"
    assert all(card["city"] == "Тверь" for card in cards), [
        card["city"] for card in cards
    ]


async def test_a_deck_built_before_the_word_is_dropped_by_the_write(client: AsyncClient):
    """Paging through the old queue is not an answer to a new preference.

    The first read stores a queue that holds both cities. Without the invalidation the second
    read would hand back cards built for the previous answer — the same trap `_DECK_FIELDS`
    already closes for `age_min` and `gender_preference`; the city joins that set for the same
    reason, and this test is what keeps it there.
    """
    creds = await _viewer(client, "s104-stale@befos.app")
    await _candidate(client, "s104-tver3@befos.app", "Тверянка", "Тверь")
    moscow = await _candidate(client, "s104-moscow3@befos.app", "Москвичка", "Москва")

    first = await _deck(client, creds)
    assert moscow["user_id"] in {card["user_id"] for card in first}

    assert (await _patch(client, creds, {"city_preference": "Тверь"})).status_code == 200

    second = await _deck(client, creds)
    assert moscow["user_id"] not in {card["user_id"] for card in second}, (
        "the stored queue outlived the preference that made it"
    )


async def test_the_filter_is_not_a_second_case(client: AsyncClient):
    """«тверь» finds «Тверь» — the read compares both sides lower-cased, the write stores the word.

    Storing the case untouched and comparing folded is how `city` itself already behaves;
    the preference follows the same rule so the two columns cannot disagree about «the same city».
    """
    creds = await _viewer(client, "s104-case@befos.app")
    tver = await _candidate(client, "s104-tver4@befos.app", "Тверянка", "Тверь")

    answer = await _patch(client, creds, {"city_preference": "тверь"})
    assert answer.status_code == 200, answer.text
    assert answer.json()["city_preference"] == "тверь"

    cards = await _deck(client, creds)
    assert tver["user_id"] in {card["user_id"] for card in cards}
    assert cards, "a folded preference matched nothing it should have matched"


async def test_the_empty_answer_clears_the_word_and_widens_the_deck(client: AsyncClient):
    """«снимите фильтр» is a string the client can send, not a null it cannot.

    The Android client drops absent fields on the way out (`explicitNulls = false`), so the only
    erase a real request can carry is the empty string — and an empty string the schema refused
    would leave the deck narrowed forever, with the screen showing an empty field.
    """
    creds = await _viewer(client, "s104-clear@befos.app")
    await _candidate(client, "s104-tver5@befos.app", "Тверянка", "Тверь")
    moscow = await _candidate(client, "s104-moscow5@befos.app", "Москвичка", "Москва")

    assert (await _patch(client, creds, {"city_preference": "Тверь"})).status_code == 200
    assert (await _patch(client, creds, {"city_preference": ""})).status_code == 200
    assert (await _own_answer(client, creds))["city_preference"] is None

    cards = await _deck(client, creds)
    assert moscow["user_id"] in {card["user_id"] for card in cards}


async def test_a_city_of_only_spaces_is_the_same_erase(client: AsyncClient):
    """Spaces are the user's empty, not a city with three letters nobody lives in.

    The strip runs before the store for `city` since the whitespace audit; the preference is
    read the same way, or the deck would filter against «   » and answer nobody at all.
    """
    creds = await _viewer(client, "s104-spaces@befos.app")
    assert (await _patch(client, creds, {"city_preference": "Тверь"})).status_code == 200
    answer = await _patch(client, creds, {"city_preference": "   "})
    assert answer.status_code == 200, answer.text
    assert answer.json()["city_preference"] is None


async def test_a_request_that_says_nothing_about_the_city_leaves_it_alone(client: AsyncClient):
    """Absent is not «снимите»: a screen that saves the name must not erase the filter beside it.

    `exclude_unset` is what makes the distinction real, so the promise is pinned from the wire,
    not from the service's defaults.
    """
    creds = await _viewer(client, "s104-absent@befos.app")
    assert (await _patch(client, creds, {"city_preference": "Сочи"})).status_code == 200

    answer = await _patch(client, creds, {"name": "Другое имя"})
    assert answer.status_code == 200, answer.text
    assert answer.json()["city_preference"] == "Сочи"


async def test_a_city_longer_than_the_column_is_refused_before_it_reaches_it(client: AsyncClient):
    creds = await _viewer(client, "s104-long@befos.app")
    refused = await _patch(client, creds, {"city_preference": "А" * 121})
    assert refused.status_code == 422, refused.text
    assert (await _own_answer(client, creds))["city_preference"] is None


async def test_the_preference_travels_with_no_answer_about_somebody_else(client: AsyncClient):
    """Where a person searches is their own business, not a line on somebody's card.

    The public read is built from a narrower set of fields; a search city is not one of them,
    and a reader who learned it could tell that a person plans to move. The owner's routes carry
    it; the card route does not — the same split the moderation role already lives by.
    """
    owner = await _viewer(client, "s104-priv@befos.app")
    assert (await _patch(client, owner, {"city_preference": "Псков"})).status_code == 200

    stranger = await _viewer(client, "s104-peek@befos.app")
    card = await client.get(
        f"/api/v1/users/{owner['user_id']}", headers=auth_headers(stranger["token"])
    )
    assert card.status_code == 200, card.text
    assert "city_preference" not in card.json()
