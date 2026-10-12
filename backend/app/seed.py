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
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compatibility.engine import CompatibilityInput, compute_compatibility
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
from app.models.base import utc_today
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
    "Горы лучше моря, палатка лучше отеля — но только если погода не подводит.",
    "Ценю разговоры, которые заканчиваются после полуночи, и музыку, которую слышишь впервые.",
    "Ищу того, кто согласен на спонтанную поездку в четверг и на спокойное воскресенье в декабре.",
    "Рисую по выходным, читаю в дороге, раз в месяц хожу на скалолазание и каждый раз удивляюсь, как люди это выдумали.",
    "Тихий вечер с книгой — не компромисс, а ровно то, чего я хочу.",
    "Готовлю лучше, чем ем: дома всегда есть чем угостить, если заглянешь.",
    "Честность экономит больше времени, чем вежливость.",
    "Кино, книги и прогулки без маршрута. Если совпадём — будет о чём помолчать.",
]

ALL_TRAITS: list[tuple[str, str]] = [
    (cat.key, trait.key) for cat in TRAIT_CATEGORIES_BY_KEY.values() for trait in cat.traits
]


async def _table_empty(session: AsyncSession) -> bool:
    count = (await session.execute(select(func.count(User.id)))).scalar_one()
    return count == 0


_INTEREST_FIELDS = ("name", "category")
# The columns the engine reads off an activity row, in the order ACTIVITIES lists them.
_ACTIVITY_FIELDS = ("title", "description", "category", "interests", "cities", "energy", "social", "cost")


def _row_drift(kind: str, row, spec: tuple, fields: tuple[str, ...]) -> list[str]:
    """Name every column where a stored reference row is not what the shipped catalogue says."""
    lines = []
    for index, field in enumerate(fields):
        stored = getattr(row, field)
        shipped = spec[1 + index]
        if stored != shipped:
            lines.append(
                f"{kind} {spec[0]} (id={row.id}) holds {field}={stored!r}, the catalogue ships {field}={shipped!r}"
            )
    return lines


def _extra_row(kind: str, row, shipped_slugs: set[str]) -> list[str]:
    """Name a row this database has and the catalogue no longer ships."""
    if row.slug in shipped_slugs:
        return []
    return [
        f"{kind} {row.slug} (id={row.id}): this database holds the row, the catalogue does not ship the slug. "
        "It is kept: dropping it would cascade into rows people already chose."
    ]


def _questionnaire_drift(
    by_position: dict[int, TestQuestion], options_by_question: dict[int, list[TestOption]]
) -> list[str]:
    """Compare the stored questionnaire to the catalogue, question by question.

    Nothing here rewrites: ``test_answers.option_id`` points at the option a person actually chose,
    so replacing its text or value would re-read years of answers as answers to a different
    question. That is why a questionnaire edit is reported instead of applied.
    """
    lines = []
    if len(by_position) != len(QUESTIONS):
        lines.append(
            f"questionnaire: this database holds {len(by_position)} questions, the catalogue ships {len(QUESTIONS)}"
        )
    for position, (category, trait, text, options) in enumerate(QUESTIONS):
        row = by_position.get(position)
        if row is None:
            lines.append(
                f"questionnaire position {position}: the catalogue ships {text!r}, this database has no question there"
            )
            continue
        if (row.category, row.trait, row.text) != (category, trait, text):
            lines.append(
                f"question (id={row.id}, position={position}) holds "
                f"category={row.category!r} trait={row.trait!r} text={row.text!r}, the catalogue ships "
                f"category={category!r} trait={trait!r} text={text!r}"
            )
        stored_options = [(o.text, o.value, o.position) for o in options_by_question.get(row.id, [])]
        shipped_options = [(otext, ovalue, opos) for opos, (otext, ovalue) in enumerate(options)]
        if stored_options != shipped_options:
            lines.append(
                f"options of question (id={row.id}, text={row.text!r}) holds {stored_options}, "
                f"the catalogue ships {shipped_options}"
            )
    for position in sorted(set(by_position) - set(range(len(QUESTIONS)))):
        row = by_position[position]
        lines.append(
            f"question (id={row.id}, position={position}, text={row.text!r}): "
            "this database holds it, the catalogue ships no question at that position"
        )
    return lines


def _report_drift(lines: list[str]) -> None:
    """Tell the operator what this database's reference rows are not, and why the run leaves them.

    The seed adds rows a database is missing and never rewrites one it already has: a retagged
    activity or a renamed interest may be that deployment's own editorial choice, which is the
    protection revision ``7c4f2a91be36`` keyed its UPDATEs on the shipped array for. So a catalogue
    edit reaches an existing database through a data migration, and a run that finds rows the
    catalogue no longer says simply says so — the container boots either way.
    """
    if not lines:
        return
    logger.warning(
        "Catalogue drift: %d reference row(s) in this database are not what the code ships. This "
        "run adds rows the database is missing and leaves rows it already has alone — a retagged "
        "activity or a renamed interest may be that deployment's own editorial choice, the same "
        "protection revision 7c4f2a91be36 keyed its UPDATEs on the shipped array for. Carrying a "
        "catalogue edit into an existing database is a data migration's job. What disagrees:\n  %s",
        len(lines),
        "\n  ".join(lines),
    )


async def _seed_catalogs(session: AsyncSession) -> dict:
    """Put the three reference catalogues on the stand and name what this database already holds
    differently."""
    shipped_interests = {slug for slug, _name, _category in INTERESTS}
    existing = {i.slug: i for i in (await session.execute(select(Interest))).scalars().all()}
    drift: list[str] = []
    for slug, name, category in INTERESTS:
        row = existing.get(slug)
        if row is None:
            interest = Interest(slug=slug, name=name, category=category)
            session.add(interest)
            existing[slug] = interest
        else:
            drift += _row_drift("interest", row, (slug, name, category), _INTEREST_FIELDS)
    for row in existing.values():
        drift += _extra_row("interest", row, shipped_interests)
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
        options_by_question: dict[int, list[TestOption]] = {}
        for option in (await session.execute(select(TestOption).order_by(TestOption.position))).scalars().all():
            options_by_question.setdefault(option.question_id, []).append(option)
        drift += _questionnaire_drift({q.position: q for q in questions}, options_by_question)

    # Activities. A card the database does not have yet is added — an empty slot costs the pair a
    # card the page could have offered, and adding a row takes nothing from anybody. A card it does
    # have is only ever named: see `_report_drift`.
    shipped_activities = {spec[0] for spec in ACTIVITIES}
    stored_activities = {a.slug: a for a in (await session.execute(select(Activity))).scalars().all()}
    for spec in ACTIVITIES:
        slug, title, desc, category, interests, cities, energy, social, cost = spec
        row = stored_activities.get(slug)
        if row is None:
            stored_activities[slug] = Activity(
                slug=slug, title=title, description=desc, category=category,
                interests=interests, cities=cities, energy=energy, social=social, cost=cost,
            )
            session.add(stored_activities[slug])
        else:
            drift += _row_drift("activity", row, spec, _ACTIVITY_FIELDS)
    for row in stored_activities.values():
        drift += _extra_row("activity", row, shipped_activities)
    await session.flush()

    _report_drift(drift)
    return {"interests": existing, "questions": questions, "drift": drift}


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
        onboarding_completed_at=datetime.now(timezone.utc),
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

    if not settings.demo_enabled:
        # This is the switch README.md and DEMO.md name. With it off the stand still gets the
        # reference catalogues the app cannot work without — interests, questions, activities —
        # and no invented people. The demo account's password is printed in this repository,
        # so seeding it into a real deployment is a shared credential, not a convenience.
        logger.info("DEMO_ENABLED=false: catalogues seeded, no demo accounts created")
        await session.commit()
        return

    if not force and not await _table_empty(session):
        logger.info("Users already exist; skipping user seed (use --force to reseed).")
        await session.commit()
        return

    password_hash = hash_password("Password123!")

    created_users: list[User] = []
    created_latents: dict[uuid.UUID, dict] = {}
    # What each seeded person looks like to the engine. A match row's percent is read back by
    # the match list, so a seeded pair has to carry the number the engine gives it, not a
    # round number someone typed here.
    created_inputs: dict[uuid.UUID, CompatibilityInput] = {}

    # Demo user first (fully featured)
    demo_birth = date(1996, 5, 14)
    demo_latent = _latent_traits(rng)
    demo_interests = rng.sample(interest_slugs, 8)
    demo = await _create_user(
        session, rng,
        email=settings.demo_email,
        password_hash=hash_password(settings.demo_password),
        name="Алекс",
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
    created_inputs[demo.id] = CompatibilityInput(
        vector=_vector_from_traits(demo_latent),
        interests=set(demo_interests),
        dating_goal="relationship",
    )

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
        created_inputs[user.id] = CompatibilityInput(
            vector=_vector_from_traits(latent),
            interests=set(interests),
            dating_goal=goal,
        )

    await session.flush()

    def pair_score(x: uuid.UUID, y: uuid.UUID) -> float:
        return compute_compatibility(created_inputs[x], created_inputs[y]).overall

    # Likes + matches + messages for the demo user (for instant demonstration)
    others = [u for u in created_users if u.id != demo.id]
    demo_matches: list[Match] = []
    for target in others[:8]:
        session.add(Like(from_user_id=demo.id, to_user_id=target.id,
                         compatibility_score=pair_score(demo.id, target.id)))
        # First four like back -> mutual matches
    await session.flush()

    for target in others[:4]:
        score = pair_score(demo.id, target.id)
        session.add(Like(from_user_id=target.id, to_user_id=demo.id, compatibility_score=score))
        ua, ub = ordered_pair(demo.id, target.id)
        match = Match(user_a_id=ua, user_b_id=ub, compatibility_score=score)
        session.add(match)
        demo_matches.append(match)
    await session.flush()

    # Seed messages in demo matches
    sample_dialog = [
        ("Привет! Здорово, что мы совпали 😊", True),
        ("Привет! Взаимно. Чем увлекаешься?", False),
        ("Люблю фотографию и прогулки по городу. А ты?", True),
        ("Тоже обожаю гулять! Может, как-нибудь устроим фотопрогулку?", False),
        ("Отличная идея! Давай обсудим детали.", True),
    ]
    now = utc_today()
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
                session.add(Like(from_user_id=a.id, to_user_id=b.id, compatibility_score=pair_score(a.id, b.id)))
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
