"""Database seeder.

Populates catalogues (interests, test questions, activities) and a realistic
demo dataset of users with profiles, test answers, compatibility vectors,
photos, likes, matches and messages.

Run:
    python -m app.seed            # seed only if the users table is empty
    python -m app.seed --force    # wipe domain data and reseed
    python -m app.seed --if-empty # explicit no-op when data exists (default)

All randomness uses a fixed seed, so the demo dataset is reproducible.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import uuid
from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compatibility.traits import TRAIT_CATEGORIES_BY_KEY
from app.compatibility.weights import ENGINE_VERSION
from app.core.config import settings
from app.core.database import AsyncSessionLocal, Base, engine
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models import (
    Activity,
    CompatibilityProfile,
    Interest,
    Like,
    Match,
    Message,
    MessageRead,
    Pass,
    Photo,
    Profile,
    TestAnswer,
    TestOption,
    TestQuestion,
    TestResult,
    User,
)
from app.seed_data.activities_catalog import ACTIVITIES
from app.seed_data.interests_catalog import INTERESTS
from app.seed_data.placeholder_images import generate_avatar
from app.seed_data.questions_catalog import QUESTIONS
from app.repositories.social_repo import ordered_pair

logger = get_logger(__name__)

RNG_SEED = 20240501

FEMALE_NAMES = ["Анна", "Мария", "Елена", "Ольга", "Дарья", "Полина", "Ксения", "Юлия", "Виктория", "София", "Алиса", "Марина", "Наталья", "Екатерина", "Вера"]
MALE_NAMES = ["Андрей", "Дмитрий", "Алексей", "Сергей", "Иван", "Максим", "Никита", "Артём", "Павел", "Роман", "Егор", "Михаил", "Кирилл", "Тимур", "Влад"]
CITIES = ["Москва", "Санкт-Петербург", "Казань", "Новосибирск", "Екатеринбург", "Нижний Новгород", "Сочи"]
GOALS = ["relationship", "marriage", "friendship", "casual", "networking"]
ABOUT = [
    "Люблю активный отдых и новые впечатления.",
    "Ценю глубокие разговоры и хорошую музыку.",
    "Ищу человека для совместных приключений.",
    "Увлекаюсь творчеством и саморазвитием.",
    "Предпочитаю спокойный отдых и уютные вечера.",
    "Спорт, путешествия и вкусная еда — моя жизнь.",
    "Открыт(а) к новому и честному общению.",
    "Обожаю кино, книги и долгие прогулки.",
]

ALL_TRAITS: list[tuple[str, str]] = [
    (cat.key, trait.key) for cat in TRAIT_CATEGORIES_BY_KEY.values() for trait in cat.traits
]


async def _table_empty(session: AsyncSession) -> bool:
    count = (await session.execute(select(func.count(User.id)))).scalar_one()
    return count == 0


async def _seed_catalogs(session: AsyncSession) -> dict:
    # Interests
    existing = {i.slug: i for i in (await session.execute(select(Interest))).scalars().all()}
    for slug, name, category in INTERESTS:
        if slug not in existing:
            interest = Interest(slug=slug, name=name, category=category)
            session.add(interest)
            existing[slug] = interest
    await session.flush()

    # Questions + options
    q_count = (await session.execute(select(func.count(TestQuestion.id)))).scalar_one()
    questions: list[TestQuestion] = []
    if q_count == 0:
        for position, (category, trait, text, options) in enumerate(QUESTIONS):
            q = TestQuestion(category=category, trait=trait, text=text, position=position, is_active=True)
            session.add(q)
            await session.flush()
            for opos, (otext, ovalue) in enumerate(options):
                session.add(TestOption(question_id=q.id, text=otext, value=ovalue, position=opos))
            questions.append(q)
        await session.flush()
    else:
        questions = list(
            (await session.execute(select(TestQuestion).order_by(TestQuestion.position))).scalars().all()
        )

    # Activities
    a_count = (await session.execute(select(func.count(Activity.id)))).scalar_one()
    if a_count == 0:
        for slug, title, desc, category, interests, cities, energy, social, cost in ACTIVITIES:
            session.add(
                Activity(
                    slug=slug, title=title, description=desc, category=category,
                    interests=interests, cities=cities, energy=energy, social=social, cost=cost,
                )
            )
        await session.flush()

    return {"interests": existing, "questions": questions}


def _latent_traits(rng: random.Random) -> dict[tuple[str, str], float]:
    """Generate a user's latent trait values in 0..1 with some correlation."""
    base = rng.random()
    traits: dict[tuple[str, str], float] = {}
    for cat, trait in ALL_TRAITS:
        value = base * 0.4 + rng.random() * 0.6
        traits[(cat, trait)] = max(0.0, min(1.0, value))
    return traits


def _vector_from_traits(traits: dict[tuple[str, str], float]) -> dict[str, dict[str, float]]:
    vector: dict[str, dict[str, float]] = {}
    for (cat, trait), value in traits.items():
        vector.setdefault(cat, {})[trait] = round(value, 4)
    return vector


async def _create_user(
    session: AsyncSession,
    rng: random.Random,
    *,
    email: str,
    password_hash: str,
    name: str,
    gender: str,
    city: str,
    birth_date: date,
    goal: str,
    interests_slugs: list[str],
    latent: dict[tuple[str, str], float],
    avatar_name: str,
) -> User:
    user = User(email=email, password_hash=password_hash, is_active=True, is_verified=True)
    session.add(user)
    await session.flush()

    age_min = max(18, birth_date.year + 18 - 60)
    profile = Profile(
        user_id=user.id,
        name=name,
        birth_date=birth_date,
        gender=gender,
        city=city,
        about=rng.choice(ABOUT),
        dating_goal=goal,
        age_min=18,
        age_max=60,
        gender_preference=[],
        lifestyle={},
        is_hidden=False,
    )
    session.add(profile)
    await session.flush()

    # Photo (generated placeholder)
    url = generate_avatar(name + email, avatar_name, name)
    session.add(Photo(user_id=user.id, url=url, is_primary=True, position=0))

    # Interests
    interest_objs = list((await session.execute(select(Interest).where(Interest.slug.in_(interests_slugs)))).scalars().all())
    for interest in interest_objs:
        session.add(_user_interest(profile.id, interest.id))

    await session.flush()

    # Test answers: choose the option closest to the latent trait value
    questions = list((await session.execute(select(TestQuestion))).scalars().all())
    options = list((await session.execute(select(TestOption))).scalars().all())
    opts_by_q: dict[int, list[TestOption]] = {}
    for opt in options:
        opts_by_q.setdefault(opt.question_id, []).append(opt)

    category_scores: dict[str, list[float]] = {}
    for q in questions:
        latent_value = latent.get((q.category, q.trait), 0.5)
        opts = opts_by_q.get(q.id, [])
        if not opts:
            continue
        chosen = min(opts, key=lambda o: abs(o.value - latent_value))
        session.add(TestAnswer(user_id=user.id, question_id=q.id, option_id=chosen.id))
        category_scores.setdefault(q.category, []).append(chosen.value)

    await session.flush()

    # Compatibility profile vector
    vector = _vector_from_traits(latent)
    session.add(CompatibilityProfile(user_id=user.id, vector=vector, version=ENGINE_VERSION))

    # Per-category aggregated results
    for category, values in category_scores.items():
        session.add(TestResult(user_id=user.id, category=category, score=sum(values) / len(values)))

    await session.flush()
    return user


def _user_interest(profile_id: uuid.UUID, interest_id: int):
    from app.models import UserInterest

    return UserInterest(profile_id=profile_id, interest_id=interest_id)


async def _clear_domain(session: AsyncSession) -> None:
    for model in (MessageRead, Message, Match, Pass, Like, TestAnswer, TestResult, CompatibilityProfile, Photo, Profile, User):
        await session.execute(delete(model))
    await session.flush()


async def run_seed(session: AsyncSession, *, force: bool = False) -> None:
    rng = random.Random(RNG_SEED)

    if force:
        logger.info("Force mode: clearing domain data")
        await _clear_domain(session)

    catalogs = await _seed_catalogs(session)
    interest_slugs = list(catalogs["interests"].keys())

    if not force and not await _table_empty(session):
        logger.info("Users already exist; skipping user seed (use --force to reseed).")
        await session.commit()
        return

    password_hash = hash_password("Password123!")

    created_users: list[User] = []
    created_latents: dict[uuid.UUID, dict] = {}

    # Demo user first (fully featured)
    demo_birth = date(1996, 5, 14)
    demo_latent = _latent_traits(rng)
    demo_interests = rng.sample(interest_slugs, 8)
    demo = await _create_user(
        session, rng,
        email=settings.demo_email,
        password_hash=hash_password(settings.demo_password),
        name="Андрей",
        gender="male",
        city="Москва",
        birth_date=demo_birth,
        goal="relationship",
        interests_slugs=demo_interests,
        latent=demo_latent,
        avatar_name="seed_demo.png",
    )
    created_users.append(demo)
    created_latents[demo.id] = demo_latent

    # 50 additional users
    total_users = 50
    for i in range(total_users):
        gender = "female" if i % 2 == 0 else "male"
        name = (FEMALE_NAMES if gender == "female" else MALE_NAMES)[i % 15]
        city = rng.choice(CITIES)
        birth = date(2000 - rng.randint(0, 12), rng.randint(1, 12), rng.randint(1, 28))
        goal = rng.choice(GOALS)
        interests = rng.sample(interest_slugs, rng.randint(4, 9))
        latent = _latent_traits(rng)
        email = f"user{i+1:02d}@befos.demo"
        user = await _create_user(
            session, rng,
            email=email,
            password_hash=password_hash,
            name=f"{name}",
            gender=gender,
            city=city,
            birth_date=birth,
            goal=goal,
            interests_slugs=interests,
            latent=latent,
            avatar_name=f"seed_{i+1:02d}.png",
        )
        created_users.append(user)
        created_latents[user.id] = latent

    await session.flush()

    # Likes + matches + messages for the demo user (for instant demonstration)
    others = [u for u in created_users if u.id != demo.id]
    demo_matches: list[Match] = []
    for target in others[:8]:
        session.add(Like(from_user_id=demo.id, to_user_id=target.id, compatibility_score=0.8))
        # First four like back -> mutual matches
    await session.flush()

    for target in others[:4]:
        session.add(Like(from_user_id=target.id, to_user_id=demo.id, compatibility_score=0.8))
        ua, ub = ordered_pair(demo.id, target.id)
        match = Match(user_a_id=ua, user_b_id=ub, compatibility_score=0.82)
        session.add(match)
        demo_matches.append(match)
    await session.flush()

    # Seed messages in demo matches
    sample_dialog = [
        ("Привет! Рад(а) знакомству 😊", True),
        ("Привет! Взаимно. Чем увлекаешься?", False),
        ("Люблю фотографию и прогулки по городу. А ты?", True),
        ("Тоже обожаю гулять! Может, как-нибудь устроим фотопрогулку?", False),
        ("Отличная идея! Давай обсудим детали.", True),
    ]
    now = date.today()
    for idx, match in enumerate(demo_matches):
        base_time = now - timedelta(days=idx)
        other_id = match.user_b_id if match.user_a_id == demo.id else match.user_a_id
        for m_i, (body, from_demo) in enumerate(sample_dialog):
            sender = demo.id if from_demo else other_id
            created = _make_message(match.id, sender, body, base_time, m_i)
            session.add(created)
            await session.flush()
            session.add(MessageRead(message_id=created.id, reader_id=sender, read_at=created.created_at))
    await session.flush()

    # A few likes/passes among other users for realistic discovery state
    for a in others[:20]:
        for b in others[:5]:
            if a.id != b.id and rng.random() < 0.15:
                session.add(Like(from_user_id=a.id, to_user_id=b.id, compatibility_score=round(rng.uniform(0.4, 0.9), 3)))
    await session.flush()

    await session.commit()
    logger.info(
        "Seed complete: users=%d, demo_matches=%d, interests=%d, questions=%d, activities=%d",
        len(created_users), len(demo_matches), len(interest_slugs), len(catalogs["questions"]), len(ACTIVITIES),
    )


def _make_message(match_id, sender_id, body, base_day, index) -> Message:
    from datetime import datetime, time as dtime, timezone

    ts = datetime.combine(base_day, dtime(12 + index, (index * 7) % 60), tzinfo=timezone.utc)
    return Message(match_id=match_id, sender_id=sender_id, body=body, created_at=ts, updated_at=ts)


async def _create_all_and_seed(force: bool) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        await run_seed(session, force=force)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the BeFoS database.")
    parser.add_argument("--force", action="store_true", help="Wipe domain data and reseed.")
    parser.add_argument("--if-empty", action="store_true", help="Seed only if empty (default).")
    args = parser.parse_args()
    asyncio.run(_create_all_and_seed(force=args.force))


if __name__ == "__main__":
    main()
