"""The card of the person you matched with has no way to be opened, and one route to it is refused.

Stage 72 §2 asked for a map of every screen and every transition, walked from the navigation graph
(`android/app/src/main/java/app/befos/presentation/navigation/BeFosNavHost.kt`) and measured against
the live stand. The map has ten destinations and one of them — `Routes.PUBLIC_PROFILE` — is reachable
from exactly one place: a Discovery card. A mutual match removes that card, measured on the running
stack (`s72_d10_hide_pair.txt`, прогон 00:50:12…00:50:17 UTC): after the pair forms, the page of
candidates for the person who is in it answers 46 cards and does not contain the partner's id.
`MatchListScreen` hands its row only to `onOpenChat`, `ChatScreen` only to compatibility and
recommendations, and `ChatViewModel.loadPartner()` takes the whole `PublicProfile` the server answers
with and keeps `.name`. So the person who is closest to the user is the one person whose card cannot
be read again.

The answer is not to point that link at the deck route. `GET /users/{id}` filters by the deck's rule
on purpose, and `tests/test_match_detail_after_partner_hides.py:90` pins that decision: «the public
profile route keeps the deck's rule, so the switch remains enforceable against an id copied from a
link or a screenshot». Measured with the same probe: once the partner presses «Скрыть из подбора»,
`GET /users/{id}` answers 404 to their own match while `GET /matches/{id}` answers 200 with the same
card, because the pair proved membership against the `matches` row. A link built on the deck route
would therefore open «Профиль недоступен» on a live conversation.

The checks below read the Kotlin sources and require the pair path to arrive through the match route
— the one the backend already answers — and to hold back the gestures that only make sense before a
pair exists.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1].parent
CLIENT = ROOT / "android/app/src/main/java/app/befos"
ROUTES = CLIENT / "presentation/navigation/Routes.kt"
NAV_HOST = CLIENT / "presentation/navigation/BeFosNavHost.kt"
CHAT_SCREEN = CLIENT / "presentation/chat/ChatScreen.kt"
PROFILE_SCREEN = CLIENT / "presentation/publicprofile/PublicProfileScreen.kt"
PROFILE_VM = CLIENT / "presentation/publicprofile/PublicProfileViewModel.kt"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_a_card_opened_from_a_pair_names_the_pair_not_a_stranger_s_id() -> None:
    """The destination a pair uses is keyed by the match, because that is what proves membership.

    A user id alone selects the deck rule; a match id selects the rule the backend already wrote
    down for a pair in `_match_peer_conditions` (`backend/app/repositories/user_repo.py`).
    """
    routes = _read(ROUTES)
    partner = re.search(r'val PARTNER = "(?P<route>[^"]+)"', routes)
    assert partner is not None, "Routes.kt declares no partner destination for a pair to open"
    key = re.fullmatch(r"[\w/]+\{\$([A-Z_]+)\}", partner["route"])
    assert key is not None, (
        f"the partner destination is not keyed by one argument: {partner['route']}"
    )
    # Routes.kt spells its placeholders through the shared argument constants, so the word
    # `matchId` lives one line away from the route instead of inside it.
    declared = re.search(
        rf'const val {key.group(1)} = "(?P<name>[^"]+)"', routes
    )
    assert declared is not None, f"Routes.kt references an undeclared argument {key.group(1)}"
    assert declared["name"] == "matchId", (
        f"the pair's card is keyed by {declared['name']}, which selects the deck rule"
    )
    builder = re.search(r'fun partner\((?P<args>[^)]*)\)', routes)
    assert builder is not None, "Routes.kt has no partner(matchId) builder to navigate with"
    assert "matchId" in builder["args"], "the partner builder does not carry the pair id"


def test_the_chat_screen_offers_the_transition_and_the_graph_answers_it() -> None:
    """A destination nobody navigates to is not a screen: the chat has to hand it over."""
    nav = _read(NAV_HOST)
    assert re.search(r"Routes\.partner\(", nav) is not None, (
        "BeFosNavHost.kt never navigates to the partner destination"
    )
    chat = re.search(r"ChatScreen\((?P<body>.*?)\n            \)", nav, re.S)
    assert chat is not None, "BeFosNavHost.kt no longer builds ChatScreen where it can be read"
    assert "onOpenPartner" in chat["body"], (
        "the chat is wired without a way to the partner's card"
    )
    screen = _read(CHAT_SCREEN)
    assert re.search(r"onOpenPartner\w*: \(\) -> Unit", screen) is not None, (
        "ChatScreen.kt takes no partner-card callback"
    )


def test_the_card_of_a_partner_is_read_through_the_route_that_answers_the_pair() -> None:
    """The deck read is refused to a partner who hides: measured 404 in `s72_d10_hide_pair.txt`."""
    vm = _read(PROFILE_VM)
    assert "matchRepository" in vm, "PublicProfileViewModel is given no way to read the pair route"
    assert re.search(r"matchRepository\.partner\(", vm) is not None, (
        "PublicProfileViewModel never asks the pair route for the card"
    )
    assert re.search(r"fun loadPartner|matchId", vm) is not None, (
        "PublicProfileViewModel has no notion of being opened from a pair"
    )


def test_a_pair_is_not_offered_the_gestures_that_ended_when_they_matched() -> None:
    """«Нравится» and «Пропустить» answer the question of whether to introduce two strangers.

    Once the two are a pair the question is closed: liking again re-answers it, and passing is
    refused by the deck's own bookkeeping, so the screen has to hold the row back rather than let
    the user press a button whose answer cannot arrive.
    """
    screen = _read(PROFILE_SCREEN)
    like = re.search(r'text = "Нравится"', screen)
    assert like is not None, "PublicProfileScreen.kt no longer offers the gesture checked here"
    guard = re.search(r"if \(!state\.\w*[Pp]artner\w*\) \{", screen) or re.search(
        r"if \(!state\.pair\) \{", screen
    )
    assert guard is not None, (
        "the gesture row is drawn for a pair as well: nothing holds «Нравится» back once the two"
        " matched"
    )
    gestures = screen[guard.start() : screen.find("Нравится", guard.start())]
    assert "Пропустить" in gestures, "the guard holds back only one of the two gestures"


def test_the_deck_still_opens_the_same_screen_by_a_user_id() -> None:
    """The pair path is added, not substituted: a stranger's card still arrives by its own route."""
    vm = _read(PROFILE_VM)
    assert re.search(r"profileRepository\.publicProfile\(", vm) is not None, (
        "PublicProfileViewModel no longer reads the deck route a Discovery card opens"
    )
    nav = _read(NAV_HOST)
    assert "Routes.PUBLIC_PROFILE" in nav, "the deck destination has left the graph"
