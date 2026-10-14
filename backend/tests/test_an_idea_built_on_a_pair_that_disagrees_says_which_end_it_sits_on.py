"""A card built on a pair that disagrees has to say which end of the disagreement it is on.

Stage 81 removed «Подходит вашему стилю досуга» from these cards: the leisure number is the mean of
two similarities, so it passed the old threshold on one half who is exactly this idea and one half
who is its opposite, and the sentence told the second half a taste it never answered. The removal
was right and left the card silent — measured on the pristine engine before this stage, a pair at
0.95 against 0.05 on `outdoor` and `social_leisure` got `score 0.5850000000000001` and `reasons []`:
no leisure bullet, no interest bullet, no city, no goal, an empty block under «ПОЧЕМУ ПОДХОДИТ».

Silence is the honest answer for an axis the data cannot name. It is not the honest answer here: the
pair holds two named, opposite answers, and the idea carries its own value on the same axis, so the
card can say in one sentence who it serves. And the mean is blind to that in a way worth pinning: the
three fixtures below answer 0.95, 0.5 and 0.05 on the idea's own energy and all three score the same
number, because the two similarities average back to the same figure whichever end the idea stands
on. Same number, three different cards for the pair in front of them.

The rule these checks encode:

* A difference is printed only between two named sides. An answer in the middle («умеренно») names
  no side, so it neither agrees nor disagrees with anything, and the card stays silent.
* The sentence quotes `describe_side`'s words and the idea's own distance from them. It never says
  which half of the pair sits where: one stored page is read by both, and a name would be a
  statement about one of them the other never asked for.
* Agreement about the idea still outranks a difference. A card the two halves share is explained by
  what they share.
* None of this touches the arithmetic. Every score below is the number the pristine engine produced
  for the same fixture.
"""
from __future__ import annotations

from app.compatibility.traits import TRAIT_CATEGORIES_BY_KEY, describe_side
from app.recommendations.engine import ActivitySignal, UserSignal, score_activity

LEISURE = {t.key: t for t in TRAIT_CATEGORIES_BY_KEY["leisure"].traits}

# The number the pristine engine answers for the single-axis fixtures this file pins it on. Captured
# before the change and repeated here on purpose: text moved, the score did not.
UNCHANGED_SCORE = 0.5850000000000001


def _act(energy: float, social: float = 0.5) -> ActivitySignal:
    return ActivitySignal(
        activity_id=1, slug="a1", title="a1", category="x",
        interests=[], cities=[], energy=energy, social=social,
    )


def _on_outdoor(energy: float) -> list[str]:
    """One axis only, so the sentence below cannot be about whichever axis the taxonomy lists first."""
    a = UserSignal(vector={"leisure": {"outdoor": 0.95}})
    b = UserSignal(vector={"leisure": {"outdoor": 0.05}})
    return score_activity(_act(energy), a, b).reasons


def _leisure_bullets(reasons: list[str]) -> list[str]:
    return [r for r in reasons if any(r.startswith(f"{t.label}: ") for t in LEISURE.values())]


def test_a_card_the_two_halves_cannot_share_says_so_instead_of_going_silent():
    """The defect in one fixture: a pair at opposite ends, a card that says nothing about it.

    Red before this stage as an empty list — the pristine engine answered `reasons []` for exactly
    these two answers and this idea, while the score above the block had already spent 0.2 of the
    card's weight on how well the idea fits each of them.
    """
    a = UserSignal(vector={"leisure": {"outdoor": 0.95, "social_leisure": 0.95}})
    b = UserSignal(vector={"leisure": {"outdoor": 0.05, "social_leisure": 0.05}})
    scored = score_activity(_act(0.95, 0.05), a, b)

    assert scored.score == UNCHANGED_SCORE, "the arithmetic of this stage is off-limits"
    assert _leisure_bullets(scored.reasons) == [
        "Активный отдых: вы на разных сторонах — «на природе/активно» против «дома», "
        "идея ближе к «на природе/активно»"
    ], scored.reasons


def test_the_sentence_names_both_sides_in_the_words_the_app_already_gives_them():
    """No second rendering of an answer: the two quoted words come from `describe_side`.

    A wording typed into this file would keep passing while the taxonomy renamed the side, and the
    card would then print a word nobody's answer maps to any more — the drift stage 75 removed for
    percents.
    """
    trait = LEISURE["outdoor"]
    high = describe_side(0.95, trait.low_label, trait.high_label)
    low = describe_side(0.05, trait.low_label, trait.high_label)

    assert high == "на природе/активно" and low == "дома"
    bullet = _leisure_bullets(_on_outdoor(0.95))[0]
    assert bullet == f"{trait.label}: вы на разных сторонах — «{high}» против «{low}», идея ближе к «{high}»"


def test_the_card_says_which_end_of_the_pair_it_sits_on():
    """Three ideas, three different answers for the same two people.

    The score is the mean of the two similarities and comes back identical here — 0.5850000000000001
    for all three, as the pristine engine gave it — which is precisely why the number alone could not
    tell the pair what the card is aimed at.
    """
    trait = LEISURE["outdoor"]
    high = trait.high_label
    low = trait.low_label
    prefix = f"{trait.label}: вы на разных сторонах — «{high}» против «{low}»"

    assert _leisure_bullets(_on_outdoor(0.95)) == [f"{prefix}, идея ближе к «{high}»"]
    assert _leisure_bullets(_on_outdoor(0.05)) == [f"{prefix}, идея ближе к «{low}»"]
    assert _leisure_bullets(_on_outdoor(0.5)) == [f"{prefix}, идея посередине между вами"]
    assert score_activity(_act(0.95), UserSignal(vector={"leisure": {"outdoor": 0.95}}),
                          UserSignal(vector={"leisure": {"outdoor": 0.05}})).score == UNCHANGED_SCORE


def test_an_answer_that_names_no_side_is_not_reported_as_a_difference():
    """«умеренно» is not the opposite of anything, so a middle answer keeps the card silent.

    0.95 against 0.5 is not two named sides, and the card would be inventing a disagreement out of
    somebody's refusal to lean. This is the same rule `_shared_side` applies to agreement, read from
    the other end.
    """
    a = UserSignal(vector={"leisure": {"outdoor": 0.95}})
    b = UserSignal(vector={"leisure": {"outdoor": 0.5}})

    assert _leisure_bullets(score_activity(_act(0.95), a, b).reasons) == []


def test_agreement_about_the_idea_still_outranks_a_difference_on_the_card():
    """One bullet per card, and the shared one wins: stage 81's rule, kept intact.

    The pair agrees with the idea on `social_leisure` and diverges on `outdoor`. The card is about
    something the two of them do share, and saying that is worth more here than listing the axis they
    do not.
    """
    a = UserSignal(vector={"leisure": {"outdoor": 0.95, "social_leisure": 0.9}})
    b = UserSignal(vector={"leisure": {"outdoor": 0.05, "social_leisure": 0.9}})
    reasons = score_activity(_act(0.95, social=0.9), a, b).reasons

    assert _leisure_bullets(reasons) == ["Социальный досуг: и вы, и идея — в больших компаниях"], reasons


def test_the_difference_names_no_half_of_the_pair():
    """Which of the two answers 0.95 is not on the card, and cannot be recovered from it.

    The page is stored once and rendered for both halves, so a sentence shaped as «вы активны, а
    партнёр — нет» would tell one of them a fact about the other that neither screen was asked to
    show. Swapping the two signals moves only the order of the quoted sides; the side the idea sits
    on stays the same word.
    """
    straight = _leisure_bullets(_on_outdoor(0.95))[0]
    swapped = _leisure_bullets(
        score_activity(
            _act(0.95),
            UserSignal(vector={"leisure": {"outdoor": 0.05}}),
            UserSignal(vector={"leisure": {"outdoor": 0.95}}),
        ).reasons
    )[0]

    for bullet in (straight, swapped):
        assert "партн" not in bullet and "одного из вас" not in bullet, bullet
        assert "«на природе/активно»" in bullet and "«дома»" in bullet, bullet
    assert straight.endswith("идея ближе к «на природе/активно»")
    assert swapped.endswith("идея ближе к «на природе/активно»")


def test_the_widest_divergence_of_the_axes_the_idea_speaks_on_is_the_one_printed():
    """Two axes, two distances, one bullet — and the choice has to be a rule, not a hash order.

    `outdoor` holds a 0.9-wide disagreement and `social_leisure` a 0.85-wide one, so the wider axis
    speaks; the same card read twice answers the same, because the page is stored and re-read.
    """
    a = UserSignal(vector={"leisure": {"outdoor": 0.95, "social_leisure": 0.9}})
    b = UserSignal(vector={"leisure": {"outdoor": 0.05, "social_leisure": 0.05}})
    act = _act(0.95, social=0.9)

    first = _leisure_bullets(score_activity(act, a, b).reasons)
    second = _leisure_bullets(score_activity(act, a, b).reasons)

    assert first == second, "the same card printed a different reason between two visits"
    assert len(first) == 1
    assert first[0].startswith("Активный отдых: "), first
    assert not first[0].startswith("Социальный досуг: ")
