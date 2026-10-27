"""Семь весов полос — то, что выбрал продукт, а не то, что дало красивую цифру.

Стадия 125 §5 требует сверить веса до того, как экранов станет больше: движок складывает
полосы в итог именно этими долями, и правка любой из них меняет число у пары молча, без
ошибки и без красного теста. Сейчас суммы весов касалась только проверка `WeightConfig.validate`
— она сторожит равенство единице и не замечает, если «Личность» переставили с 0.15 на 0.20
заодно с остальными. Этот ряд называет каждую долю по имени, чтобы перестановка веса стала
решением, которое кто-то вынес явно, а не строчкой в диффе.

Значения сверены с `app/compatibility/weights.py` в этом же дереве и с порядком полос в
`traits.ALL_CATEGORIES`: ровно семь полос, ни одной лишней.
"""

from __future__ import annotations

from app.compatibility.traits import ALL_CATEGORIES
from app.compatibility.weights import DEFAULT_WEIGHTS

EXPECTED = {
    "values": 0.25,
    "personality": 0.15,
    "interests": 0.15,
    "communication": 0.15,
    "lifestyle": 0.15,
    "leisure": 0.10,
    "goals": 0.05,
}


def test_the_default_weights_are_the_seven_shares_the_product_chose() -> None:
    assert DEFAULT_WEIGHTS == EXPECTED


def test_no_band_gained_or_lost_a_place_in_the_scale() -> None:
    assert {c.key for c in ALL_CATEGORIES} == set(DEFAULT_WEIGHTS), (
        "полоса появилась или ушла из весов, а экран совместимости читает их семь"
    )


def test_the_shares_still_add_up_to_the_whole_score() -> None:
    assert round(sum(DEFAULT_WEIGHTS.values()), 6) == 1.0
