"""An explanation under a card has to name the pair's own data, not the threshold that printed it.

§81 of the sprint asks the ideas page to say «почему именно этой паре», and the screen's own header
promises it: «под каждой указано, почему она подходит». The engine behind that header answered with
templates keyed on a single number instead. Measured on the working database before this change:
«Подходит вашему стилю досуга» was printed on 15 of the 16 cards two real pairs had, and it was the
only bullet on 7 of the 8 cards of one of them, while the city band and the goal band never spoke at
all. The sentence is not false for a pair that likes the idea — it is false for the half that does
not, and the score above it is the mean of two similarities, so it can pass 0.7 on one person who is
exactly this idea and one who is not.

The rule these checks encode:

* A band may name a trait only when every value behind the claim — both people and the idea —
  answers the same side of it, in the words `describe_side` already gives that side (stage 75
  removed a second rendering of the same answer).
* A value nobody gave stays silent, and the number it was neutralised into keeps its place.
* A fact about one half is not printed as a fact about the pair: an interest only one of the two
  chose moves the score at 0.4 weight, so the card that hides it is hiding arithmetic.
* One sentence per band, chosen deterministically, because the page is stored and re-read.

None of this touches the arithmetic. Three of the cases below pin the exact float the old engine
produced, which is how the change stays provably explanatory: the text moved, the number did not.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from app.compatibility.traits import TRAIT_CATEGORIES_BY_KEY, describe_side
from app.recommendations.engine import ActivitySignal, UserSignal, score_activity

LEISURE = {t.key: t for t in TRAIT_CATEGORIES_BY_KEY["leisure"].traits}
LIFESTYLE = {t.key: t for t in TRAIT_CATEGORIES_BY_KEY["lifestyle"].traits}

REMOVED_LEISURE_TEMPLATE = "Подходит вашему стилю досуга"


def _act(aid=1, interests=None, cities=None, energy=0.5, social=0.5) -> ActivitySignal:
    return ActivitySignal(
        activity_id=aid, slug=f"a{aid}", title=f"a{aid}", category="x",
        interests=interests or [], cities=cities or [], energy=energy, social=social,
    )


def _leisure_bullet(reasons: list[str]) -> str | None:
    named = [r for r in reasons if any(r.startswith(f"{t.label}: ") for t in LEISURE.values())]
    assert len(named) <= 1, f"a card may name one leisure axis, got {named}"
    return named[0] if named else None


def _split_pair() -> tuple[ActivitySignal, UserSignal, UserSignal]:
    """One half is the party this idea describes, the other is its opposite."""
    return (
        _act(1, ["dancing"], ["Казань"], energy=0.95, social=0.9),
        UserSignal(
            interests={"dancing"}, city="Казань", dating_goal="marriage",
            vector={"leisure": {"outdoor": 0.95, "social_leisure": 0.9, "relaxation": 0.5}},
        ),
        UserSignal(
            interests=set(), city="Казань", dating_goal="marriage",
            vector={"leisure": {"outdoor": 0.05, "social_leisure": 0.9, "relaxation": 0.5}},
        ),
    )


def _agreeing_pair() -> tuple[ActivitySignal, UserSignal, UserSignal]:
    return (
        _act(2, ["dancing", "music_live"], ["Казань"], energy=0.9, social=0.85),
        UserSignal(
            interests={"dancing"}, city="Казань", dating_goal="marriage",
            vector={
                "leisure": {"outdoor": 0.9, "social_leisure": 0.9, "relaxation": 0.1},
                "lifestyle": {
                    "health_focus": 0.9, "activity_level": 0.8,
                    "sleep_schedule": 0.8, "social_frequency": 0.9,
                },
            },
        ),
        UserSignal(
            interests={"dancing", "music_live"}, city="Казань", dating_goal="marriage",
            vector={
                "leisure": {"outdoor": 0.88, "social_leisure": 0.92, "relaxation": 0.12},
                "lifestyle": {
                    "health_focus": 0.86, "activity_level": 0.82,
                    "sleep_schedule": 0.78, "social_frequency": 0.88,
                },
            },
        ),
    )


def test_a_card_names_no_axis_the_two_halves_disagree_on():
    """The defect this stage closed, in one card: a number earned by one half, explained to both.

    Red before this change with `['Подходит вашему стилю досуга', ...]` in place of the social
    bullet — the mean of the two similarities passed 0.7 and the sentence claimed the taste of
    a person whose own answer is the opposite end of the axis.
    """
    act, a, b = _split_pair()
    scored = score_activity(act, a, b)

    assert scored.score == 0.625, "the arithmetic of this stage is off-limits, only the text moved"
    assert REMOVED_LEISURE_TEMPLATE not in scored.reasons
    assert _leisure_bullet(scored.reasons) == (
        "Социальный досуг: и вы, и идея — в больших компаниях"
    ), scored.reasons
    assert not any(r.startswith("Активный отдых:") for r in scored.reasons), (
        "the pair disagrees on `outdoor` (0.95 against 0.05), so the card may not call it theirs"
    )
    assert not any(r.startswith("Спокойный отдых:") for r in scored.reasons), (
        "one half answered 0.5, which names no side at all"
    )


def test_the_idea_of_a_split_pair_is_still_explained_by_what_the_pair_does_share():
    """The card is not left mute: the bands that can speak do, and each says a different fact.

    Pinned as the whole list on purpose — the one-sided interest, the agreed axis, the city and the
    goal are four separate bands, and a bullet missing from this list is a fact the pair paid for.
    """
    act, a, b = _split_pair()
    assert score_activity(act, a, b).reasons == [
        "Интерес одного из вас — dancing",
        "Социальный досуг: и вы, и идея — в больших компаниях",
        "Проходит в вашем городе",
        "Цель знакомства у вас одна",
    ]


def test_an_axis_the_pair_and_the_idea_agree_on_is_named_in_the_apps_own_words():
    """The other half of the rule: agreement earns the sentence, in `describe_side`'s wording.

    The word is read from `describe_side` rather than typed here, so a fifth screen quoting this
    band cannot drift from it, and a threshold moved in the taxonomy shows up as a failing check.
    """
    act, a, b = _agreeing_pair()
    scored = score_activity(act, a, b)
    trait = LEISURE["outdoor"]
    side = describe_side(a.vector["leisure"]["outdoor"], trait.low_label, trait.high_label)

    assert side == "на природе/активно"
    assert _leisure_bullet(scored.reasons) == f"{trait.label}: и вы, и идея — {side}"
    assert scored.score == 0.8709166666666667, "the same card at the same number, text only"


def test_the_axis_a_card_names_is_chosen_the_same_way_every_time_it_is_read():
    """Two axes are equally far from the middle here, so the tie needs a rule, not a hash order.

    `outdoor` and `relaxation` both answer 0.4 away from 0.5 on the idea, and the page is stored
    and re-read: a tie broken by iteration order would print a different reason for one card
    between two visits.
    """
    act, a, b = _agreeing_pair()
    first = score_activity(act, a, b).reasons
    second = score_activity(act, a, b).reasons

    assert first == second
    assert _leisure_bullet(first) is not None and "Активный отдых" in _leisure_bullet(first)
    assert "Спокойный отдых" not in " ".join(first), (
        "the tie must resolve on the axis key, and `outdoor` sorts before `relaxation`"
    )


def test_a_card_with_nothing_true_to_say_stays_silent_and_keeps_its_number():
    """The empty answer is the baseline every band above is measured against.

    No interests, no vectors, no city, no goal: five neutralised bands and one bullet-free card.
    Red before this change only in the sense that it could not be — but it pins the number,
    because a card that says nothing must still cost the pair the same points.
    """
    scored = score_activity(
        _act(3, ["reading"]),
        UserSignal(interests=set(), city="", dating_goal=""),
        UserSignal(interests=set(), city="", dating_goal=""),
    )
    assert scored.reasons == []
    assert scored.score == 0.37499999999999994


def test_an_interest_only_one_half_chose_is_not_printed_as_a_shared_one():
    """The score reads `shared_any` at 0.4, so a one-sided tag moved the number in silence.

    Red before this change: the card cost the pair those points and said either nothing about
    them or, worse, left the reader to guess the tag was shared. Whichever of the two it is stays
    unnamed on purpose — the page is one text for both halves, and a name would be a statement
    about one of them the other never asked for.
    """
    a = UserSignal(
        interests={"dancing"}, city="Казань", dating_goal="marriage",
        interest_titles={"dancing": "Танцы"},
    )
    b = UserSignal(interests=set(), city="Казань", dating_goal="marriage")
    reasons = score_activity(_act(1, ["dancing"]), a, b).reasons

    assert "Интерес одного из вас — Танцы" in reasons, reasons
    assert not any(r.startswith("Общий") for r in reasons), (
        f"nobody shares this tag: {reasons}"
    )


def test_a_shared_tag_and_a_one_sided_tag_are_told_apart_on_the_same_card():
    a = UserSignal(interests={"dancing", "music_live"}, city="", dating_goal="")
    b = UserSignal(interests={"dancing", "board_games"}, city="", dating_goal="")
    reasons = score_activity(_act(1, ["dancing", "music_live", "board_games"]), a, b).reasons

    assert "Общий интерес — dancing" in reasons, reasons
    assert "Интересы одного из вас — board_games, music_live" in reasons, reasons


def test_the_city_bullet_agrees_with_how_many_cities_the_pair_actually_has():
    """One sentence for two different facts was the other half of the borrowed explanation.

    Two people living in two of the listed places were told the idea runs «в вашем городе» — a
    city neither of them shares with the other — and a 0.4 half-match, where the idea is available
    to one of the two, printed nothing at all.
    """
    same = score_activity(
        _act(1, cities=["Казань"]),
        UserSignal(city="Казань"), UserSignal(city="Казань"),
    ).reasons
    both = score_activity(
        _act(1, cities=["Казань", "Новосибирск"]),
        UserSignal(city="Казань"), UserSignal(city="Новосибирск"),
    ).reasons
    one = score_activity(
        _act(1, cities=["Казань"]),
        UserSignal(city="Казань"), UserSignal(city="Новосибирск"),
    ).reasons
    unrestricted = score_activity(
        _act(1, cities=[]),
        UserSignal(city="Казань"), UserSignal(city="Казань"),
    ).reasons

    assert "Проходит в вашем городе" in same, same
    assert "Проходит в ваших городах" in both, both
    assert "Проходит в вашем городе" not in both
    assert "Проходит в городе одного из вас" in one, one
    assert not any("Проходит" in r for r in unrestricted), (
        f"an idea the catalogue places nowhere says nothing about the pair's city: {unrestricted}"
    )


@pytest.mark.parametrize(
    "goal_a, goal_b, expected",
    [
        pytest.param("marriage", "marriage", "Цель знакомства у вас одна", id="same goal"),
        pytest.param("marriage", "relationship", "Цели знакомства не расходятся", id="complementary"),
        pytest.param("relationship", "networking", None, id="conflicting"),
        pytest.param("", "relationship", None, id="one half answered nothing"),
        pytest.param("", "", None, id="neither answered"),
    ],
)
def test_the_goal_bullet_says_which_of_the_two_facts_the_number_holds(
    goal_a: str, goal_b: str, expected: str | None
):
    """1.0 and 0.85 used to print the same sentence.

    «Цели знакомства совпадают» was said to a pair where one half wants marriage and the other a
    relationship — a statement neither of them made. An unanswered goal stays silent and neutral,
    the rule stage 60 set for interests, so the card never charges a person for an answer nobody
    gave. The goal itself is not spelled out: the option words live on the client.
    """
    reasons = score_activity(
        _act(1),
        UserSignal(city="", dating_goal=goal_a),
        UserSignal(city="", dating_goal=goal_b),
    ).reasons
    goals = [r for r in reasons if "Цели" in r or "Цель" in r]

    assert goals == ([expected] if expected else []), reasons


def test_a_close_rhythm_names_the_axis_that_carried_it():
    """«У вас близкий ритм жизни» without a noun is a claim about four answers at once.

    The mean says the two rhythms are alike; it does not say which of them they agree on. Here the
    three closest axes tie, so the check pins the chosen one as well — the tie is the same rule the
    leisure band follows, and the reason the page reads the same twice.
    """
    act, a, b = _agreeing_pair()
    reasons = score_activity(act, a, b).reasons

    assert "Близкий ритм жизни: активность (высокая активность)" in reasons, reasons
    assert "У вас близкий ритм жизни" not in reasons


def test_a_close_rhythm_stays_plain_when_no_axis_lands_on_a_named_side():
    """The fallback has to stay reachable: four answers alike and in the middle are still alike.

    Both halves answered the exact centre of every lifestyle axis, so the mean is 1.0 and the band
    is earned, while no axis can be named — «умеренно» says which side nobody is on. The plain
    sentence is true about the rhythm as a whole, and it is the only thing this pair supports.
    """
    centre = {key: 0.5 for key in LIFESTYLE}
    reasons = score_activity(
        _act(1),
        UserSignal(vector={"lifestyle": dict(centre)}),
        UserSignal(vector={"lifestyle": dict(centre)}),
    ).reasons

    assert reasons == ["У вас близкий ритм жизни"], reasons


def test_a_distant_rhythm_is_not_called_close():
    reasons = score_activity(
        _act(1),
        UserSignal(vector={"lifestyle": {"activity_level": 1.0, "sleep_schedule": 1.0}}),
        UserSignal(vector={"lifestyle": {"activity_level": 0.0, "sleep_schedule": 0.0}}),
    ).reasons

    assert not any("ритм" in r for r in reasons), reasons


@pytest.mark.parametrize("energy", [0.05, 0.3, 0.5, 0.72, 0.98])
@pytest.mark.parametrize("outdoor_b", [0.02, 0.3, 0.5, 0.7, 0.99])
def test_no_bullet_ever_names_an_axis_the_data_does_not_place_on_a_side(energy: float, outdoor_b: float):
    """The general form of the rule, over a grid rather than over the cases above.

    For every card that prints a leisure axis, all three values behind the claim — the idea's own
    energy, the first half's answer and the second half's — have to answer `describe_side` with the
    word printed. A band that could speak on a mean alone would fail this on the first row.
    """
    act = _act(1, energy=energy, social=0.9)
    a = UserSignal(
        city="", dating_goal="",
        vector={"leisure": {"outdoor": energy, "social_leisure": 0.9, "relaxation": 1.0 - energy}},
    )
    b = UserSignal(
        city="", dating_goal="",
        vector={"leisure": {"outdoor": outdoor_b, "social_leisure": 0.9, "relaxation": 0.5}},
    )
    bullet = _leisure_bullet(score_activity(act, a, b).reasons)
    if bullet is None:
        return

    key = next(k for k, t in LEISURE.items() if bullet.startswith(f"{t.label}: "))
    trait = LEISURE[key]
    side = bullet.split(" — ", 1)[1]
    values = {
        "outdoor": (energy, a.vector["leisure"]["outdoor"], b.vector["leisure"]["outdoor"]),
        "social_leisure": (0.9, 0.9, 0.9),
        "relaxation": (1.0 - energy, 1.0 - energy, 0.5),
    }[key]
    for value in values:
        assert describe_side(value, trait.low_label, trait.high_label) == side, (
            f"{bullet} claims {trait.label} is yours as {side}, but {value} answers "
            f"{describe_side(value, trait.low_label, trait.high_label)}"
        )
    assert side != describe_side(0.5, trait.low_label, trait.high_label), (
        "the neutral answer names no side, so it may not be printed as one"
    )


_ROOT = pathlib.Path(__file__).resolve().parents[2]
_API_DOC = _ROOT / "docs" / "API.md"
_RECS_BLOCK = re.compile(r"`recommendations\[\]`:\s*```json\s*(.*?)```", re.DOTALL)
_SAMPLE_SCORE = re.compile(r'"score":\s*(\d+)')
_SAMPLE_REASONS = re.compile(r'"reasons":\s*\[(.*?)\]', re.DOTALL)
_SAMPLE_SIGNALS = re.compile(r'"energy":\s*([\d.]+),\s*"social":\s*([\d.]+)')
_QUOTED = re.compile(r'"([^"]+)"')


def test_the_api_document_samples_a_card_the_engine_prints() -> None:
    """A sample a fresh clone can only guess at is a second, untested rendering of the answer.

    The document prints one card of this page: its number, its four sentences and the two signals
    the score multiplies. This check rebuilds that card from the tags, cities and answers the sample
    stands on — `hiking` chosen by both halves, `camping` by one of them, both living in Москва,
    neither naming a goal, the leisure axis answered 0.9 and 0.8 — and requires the engine to answer
    with the printed text. A wording edited in the engine and left out of the document fails here,
    the way stage 75 pinned the map's own sample.
    """
    doc = _API_DOC.read_text(encoding="utf-8")
    block = _RECS_BLOCK.search(doc)
    assert block, "docs/API.md no longer samples recommendations[] with a json block"
    shown = block.group(1)
    score = _SAMPLE_SCORE.search(shown)
    reasons = _SAMPLE_REASONS.search(shown)
    signals = _SAMPLE_SIGNALS.search(shown)
    assert score and reasons and signals, f"the sample lost a field this check reads: {shown}"

    titles = {"hiking": "Походы", "camping": "Кемпинг"}
    act = ActivitySignal(
        activity_id=3, slug="forest_walk", title="…", category="…",
        interests=["hiking", "camping"], cities=["Москва"],
        energy=float(signals.group(1)), social=float(signals.group(2)),
    )
    a = UserSignal(
        interests={"hiking"}, city="Москва", interest_titles=dict(titles),
        vector={"leisure": {"outdoor": 0.9}},
    )
    b = UserSignal(
        interests={"hiking", "camping"}, city="Москва", interest_titles=dict(titles),
        vector={"leisure": {"outdoor": 0.8}},
    )
    scored = score_activity(act, a, b)

    assert _QUOTED.findall(reasons.group(1)) == scored.reasons, (
        f"the document shows {scored.reasons!r} as this page's answer, and the card says otherwise"
    )
    assert int(score.group(1)) == scored.percent, (
        f"the document prints {score.group(1)} for a card the engine scores {scored.percent}"
    )


_SCREEN = (
    pathlib.Path(__file__).resolve().parents[2]
    / "android" / "app" / "src" / "main" / "java" / "app" / "befos"
    / "presentation" / "recommendations" / "RecommendationsScreen.kt"
)


def test_the_screen_promises_only_what_the_engine_can_answer() -> None:
    """The header above the list is the user-facing half of this stage.

    It read «под каждой указано, почему она подходит» — a count of lines on every card, while the
    engine prints a bullet only where the pair's answers support one, and the check above keeps that
    empty list reachable. The sentence is the defect the sprint's own wording closes: an explanation
    promised for its own sake rather than for the data behind it.
    """
    text = _SCREEN.read_text(encoding="utf-8")
    # Only what the screen renders: the comment above the subtitle quotes the old sentence to
    # explain why it went, and a check over comments would fail on its own reasoning.
    body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))

    assert "под каждой" not in body, (
        "the ideas page promises a reason under every card again, and the engine cannot keep that"
    )
    assert "правда для вас двоих" in body, (
        "the header no longer says what the cards hold, so nothing on the page names the pair"
    )
