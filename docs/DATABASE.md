# База данных BeFoS

PostgreSQL 16, SQLAlchemy 2.0 (async) + asyncpg. Миграции — Alembic (`backend/alembic/versions/`). Первичная миграция `03f0ea587029_initial_schema` создаёт 21 таблицу, `4f2a1c9d7b30_discovery_deck_and_indexes` добавляет колоду подбора и индексы, нужные горячим чтением, `9c1f5b7d2a40_message_idempotency_key` — ключ повторяемости отправки в `messages`, `b7e3d0a9c421_onboarding_completed_at` — отметку законченного онбординга в `profiles`, `c5a7d1e0b342_unique_deck_rank_per_viewer` — уникальный индекс `(viewer_id, rank)`, `d8f4b2c6a157_index_email_lookup_a_sign_in_actually_uses` — функциональный индекс `lower(email)`, а `e6b28c4a13d0_indexes_that_only_cost_writes` снимает 15 индексов, которые были левым префиксом другого ключа и чтению не служили (head на 2026-10-07, `alembic check` чист).

Все таблицы наследуют `TimestampMixin` (`created_at`, `updated_at`), кроме чисто справочных. Первичные ключи пользователей и связанных сущностей — `UUID`; справочники — `INTEGER` (autoincrement). Внешние ключи на `users.id` используют `ON DELETE CASCADE`.

После `e6b28c4a13d0` в схеме 23 таблицы и 62 индекса. Одиночный индекс по внешней колонке здесь
есть там, где с этой колонки не начинается более длинный ключ: свайп — это `INSERT` в `passes`, и
каждый лишний btree на этой таблице оплачивается при каждом свайпе. Замерено: 100 000 строк
входят в `passes` за 4 047 мс с префиксным индексом и за 3 514 мс без него, в `messages` — 4 234
против 3 518 мс. План, числа и SQL эксперимента — в [`docs/SCALE_PLAN.md`](SCALE_PLAN.md).

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
| email | String(255) | unique, index — и отдельно уникальный функциональный индекс `uq_users_email_lower (lower(email))` |
| password_hash | String(255) | bcrypt |
| is_active | Boolean | default true |
| is_verified | Boolean | default false |
| is_deleted | Boolean | мягкое удаление |
| deleted_at | timestamptz | nullable |

Вход ищет адрес как `lower(users.email) = :email_lower`, и обычный уникальный индекс по
колонке такому предикату не служил: `EXPLAIN` на рабочей базе показывал `Seq Scan on users` —
то есть каждый вход и каждая регистрация перебирали таблицу целиком. `uq_users_email_lower`
закрывает и чтение, и более раннюю дырку: `uq_users_email` различает регистр, поэтому
`ana@example.com` и `Ana@example.com` были двумя аккаунтами с одной почтой. Сервис
регистрации пишет адрес в нижнем регистре с первой же коммита бэкенда, но это защита уровня
кода, а не схемы: строка, записанная в `users` в обход `auth_service` (прямая вставка, перенос
данных, будущий импорт), создавала второй аккаунт на чужой адрес, и база бы этого не заметила.
Поэтому миграция `d8f4b2c6a157` сначала приводит существующие адреса к нижнему регистру
(`UPDATE ... SET email = lower(email)`), и если в базе уже лежат два адреса, отличающихся
только регистром, этот шаг падает вместо того, чтобы выбрать победителя молча; после него
индекс создаётся как уникальный. Покрыто набором `backend/tests/test_db_reliability.py`
(план чтения под `enable_seqscan=off`, попытка вставить ту же почту в другом регистре, и
201 → 409 на второй регистрации).

### `profiles` (1:1 с `users`)
`user_id` (FK users, unique, cascade), `name` (String 80), `birth_date` (Date), `gender` (String 20), `city` (String 120), `about` (Text, null), `dating_goal` (String), `age_min`/`age_max` (Integer, 18/60), `gender_preference` (`ARRAY(String(20))` — массив, не JSON: пустой список сюда пишется как `'{}'::varchar[]`, и `[]'::jsonb` — это ошибка типа, а не тихая подмена), `city_preference` (String, null), `lifestyle` (JSONB, default `{}`), `is_hidden` (Boolean), `onboarding_completed_at` (timestamptz, null).

`city_preference` — зарезервированная колонка, а не работающая функция: ни один эндпоинт и
ни один экран её не пишет, и `discovery_service` передаёт в фильтр
`viewer_profile.city_preference or None`. `_preference_conditions` добавляет условие по
городу только когда город непустой, поэтому запрос, пришедший из API, ветку `lower(city)`
не содержит вообще.

`ix_profiles_city_lower_birth (lower(city), birth_date)` появился в `4f2a1c9d7b30` вместо трёх
обычных индексов по `city` и `dating_goal`, которые чтению кандидатов служили хуже. Честное
состояние по замеру 2026-10-06 на рабочей базе (264 профиля):

- форма с городом (`lower(p.city) = 'москва'` и диапазон по `birth_date`) — `Bitmap Index Scan
  on ix_profiles_city_lower_birth`, выполнение 0.323 мс. Эта форма написана руками и из API
  недостижима.
- форма, которую реально шлёт API (только диапазон возрастов, город `NULL`): `Seq Scan on
  profiles p`, выполнение 0.673 мс. Без ведущей колонки `lower(city)` индекс остаётся
  пригодным — Postgres читает его целиком и фильтрует по второй колонке, и под
  `enable_seqscan=off` он так и делает, — но на 264 строках выигрыша нет, и planner это
  считает правильно. Город в это чтение не попадает ни с одним запросом из API, поэтому
  ведущая колонка индекса сегодня не связана ни одним предикатом, который продукт умеет
  отправить.

Индекс оставлен, потому что колонка, фильтр и индекс — одна форма, и удаление любой из трёх
частей оставило бы две ссылаться на пустое место; как только предпочтение города станет
функцией, готовому индексу найдётся работа. Сегодня же ни один запрос из API не связывает его
ведущую колонку, и ни одна цифра в документации не должна выглядеть так, будто этот индекс
что-то экономит.

`onboarding_completed_at` (`b7e3d0a9c421`) ставится один раз онбордингом. Регистрация оставляет
оболочку — имя из адреса, дата-заглушка, `lifestyle` пустой; оболочка не согласие быть
показанной, поэтому колода требует эту отметку (`social_repo._candidate_conditions`), а не
угадывает готовность анкеты по заполненным полям. Без неё новый пользователь попадал в чужие
ленты, а процент совместимости считывался с профиля, в котором не было ни одного ответа.

`birth_date`, `gender` и `dating_goal` — NOT NULL, поэтому удаление аккаунта не может оставить
в них NULL и пишет значения, которые не могут прийти с формы: `date '1900-01-01'`,
`'erased'`, `'erased'` (`safety_service.ERASED_*`). Строка при этом остаётся — удаление
мягкое, `ON DELETE CASCADE` в схеме не срабатывает никогда, и всё, что стирается, перечислено
кодом (`docs/OPERATIONS.md` §13, включая одноразовый backfill `backend/ops/anonymize_deleted_users.sql`).

### `photos`
`user_id` (FK, cascade, index), `url` (String 500), `is_primary` (Boolean), `position` (Integer).

Чтётся всегда в одном порядке — `PHOTO_DISPLAY_ORDER` в `app/models/user.py`
(`is_primary DESC, position ASC, created_at ASC, id ASC`), его импортируют все семь мест
чтения (профиль, публичная анкета, подбор, колода, основные фото пар). `position` сейчас у
всех строк 0, поэтому сортировка только по нему — порядок строк с одинаковыми значениями,
то есть порядок heap, а не факт: `VACUUM` его переписывает. Два последних ключа делают
ответ определённым, а `is_primary` первым — тем, что выбрал владелец (экраны берут
`photos[0]` как аватар).

`url` — путь, а не идентификатор: при удалении аккаунта файл ищется по последнему сегменту
(`basename`), потому что доверять пути как ключу нельзя. Файлы удаляются после commit,
чтобы неудачная транзакция не оставила базу, указывающую на несуществующие файлы.

### `interests` / `user_interests`
`interests`: `id` (Int PK), `slug` (String 80, unique), `name`, `category` (index). Связь M:N через `user_interests` (`profile_id` + `interest_id`, составной PK, `uq_user_interest`).

## Тест и профиль совместимости

### `test_questions`
`id` (Int PK), `category`, `trait`, `text`, `position`, `is_active`. Чтение категорий идёт индексом `ix_question_category_position (category, position)`; одиночный индекс по `category` удалён `e6b28c4a13d0` — он был префиксом этого же ключа.

### `test_options`
`id` (Int PK), `question_id` (FK, cascade, index), `text`, `value` (Float — вклад варианта в признак), `position`.

### `test_answers`
`id` (UUID PK), `user_id` (FK, cascade), `question_id` (FK), `option_id` (FK). Ограничение `uq_user_question_answer (user_id, question_id)` — один ответ на вопрос; оно же служит чтению по `user_id`, поэтому отдельный индекс по пользователю удалён `e6b28c4a13d0`.

Дырка, оставленная намеренно: `question_id` и `option_id` — FK с `ON DELETE CASCADE`, и ни один
индекс с них не начинается, поэтому удаление вопроса будет читать `test_answers` целиком.
Недостижимо сегодня: каталог вопросов не удаляется, `is_active` его только выключает. Индекс
под это удаление стоил бы записи на каждом ответе, чтобы ускорить операцию, которой в продукте
нет. Если админка с удалением вопросов появится — первым делом нужен индекс по `question_id`.

Читается всегда с `ORDER BY question_id` (`TestRepository.list_answers`). Без порядка
ответы приходят в порядке кучи, а `upsert_answer` — это `UPDATE`, то есть новая версия
кортежа: перезапись одного ответа переносит его строку в конец таблицы (замерено на dev
кластере: seq scan `1..21` превратился в `2..21,1` после обновления с тем же значением).
Вектор совместимости — сумма float-ов по этому порядку, поэтому без `ORDER BY` те же
самые ответы давали бы разные проценты в разных запросах.

### `test_results`
`id` (UUID PK), `user_id` (FK, cascade), `category` (String 40), `score` (Float). `uq_user_category_result (user_id, category)` — агрегированная оценка по категории.

### `compatibility_profiles` (1:1 с `users`)
`user_id` (FK, unique, cascade), `vector` (JSONB — нормированные компоненты для движка), `version` (Integer, default 1 = `ENGINE_VERSION`).

## Социальный граф

### `likes`
`from_user_id`, `to_user_id` (FK users, cascade), `compatibility_score` (Float, null). `uq_like_pair (from_user_id, to_user_id)`; индекс `ix_likes_to_user_id` — «кто меня лайкнул» ведёт вторую колонку, и ни один ключ с неё не начинается. Чтение `from_user_id` обслуживает тот же уникальный ключ: одиночный индекс по нему удалён `e6b28c4a13d0`.

### `passes`
Аналогично `likes`, `uq_pass_pair`. Используется, чтобы не показывать пропущенных повторно.

### `matches`
`user_a_id`, `user_b_id` (FK users, cascade), `compatibility_score` (Float, default 0). `uq_match_pair (user_a_id, user_b_id)`; индекс `ix_matches_user_b_id`. Создаётся при взаимном лайке.

`compatibility_score` — не архив, а то, что показывают список пар и заголовок пары.
Пишется один раз при создании mutual-лайка (полным float-ом движка, не округлённым до 4
знаков: при выдаче это значение умножается на 100 и округляется, и округлённый снимок может
лечь по другую сторону границы, чем живой пересчёт той же пары) и перезаписывается при
каждом пересчёте теста или правке `interests`/`dating_goal` у любого из пары. Движок
симметричен (`compute(a, b) == compute(b, a)`, закреплено тестом), поэтому одной строки на
пару достаточно и обновление с любой стороны даёт то же число. Замер до правки: после
пересдачи одним человеком — `list=100 single=100 live=46`.

### `blocks`
`blocker_id`, `blocked_id` (FK, cascade), `uq_block_pair (blocker_id, blocked_id)`; индекс `ix_blocks_blocked_id` ведёт обратное чтение — «кто меня заблокировал», — которое больше ни один ключ этой таблицы не начинает. Скрывает пару из подбора.

### `reports`
`reporter_id`, `reported_id` (FK, cascade), `reason` (String 80), `details` (Text, null), `status` (String). `uq_report (reporter_id, reported_id, reason)`; индексы `ix_reports_reported_id` и `ix_reports_status` — очередь жалоб фильтруется статусом. Одиночный индекс по `reporter_id` удалён `e6b28c4a13d0`: он был префиксом `uq_report`.

## Чат

### `messages`
`id` (UUID PK), `match_id` (FK matches, cascade), `sender_id` (FK users, cascade, index), `body` (Text), `is_deleted` (Boolean), `client_msg_id` (String 64, null). Индекс `ix_message_match_created (match_id, created_at)` — для пагинации истории; одиночный индекс по `match_id` удалён `e6b28c4a13d0`, потому что был его префиксом. Замер на 40 120 сообщениях: история пары читается именно им (`Index Scan messages`, 52 строки, 0.23 мс), а не перебором таблицы.

`client_msg_id` — имя отправки, данное клиентом; оно уникально в пределах `(match_id, sender_id)`
и поэтому повтор уснувшего запроса находит уже сохранённую строку вместо второй копии. Индекс
`uq_message_sender_client_id (match_id, sender_id, client_msg_id) UNIQUE WHERE client_msg_id IS NOT NULL`
частичный: у сообщений, записанных до этой ревизии, и у отправок без имени ключа нет, и NULL не
должен сталкиваться с NULL. Миграция `9c1f5b7d2a40`.

### `message_reads`
`id` (UUID PK), `message_id` (FK messages, cascade), `reader_id` (FK users, cascade), `read_at` (timestamptz). `uq_message_read (message_id, reader_id)`. Индекс `ix_message_reads_reader_message (reader_id, message_id)` — счётчик непрочитанных фильтрует `reader_id` один, а ни один ключ этой таблицы с него не начинался. Непрочитанные = сообщения другого отправителя без записи о прочтении читателем.

## Подбор

### `discovery_queue`
`viewer_id` + `candidate_id` (составной PK `uq_discovery_queue_pair`, оба FK users с CASCADE), `rank` (Integer — порядок в колоде, назначается один раз при постановке и не переставляется), `score` (Integer — совместимость на момент постановки), `status` (`ready` | `seen`, CheckConstraint), `queued_at`, `seen_at`. Индекс `ix_discovery_queue_viewer_status_rank (viewer_id, status, rank)` — чтение очередной страницы. Уникальный индекс `uq_discovery_queue_viewer_rank (viewer_id, rank)` (`c5a7d1e0b342`).

`rank` — шаг курсора: `deck_claim` берёт строки `rank > :after` с `FOR UPDATE SKIP LOCKED`, и
два параллельных пополнения, прочитавшие один и тот же потолок `max(rank) + 1`, сажают нового
кандидата на ранг, который первая пачка уже заняла. Обе строки оказываются за одним шагом
курсора, и выбрать можно только одну: второй человек молча исчезает из колоды. Ограничение на
пару этого не видит — строки-то от разных пар. Поэтому постановка идёт через
`ON CONFLICT DO NOTHING` без указания имени: проигравший столкновение рангов просто не
попадает в очередь и остаётся доступен следующему пополнению, а не уничтожается вместе с
парой. Миграция сначала вычищает старые коллизии детерминированно (`DELETE` с правилом
`dup.candidate_id > keep.candidate_id`) и только потом поднимает уникальный индекс.

Строки `seen` — это память о том, что карточку уже показывали: они переживают перестройку колоды, поэтому человек не показывается вторично после like/pass. Тот же `rank` служит курсором API (`GET /discover?cursor=`), поэтому страница не сдвигается под тем, кто успел свайпнуть между запросами. Курсор ограничен вместимостью колонки: число, которое `integer` не хранит, не доходит до запроса — граница вычитана из типа колонки и держится тестом (правило для всех таких чисел — в начале [`API.md`](API.md)).

## Рекомендации

### `activities`
Каталог активностей: `id` (Int PK), `slug`, `title`, `description`, `category`, `energy`/`social`/`cost` (Float 0..1) — сигналы для детерминированной оценки.

### `activity_preferences`
`user_id` (FK, cascade), `activity_id` (FK, cascade), `uq_activity_pref (user_id, activity_id)`; индекс `ix_activity_preferences_activity_id` ведёт обратное чтение — «кто это любит», — а одиночный индекс по `user_id` удалён `e6b28c4a13d0` как префикс уникального ключа. Явные предпочтения пользователя.

### `recommendations`
`id` (UUID PK), `match_id` (FK matches, cascade), `activity_id` (FK activities, cascade), `score` (Float, default 0), `explanation` (JSONB — структурированные причины `{"positive": [...], "context": [...]}`), `position` (Integer). `uq_match_activity_rec (match_id, activity_id)`; индекс `ix_rec_match_position (match_id, position)` — порядок выдачи. Одиночный индекс по `match_id` удалён `e6b28c4a13d0`: оба ключа начинаются с него. Выбор пользователем активности (`POST /matches/{id}/recommendations/{activity_id}/select`) сохраняется в `activity_preferences`.

## Токены

### `refresh_tokens`
`id` (UUID PK), `user_id` (FK, cascade), `token_hash` (String 64, unique — SHA-256 от refresh-токена), `expires_at` (timestamptz), `revoked` (Boolean), `revoked_at`, `user_agent` (String, null). Индекс `ix_refresh_user_revoked (user_id, revoked)` — отзыв сессий пользователя; одиночный индекс по `user_id` удалён `e6b28c4a13d0` как его префикс. Refresh-токены ротируются: при обновлении старый отзывается.

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
«есть drift». Имена этих ограничений остаются в схеме как были заведены (`4f2a1c9d7b30`),
и менять их ради красоты — отдельная миграция без полезного результата; `uq_user_interest`
к тому же назван явно в `ON CONFLICT (constraint ...)` в `user_repo`. Ссылка кода на
`uq_discovery_queue_pair` ушла, когда `deck_append` перестал указывать имя арбитра: `DO NOTHING`
без имени смотрит и на пару, и на новый уникальный ранг, и это то, что нужно постановке.

## Миграции и сид

- **Миграции:** `alembic upgrade head` (применяется автоматически в docker-compose при старте backend).
- **Сид:** `python -m app.seed [--if-empty]`. Идемпотентно создаёт справочники (`interests`, `activities`, `test_questions`/`test_options`), затем демо-домен: 1 демо-пользователь (`demo@befos.app` / `Demo12345`), 50 пользователей и 4 демо-матча. `RNG_SEED=20240501` — детерминированная генерация. Функции `_seed_catalogs`, `_clear_domain`, `run_seed` переиспользуются и в тестах.
- **Копия, восстановление и откат** — в [`docs/OPERATIONS.md`](OPERATIONS.md): что именно копируется (и почему том Docker копией не является), как drill проверяет копию отпечатком `backend/ops/backup_fingerprint.sql`, и в каком порядке ставятся миграции релиза.
