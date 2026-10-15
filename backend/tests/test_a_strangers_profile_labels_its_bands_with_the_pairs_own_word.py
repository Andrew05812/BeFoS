"""A stranger's profile labels its bands with the pair's own word.

Stage 72-1 put ``has_data`` next to every band so an unmeasured category stopped being sold as a
measured 50 %, and the compatibility screen gained the sentence under its list that says what the
percents are: an итог built from weighted categories, with a band that had nothing to compare on
printed as «нет данных». The list itself went into ``presentation/common/CategoryScoreList.kt`` as a
shared composable, and the public profile of another person started using it — bands, rows, the word
«важность» in every row and the word «нет данных» in the empty ones. The caption stayed behind on
the pair screen.

That is a product-integrity defect, not a wording gap, and it is a different one from stage 72-1:

* on the pair screen a percent can only be read as a similarity, because both halves of the pair are
  on screen and the heading says «ВАША СОВМЕСТИМОСТЬ»;
* on a stranger's profile the same digits appear under «Совместимость по категориям» for a person
  the reader has never answered alongside, and the rows carry «важность 80%» — which is the engine's
  contribution weight, not a trait of the woman in the photo. Nothing on that screen says the number
  was built from the reader's own answers as much as from hers.

So the caption belongs to the list, not to the screen that found it. One function in
``presentation/common``, called by both screens that draw ``CategoryScoreList``; and the screens whose
bands are personal — the questionnaire result and the person's own profile, where the engine sends no
weight at all — must not print it, because there is no shared total for it to explain.

The pair screen also gains the way into the reader's own bands. The caption says these percents are
not one person's trait; a person who wants the reading that is theirs has to be able to act on that,
and stage 89 already built that screen and its route. No new route, no new read, no new endpoint.

Red state on the tree before this stage: ``git grep -n pairBandsCaption`` over the client returns
nothing, the compatibility screen keeps its own copy of the sentence at ``CompatibilityScreen.kt``
149-152, and the public profile prints the list with no caption at all under it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1].parent
CLIENT = ROOT / "android/app/src/main/java/app/befos"
LIST = CLIENT / "presentation/common/CategoryScoreList.kt"
READOUT_TEST = ROOT / "android/app/src/test/java/app/befos/presentation/common/CategoryReadoutTest.kt"
CAPTION_TEST = ROOT / "android/app/src/test/java/app/befos/presentation/common/PairBandsCaptionTest.kt"
PAIR_SCREEN = CLIENT / "presentation/compatibility/CompatibilityScreen.kt"
PUBLIC_SCREEN = CLIENT / "presentation/publicprofile/PublicProfileScreen.kt"
MY_PROFILE_SCREEN = CLIENT / "presentation/profile/MyProfileScreen.kt"
TEST_SCREEN = CLIENT / "presentation/test/TestScreen.kt"
LABELS = CLIENT / "presentation/common/Labels.kt"
NAV_HOST = CLIENT / "presentation/navigation/BeFosNavHost.kt"
ROUTES = CLIENT / "presentation/navigation/Routes.kt"

# The words the caption has to own, and the word the rows print for a band without a comparison.
UNIT_PHRASE = "сходство двух анкет"
DENIAL_PHRASE = "не черта одного человека"
IMPORTANCE_WORD = "важность"
ABSENCE_WORD = "нет данных"


def _read(path: Path) -> str:
    assert path.is_file(), f"{path.relative_to(ROOT)} is not in the working tree"
    return path.read_text(encoding="utf-8")


def _caption_body(source: str) -> str:
    """The string the shared caption returns, assembled out of its pieces."""
    start = source.index("fun pairBandsCaption")
    ends = [source.index(marker, start) for marker in ("}", "\n\n") if marker in source[start:]]
    body = source[start : min(ends)] if ends else source[start:]
    return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', body))


def test_the_caption_is_written_once_in_the_client() -> None:
    """One function, one sentence, so the two screens cannot drift apart later."""
    definitions = list(CLIENT.rglob("*.kt"))
    hits = [p for p in definitions if "fun pairBandsCaption" in _read(p)]
    assert len(hits) == 1, (
        f"the band caption is written in {len(hits)} files "
        f"({[str(p.relative_to(ROOT)) for p in hits]}); a second copy is a second wording to keep "
        "in step, and the screens would disagree the moment one of them is edited"
    )
    assert LIST in hits, "the caption does not live next to the list it captions"


def test_no_screen_keeps_a_private_copy_of_the_sentence() -> None:
    """The pair screen hands its wording over rather than keeping it."""
    pair = _read(PAIR_SCREEN)
    assert "pairBandsCaption()" in pair, (
        "CompatibilityScreen.kt still writes its own caption instead of reading the shared one"
    )
    assert "Итог — сумма категорий" not in pair, (
        "CompatibilityScreen.kt keeps a private copy of the sentence; two wordings for one list is "
        "exactly the drift the shared function exists to prevent"
    )
    for name, source in (("CompatibilityScreen.kt", pair), ("PublicProfileScreen.kt", _read(PUBLIC_SCREEN))):
        assert ABSENCE_WORD not in source, (
            f"{name} spells the absence word itself; it belongs to categoryReadout() and to the "
            "caption that quotes it, and a third copy would be free to disagree with both"
        )


def test_the_strangers_profile_signs_its_bands_with_the_same_word() -> None:
    """The screen that shows another person's bands captions them as a similarity of two."""
    public = _read(PUBLIC_SCREEN)
    assert "CategoryScoreList(" in public, "PublicProfileScreen.kt no longer draws the shared list"
    assert "pairBandsCaption()" in public, (
        "PublicProfileScreen.kt prints the pair's percents with no caption: the reader of a "
        "stranger's profile is the second half of every number on that list, and nothing on screen "
        "says so"
    )


def test_the_caption_names_the_unit_and_denies_the_misreading() -> None:
    """The sentence does the two things the defect requires of it, in the client's own words."""
    caption = _caption_body(_read(LIST))
    assert UNIT_PHRASE in caption, f"the caption does not name its unit: {caption!r}"
    assert DENIAL_PHRASE in caption, (
        f"the caption leaves a band readable as one person's trait: {caption!r}"
    )
    assert IMPORTANCE_WORD in caption, (
        "the rows print «важность» and the caption leaves it unexplained"
    )
    assert ABSENCE_WORD in caption, "the caption does not quote the word the empty band prints"
    assert not any(ch.isdigit() for ch in caption), (
        f"the caption prints a number of its own: {caption!r} — it would compete with the percents "
        "it stands under"
    )


def test_the_personal_bands_do_not_borrow_the_pair_caption() -> None:
    """A person's own bands have no weight and no shared total; the caption promises both."""
    for screen, name in ((MY_PROFILE_SCREEN, "MyProfileScreen.kt"), (TEST_SCREEN, "TestScreen.kt")):
        assert "pairBandsCaption()" not in _read(screen), (
            f"{name} captions personal bands with the pair's sentence — the engine sends no weight "
            "for a single person, so «важность» and the итог it feeds are not on that screen"
        )


def test_the_caption_is_pinned_by_a_client_test() -> None:
    """The wording is a measured claim about the client, not a description of it."""
    test_source = _read(CAPTION_TEST)
    assert "pairBandsCaption()" in test_source, (
        "PairBandsCaptionTest.kt never reads the caption the screens print"
    )
    for phrase in (UNIT_PHRASE, DENIAL_PHRASE, IMPORTANCE_WORD):
        assert phrase in test_source, f"the client test does not pin «{phrase}»"
    assert "categoryReadout(" in test_source, (
        "the client test quotes the absence word as text instead of reading it from the function "
        "that prints it"
    )
    assert "ch.isDigit()" in test_source or "isdigit" in test_source, (
        "the client test does not hold the caption to carrying no digit of its own"
    )
    assert _read(READOUT_TEST), "the readout the caption quotes is not pinned anywhere"


def test_the_pair_screen_leads_to_the_readers_own_bands() -> None:
    """Saying the percent is not one person's trait has to come with the place that is."""
    pair = _read(PAIR_SCREEN)
    assert re.search(r"onOpenMyProfile: \(\) -> Unit", pair) is not None, (
        "CompatibilityScreen.kt takes no way into the reader's own profile"
    )
    assert "myProfileEntryWord()" in pair, (
        "the entry on the pair screen spells its own name for the screen; two names for one route "
        "read as two profiles"
    )
    nav = _read(NAV_HOST)
    assert nav.count("navigate(Routes.MY_PROFILE)") == 3, (
        f"the navigation host opens the personal profile {nav.count('navigate(Routes.MY_PROFILE)')} "
        "times: the pair screen has to join the profile tab and the questionnaire result, and a "
        "fourth would mean a new screen was built for the same reading"
    )
    compatibility_wiring = nav[nav.index("CompatibilityScreen(") :]
    compatibility_wiring = compatibility_wiring[: compatibility_wiring.index("\n        }")]
    assert "onOpenMyProfile" in compatibility_wiring, (
        "the host wires the personal profile somewhere else than on the pair screen"
    )


def test_the_reading_of_oneself_still_has_one_route_and_one_name() -> None:
    """No new screen and no new route came with the entry."""
    routes = _read(ROUTES)
    assert len(re.findall(r'const val MY_PROFILE = "([^"]+)"', routes)) == 1, (
        "the personal profile gained a second route constant"
    )
    assert re.search(r'const val MY_PROFILE = "myProfile"', routes) is not None, (
        "the personal profile route changed its path — every saved link to it would break"
    )
    labels = _read(LABELS)
    assert len(re.findall(r'fun myProfileEntryWord\(\): String = "([^"]+)"', labels)) == 1, (
        "the entry word is spelled in more than one place"
    )
