# База данных BeFoS

PostgreSQL 16, SQLAlchemy 2.0 (async) + asyncpg. Миграции — Alembic (`backend/alembic/versions/`). Первичная миграция `03f0ea587029_initial_schema` создаёт 21 таблицу, `4f2a1c9d7b30_discovery_deck_and_indexes` добавляет колоду подбора и индексы, нужные горячим чтением.

Все таблицы наследуют `TimestampMixin` (`created_at`, `updated_at`), кроме чисто справочных. Первичные ключи пользователей и связанных сущностей — `UUID`; справочники — `INTEGER` (autoincrement). Внешние ключи на `users.id` используют `ON DELETE CASCADE`.

## Диаграмма связей (обзор)

```
users ─1:1─ profiles ─M:N─ interests   (через user_interests)
  │            └─1:N─ photos
  ├─1:N─ refresh_tokens
  ├─1:N─ test_answers ─N:1─ test_questions ─1:N─ test_options
  ├─1:N─ test_results
  ├─1:1─ compatibility_profiles
  ├─M:N─ likes / passes (from_user, to_user)
  ├─M:N─ discovery_queue (viewer, candidate — колода подбора)
  ├─M:N─ matches (user_a, user_b) ─1:N─ messages ─1:N─ message_reads
  ├─M:N─ blocks / reports
  └─1:N─ activity_preferences ─N:1─ activities ─M:N─ recommendations (per match)
```

## Пользователи и профиль

### `users`
| Колонка | Тип | Примечание |
|---------|-----|-----------|
| id | UUID PK | |
| email | String(255) | unique, index |
| password_hash | String(255) | bcrypt |
| is_active | Boolean | default true |
| is_verified | Boolean | default false |
| is_deleted | Boolean | мягкое удаление |
| deleted_at | timestamptz | nullable |

### `profiles` (1:1 с `users`)
`user_id` (FK users, unique, cascade), `name` (String 80), `birth_date` (Date), `gender` (String 20), `city` (String 120), `about` (Text, null), `dating_goal` (String), `age_min`/`age_max` (Integer, 18/60), `gender_preference` (JSON массив), `city_preference` (String, null), `lifestyle` (JSONB, default `{}`), `is_hidden` (Boolean). Индекс `ix_profiles_city_lower_birth (lower(city), birth_date)` — подбор фильтрует город без учёта регистра и возраст диапазоном, три обычных индекса по `city`/`dating_goal` (были в первой миграции) этому чтению не служили и удалены в `4f2a1c9d7b30`.

### `photos`
`user_id` (FK, cascade, index), `url` (String 500), `is_primary` (Boolean), `position` (Integer).

### `interests` / `user_interests`
`interests`: `id` (Int PK), `slug` (String 80, unique), `name`, `category` (index). Связь M:N через `user_interests` (`profile_id` + `interest_id`, составной PK, `uq_user_interest`).

## Тест и профиль совместимости

### `test_questions`
`id` (Int PK), `category` (index), `trait`, `text`, `position`, `is_active`. Индекс `ix_question_category_position (category, position)`.

### `test_options`
`id` (Int PK), `question_id` (FK, cascade, index), `text`, `value` (Float — вклад варианта в признак), `position`.

### `test_answers`
`id` (UUID PK), `user_id` (FK, cascade), `question_id` (FK), `option_id` (FK). Ограничение `uq_user_question_answer (user_id, question_id)` — один ответ на вопрос; индекс `ix_answer_user_question`.

### `test_results`
`id` (UUID PK), `user_id` (FK, cascade), `category` (String 40), `score` (Float). `uq_user_category_result (user_id, category)` — агрегированная оценка по категории.

### `compatibility_profiles` (1:1 с `users`)
`user_id` (FK, unique, cascade), `vector` (JSONB — нормированные компоненты для движка), `version` (Integer, default 1 = `ENGINE_VERSION`).

## Социальный граф

### `likes`
`from_user_id`, `to_user_id` (FK users, cascade, index), `compatibility_score` (Float, null). `uq_like_pair (from_user_id, to_user_id)`.

### `passes`
Аналогично `likes`, `uq_pass_pair`. Используется, чтобы не показывать пропущенных повторно.

### `matches`
`user_a_id`, `user_b_id` (FK users, cascade, index), `compatibility_score` (Float, default 0). `uq_match_pair (user_a_id, user_b_id)`. Создаётся при взаимном лайке.

### `blocks`
`blocker_id`, `blocked_id` (FK, cascade), `uq_block_pair`. Скрывает пару из подбора.

### `reports`
`reporter_id`, `reported_id` (FK, cascade), `reason` (String 80), `details` (Text, null), `status` (String). `uq_report (reporter_id, reported_id, reason)`.

## Чат

### `messages`
`id` (UUID PK), `match_id` (FK matches, cascade, index), `sender_id` (FK users, cascade, index), `body` (Text), `is_deleted` (Boolean). Индекс `ix_message_match_created (match_id, created_at)` — для пагинации истории.

### `message_reads`
`id` (UUID PK), `message_id` (FK messages, cascade), `reader_id` (FK users, cascade), `read_at` (timestamptz). `uq_message_read (message_id, reader_id)`. Индекс `ix_message_reads_reader_message (reader_id, message_id)` — счётчик непрочитанных фильтрует `reader_id` один, а ни один ключ этой таблицы с него не начинался. Непрочитанные = сообщения другого отправителя без записи о прочтении читателем.

## Подбор

### `discovery_queue`
`viewer_id` + `candidate_id` (составной PK, оба FK users с CASCADE), `rank` (Integer — порядок в колоде, назначается один раз при постановке и не переставляется), `score` (Integer — совместимость на момент постановки), `status` (`ready` | `seen`, CheckConstraint), `queued_at`, `seen_at`. Индекс `ix_discovery_queue_viewer_status_rank (viewer_id, status, rank)`.

Строки `seen` — это память о том, что карточку уже показывали: они переживают перестройку колоды, поэтому человек не показывается вторично после like/pass. `rank` служит курсором API (`GET /discover?cursor=`), поэтому страница не сдвигается под тем, кто успел свайпнуть между запросами.

## Рекомендации

### `activities`
Каталог активностей: `id` (Int PK), `slug`, `title`, `description`, `category`, `energy`/`social`/`cost` (Float 0..1) — сигналы для детерминированной оценки.

### `activity_preferences`
`user_id` (FK, cascade), `activity_id` (FK, cascade), `uq_activity_pref`. Явные предпочтения пользователя.

### `recommendations`
`id` (UUID PK), `match_id` (FK matches, cascade, index), `activity_id` (FK activities, cascade), `score` (Float, default 0), `explanation` (JSONB — структурированные причины `{"positive": [...], "context": [...]}`), `position` (Integer). `uq_match_activity_rec (match_id, activity_id)`; индекс `ix_rec_match_position (match_id, position)`. Выбор пользователем активности (`POST /matches/{id}/recommendations/{activity_id}/select`) сохраняется в `activity_preferences`.

## Токены

### `refresh_tokens`
`id` (UUID PK), `user_id` (FK, cascade, index), `token_hash` (String 64, unique — SHA-256 от refresh-токена), `expires_at` (timestamptz), `revoked` (Boolean), `revoked_at`, `user_agent` (String, null). Refresh-токены ротируются: при обновлении старый отзывается.

## Пул и что он не покрывает

`app/core/database.py`: `pool_size=10`, `max_overflow=20` (до 30 соединений на процесс),
`pool_pre_ping=True`, `pool_recycle=1800`. При `max_connections=100` это практически три
реплики backend; при четвёртой refused connection появится под нагрузкой, а не при старте.

Остаток, который pre-ping не ловит, измерен после `pg_terminate_backend`: если сервер
закрыл соединение в тот момент, когда пул уже его отдаёт, asyncpg поднимает
`InternalClientError` — это не DBAPI-ошибка, и pre-ping не может классифицировать её как
разрыв. Из трёх подряд выдач одна поднимала ошибку, две следующие нет; пул выбрасывает
отравленное соединение сам. Поэтому `get_session` берёт соединение явно, до хэндлера, и
повторяет попытку один раз; если не вышло и дважды — 503 `database_unavailable` вместо 500
с текстом драйвера. Покрыто набором `backend/tests/test_db_reliability.py` (7 тестов:
честная проба, отсутствие утечки DSN, настройки пула, реальная потеря соединения и
восстановление, 503 на dependency-пути).

Проверка соответствия моделей и схемы — `alembic check`, сейчас чистый. `discovery_queue`
и `user_interests` объявлены через `PrimaryKeyConstraint` с именами `uq_*`, а не через
отдельный `UniqueConstraint` на тех же колонках: Postgres повышал уникальный индекс до
первичного ключа, и вторая формулировка навечно оставляла `alembic check` в состоянии
«есть drift». Имена этих двух ограничений при этом обязаны остаться — на них ссылается
`ON CONFLICT (constraint ...)` в `social_repo` и `user_repo`.

## Миграции и сид

- **Миграции:** `alembic upgrade head` (применяется автоматически в docker-compose при старте backend).
- **Сид:** `python -m app.seed [--if-empty]`. Идемпотентно создаёт справочники (`interests`, `activities`, `test_questions`/`test_options`), затем демо-домен: 1 демо-пользователь (`demo@befos.app` / `Demo12345`), 50 пользователей и 4 демо-матча. `RNG_SEED=20240501` — детерминированная генерация. Функции `_seed_catalogs`, `_clear_domain`, `run_seed` переиспользуются и в тестах.
- **Копия, восстановление и откат** — в [`docs/OPERATIONS.md`](OPERATIONS.md): что именно копируется (и почему том Docker копией не является), как drill проверяет копию отпечатком `backend/ops/backup_fingerprint.sql`, и в каком порядке ставятся миграции релиза.
