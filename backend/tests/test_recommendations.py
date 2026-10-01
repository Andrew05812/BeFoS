from __future__ import annotations

from app.recommendations.engine import ActivitySignal, UserSignal, recommend, score_activity


def _act(aid: int, slug: str, interests: list[str], cities=None, energy=0.5, social=0.5) -> ActivitySignal:
    return ActivitySignal(
        activity_id=aid, slug=slug, title=slug, category="x",
        interests=interests, cities=cities or [], energy=energy, social=social,
    )


def test_shared_interests_boost_score():
    a = UserSignal(interests={"photography", "travel"}, city="Москва", dating_goal="relationship")
    b = UserSignal(interests={"photography", "travel"}, city="Москва", dating_goal="relationship")
    photo_walk = _act(1, "photo_walk", ["photography", "travel"])
    gym = _act(2, "gym", ["gym", "running"])
    s1 = score_activity(photo_walk, a, b)
    s2 = score_activity(gym, a, b)
    assert s1.score > s2.score
    assert any("фотограф" in r.lower() or "travel" in r.lower() or "интерес" in r.lower() for r in s1.reasons)


def test_city_specific_activity_scores_zero_when_no_overlap():
    a = UserSignal(interests={"coffee"}, city="Москва", dating_goal="relationship")
    b = UserSignal(interests={"coffee"}, city="Москва", dating_goal="relationship")
    far = _act(3, "ski", ["skiing"], cities=["Сочи"])
    local = _act(4, "cafe", ["coffee"], cities=["Москва"])
    assert score_activity(far, a, b).score < score_activity(local, a, b).score


def test_recommend_is_deterministic_and_sorted():
    a = UserSignal(interests={"photography", "coffee"}, city="Москва", dating_goal="relationship")
    b = UserSignal(interests={"photography", "coffee"}, city="Москва", dating_goal="relationship")
    acts = [
        _act(1, "photo_walk", ["photography", "travel"]),
        _act(2, "coffee_walk", ["coffee"]),
        _act(3, "gym", ["gym"]),
    ]
    r1 = recommend(acts, a, b, top_n=3)
    r2 = recommend(acts, a, b, top_n=3)
    assert [x.activity_id for x in r1] == [x.activity_id for x in r2]
    scores = [x.score for x in r1]
    assert scores == sorted(scores, reverse=True)


def test_scores_in_range():
    a = UserSignal(interests={"x"}, city="Казань", dating_goal="casual")
    b = UserSignal(interests={"y"}, city="Москва", dating_goal="marriage")
    acts = [_act(i, f"a{i}", ["x", "y", "z"], cities=["Москва"]) for i in range(5)]
    for s in recommend(acts, a, b, top_n=5):
        assert 0.0 <= s.score <= 1.0
        assert 0 <= s.percent <= 100


def test_top_n_limits_results():
    a = UserSignal(interests={"x"}, city="", dating_goal="relationship")
    b = UserSignal(interests={"x"}, city="", dating_goal="relationship")
    acts = [_act(i, f"a{i}", ["x"]) for i in range(10)]
    assert len(recommend(acts, a, b, top_n=3)) == 3
