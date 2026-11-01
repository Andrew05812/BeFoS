"""Ни одна сверенная полоса не теряет своё объяснение из-за обрезка списка.

Живой осмотр стадии 125 §9 снял экран пары, где все семь полос сравнены и каждая читается
100 %, а раздела «Почему вы подходите» не хватает строки «Ценности» — самой тяжёлой полосы
(важность 25 %). Раскрытая полоса при этом печатала «движок не назвал ни одной причины в этой
полосе — число есть, слов к нему нет». Так экран противоречил сам себе: процент полосы показан,
основание к ней отказано.

Причина в `_one_per_category(...)[:6]`: одна строка на полосу даёт не больше семи строк, а
срез отрезает восьмую… то есть ровно одну — и жертвой оказывается та полоса, чьё латинское
имя категории идёт послед среди равных по сходству. Порядок `(-score, category)` для пары,
где всё совпало, решает это по алфавиту, а не по смыслу.

Ряд называет право каждой сверенной полосы остаться в списке — и совпадений, и расхождений:
обрезать список можно по признаку, который читатель видит (полоса не сверена), но не молча.
"""

from __future__ import annotations

from app.compatibility.engine import CompatibilityInput, compute_compatibility
from app.compatibility.explanation import build_explanation
from app.compatibility.traits import TRAIT_CATEGORIES_BY_KEY
from app.compatibility.weights import DEFAULT_WEIGHTS

BANDS = set(DEFAULT_WEIGHTS)


def _vector(value: float) -> dict[str, dict[str, float]]:
    return {key: {trait.key: value for trait in cat.traits}
            for key, cat in TRAIT_CATEGORIES_BY_KEY.items()}


def _two_alike() -> tuple[CompatibilityInput, CompatibilityInput]:
    vector = _vector(0.8)
    one = CompatibilityInput(vector=vector, interests={"hiking", "cooking"},
                             dating_goal="relationship")
    other = CompatibilityInput(vector=dict(vector), interests={"hiking", "cooking"},
                               dating_goal="relationship")
    return one, other


def _two_apart() -> tuple[CompatibilityInput, CompatibilityInput]:
    one = CompatibilityInput(vector=_vector(1.0), interests={"hiking"},
                             dating_goal="relationship")
    other = CompatibilityInput(vector=_vector(0.0), interests={"astronomy"},
                               dating_goal="casual")
    return one, other


def test_a_pair_that_matches_on_every_band_is_told_so_about_every_band() -> None:
    one, other = _two_alike()
    result = compute_compatibility(one, other)
    assert result.bands_measured == 7, "стенд рядом: все семь полос должны быть сверены"
    names = build_explanation(one, other, result, {"hiking": "Хайкинг", "cooking": "Готовка"})
    missing = BANDS - {item.category for item in names.strengths}
    assert not missing, (
        f"полосы сверены и показаны процентом, но строки о себе не получили: {sorted(missing)}"
    )


def test_a_pair_that_parts_on_every_band_is_told_so_about_every_band() -> None:
    one, other = _two_apart()
    result = compute_compatibility(one, other)
    assert result.bands_measured == 7, "стенд рядом: все семь полос должны быть сверены"
    names = build_explanation(one, other, result, {})
    parted = {c.key for c in result.categories if c.score < 0.75}
    assert parted == BANDS, f"стенд рядом: разошлись не все полосы, а {sorted(parted)}"
    missing = parted - {item.category for item in names.differences}
    assert not missing, (
        f"расхождение измерено и названо на полосе, но в списке его нет: {sorted(missing)}"
    )


def test_a_category_still_contributes_at_most_one_line() -> None:
    # Срез был не единственным стражем: полоса несёт несколько трейтов, и без `_one_per_category`
    # «Досуг» повторился бы в списке трижды.
    one, other = _two_alike()
    result = compute_compatibility(one, other)
    names = build_explanation(one, other, result, {})
    keys = [item.category for item in names.strengths]
    assert len(keys) == len(set(keys)), keys
