from __future__ import annotations

"""Activity catalogue for the Recommendation Engine.

Each activity references interest slugs (matched against user interests) and
carries energy/social/cost signals (0..1) used for leisure & lifestyle scoring.
An empty ``cities`` list means the activity is available anywhere.

Every tag here has to be a slug from ``interests_catalog`` — a thing a person can actually pick in
the UI — because the engine divides the pair's coverage by this list's own length
(``len(act_set)`` in ``app/recommendations/engine.py``). A tag nobody can select is a ceiling no
pair can reach: it lowers the activity for everybody and can never be raised by anybody.
``nature``, ``food`` and ``art`` are names of the groups the interest catalogue sorts its 40 slugs
into, not slugs; they are also not the activity's own ``category``, which is a different column and
enters no score.
``backend/tests/test_an_activity_tag_nobody_can_select_caps_the_score.py`` keeps it that way.
"""

# (slug, title, description, category, interests, cities, energy, social, cost)
ActivitySpec = tuple[str, str, str, str, list[str], list[str], float, float, float]

ACTIVITIES: list[ActivitySpec] = [
    ("photo_walk", "Фотопрогулка", "Прогулка по городу с камерой в поисках удачных кадров.",
     "creative", ["photography", "city_walks", "travel"], [], 0.4, 0.5, 0.1),
    ("coffee_walk", "Кофе + прогулка", "Неспешная прогулка с кофе и разговором.",
     "social", ["coffee", "city_walks"], [], 0.3, 0.6, 0.2),
    ("art_exhibition", "Выставка современного искусства", "Совместный поход на выставку с обсуждением.",
     "culture", ["painting", "design", "theatre"], [], 0.3, 0.5, 0.3),
    ("cinema", "Поход в кино", "Новинка на большом экране и обсуждение после.",
     "entertainment", ["cinema"], [], 0.2, 0.5, 0.3),
    ("board_games", "Вечер настольных игр", "Настолки в уютной компании.",
     "games", ["board_games", "gaming"], [], 0.3, 0.7, 0.2),
    ("workout_together", "Совместная тренировка", "Тренировка в зале или на улице.",
     "sport", ["gym", "running", "yoga", "football"], [], 0.9, 0.5, 0.2),
    ("hiking_trip", "Поход выходного дня", "Выезд на природу с маршрутом.",
     "nature", ["hiking", "camping"], [], 0.9, 0.6, 0.3),
    ("cooking_class", "Кулинарный мастер-класс", "Готовим новое блюдо вместе.",
     "food", ["cooking", "wine_tasting"], [], 0.4, 0.6, 0.5),
    ("live_music", "Концерт живой музыки", "Вечер живой музыки.",
     "music", ["music_live", "guitar", "electronic_music", "dancing"], [], 0.6, 0.8, 0.5),
    ("cafe_talk", "Разговор в уютной кофейне", "Долгий разговор за чашкой кофе.",
     "social", ["coffee", "reading"], [], 0.2, 0.4, 0.2),
    ("book_club", "Литературный вечер", "Обсуждение книг и идей.",
     "learning", ["reading", "science", "languages"], [], 0.2, 0.5, 0.1),
    ("bike_ride", "Велопрогулка", "Поездка на велосипедах по городу или парку.",
     "sport", ["cycling", "running"], [], 0.8, 0.5, 0.2),
    ("quest_room", "Квест-комната", "Совместное решение головоломок на время.",
     "games", ["gaming", "board_games", "science"], [], 0.5, 0.8, 0.4),
    ("picnic", "Пикник в парке", "Отдых на природе с едой и играми.",
     "nature", ["dogs", "cats", "city_walks"], [], 0.4, 0.6, 0.2),
    ("theatre_night", "Вечер в театре", "Спектакль и обсуждение за ужином.",
     "culture", ["theatre", "cinema", "design"], [], 0.3, 0.5, 0.6),
    ("dance_class", "Мастер-класс по танцам", "Парные танцы для начинающих.",
     "sport", ["dancing", "music_live"], [], 0.7, 0.7, 0.4),
    ("volunteering", "Волонтёрская акция", "Совместное доброе дело.",
     "social", ["volunteering"], [], 0.6, 0.7, 0.0),
    ("startup_meetup", "Стартап-митап", "Нетворкинг и идеи для амбициозных.",
     "learning", ["startups", "programming", "ai_ml", "networking"], [], 0.4, 0.8, 0.2),
    ("spa_day", "СПА-день", "Расслабление и забота о себе вдвоём.",
     "relax", ["yoga", "meditation"], [], 0.2, 0.4, 0.7),
    ("road_trip", "Автопутешествие на день", "Поездка в новое место на машине.",
     "travel", ["travel", "road_trips", "photography"], [], 0.7, 0.5, 0.5),
    ("food_market", "Прогулка по фуд-маркету", "Дегустация уличной еды и кофе.",
     "food", ["coffee", "cooking"], [], 0.4, 0.7, 0.3),
    ("meditation_session", "Совместная медитация", "Практика осознанности и расслабления.",
     "relax", ["meditation", "yoga"], [], 0.1, 0.3, 0.1),
    ("ski_day", "Горнолыжный день", "Активный день на склоне.",
     "sport", ["skiing", "running"], [], 0.95, 0.6, 0.7),
    ("language_exchange", "Языковой обмен", "Практика языка за разговором.",
     "learning", ["languages", "travel", "reading"], [], 0.3, 0.6, 0.1),
    ("dog_walk", "Прогулка с собакой", "Совместная прогулка с питомцами.",
     "nature", ["dogs", "city_walks"], [], 0.4, 0.5, 0.0),
]
