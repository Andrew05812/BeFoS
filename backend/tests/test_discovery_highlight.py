from __future__ import annotations

from types import SimpleNamespace

from app.services.discovery_service import _highlight


def _interest(slug: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(slug=slug, name=name)


def _result(top_percent: int = 0, top_label: str = "Ценности") -> SimpleNamespace:
    return SimpleNamespace(
        categories=[
            SimpleNamespace(key="values", label=top_label, percent=top_percent, weight=0.2),
            SimpleNamespace(key="goals", label="Цели знакомства", percent=10, weight=0.2),
        ]
    )


def _profile(city: str = "", interests: list[SimpleNamespace] | None = None) -> SimpleNamespace:
    return SimpleNamespace(city=city, interests=interests or [])


def test_two_shared_interests_lists_names():
    cand = _profile(interests=[_interest("running", "Бег"), _interest("cinema", "Кино"), _interest("cooking", "Готовка")])
    hl = _highlight(_profile(city="Москва"), cand, {"running", "cinema"}, _result())
    assert hl == "Общие интересы: Бег, Кино"


def test_one_shared_interest_uses_display_name():
    cand = _profile(interests=[_interest("running", "Бег")])
    hl = _highlight(_profile(), cand, {"running"}, _result())
    assert hl == "Вам обоим нравится «Бег»"


def test_same_city_when_no_shared_interests():
    cand = _profile(city=" санкт-петербург ")
    hl = _highlight(_profile(city="Санкт-Петербург"), cand, set(), _result())
    assert hl == "Из вашего города"


def test_top_category_when_city_differs():
    cand = _profile(city="Сочи")
    hl = _highlight(_profile(city="Казань"), cand, set(), _result(top_percent=78, top_label="Ценности"))
    assert hl == "Высокое совпадение: ценности — 78%"


def test_weak_categories_yield_no_highlight():
    cand = _profile(city="Сочи")
    assert _highlight(_profile(city="Казань"), cand, set(), _result(top_percent=69)) is None


def test_shared_interests_take_priority_over_city():
    cand = _profile(city="Москва", interests=[_interest("jazz", "Джаз"), _interest("art", "Арт")])
    hl = _highlight(_profile(city="Москва"), cand, {"jazz", "art"}, _result())
    assert hl.startswith("Общие интересы:")
