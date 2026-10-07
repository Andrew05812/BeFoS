# API BeFoS

Базовый префикс: `/api/v1`. Формат тела — JSON (кроме загрузки фото — `multipart/form-data`).
Аутентификация — Bearer access-токен в заголовке `Authorization: Bearer <token>`.

**Конверт ошибки** (все не-2xx ответы):

```json
{ "error": { "code": "STRING_CODE", "message": "Текст", "detail": null } }
```

Число, которое не помещается в колонку, отсекается на входе и не доходит до запроса:
`question_id` и `option_id` в `POST /tests/answers`, `activity_id` в
`POST /matches/{match_id}/recommendations/{activity_id}/select` и номер в `cursor` подбора
ограничены вместимостью PostgreSQL `integer`. Адрес или тело с таким числом — ошибка
запроса (`validation_error` / 422), а не сбой сервера: без границы значение доходило до
SQL, где его отвергал драйвер, и рукописная опечатка выглядела как 500 `internal_error`
с трассировкой.

**Перечисления**
- `gender`: `male | female | nonbinary | other`
- `dating_goal`: `relationship | marriage | friendship | casual | networking`

---

## Health

| Метод | Путь | Что утверждает | Когда базы нет |
|-------|------|----------------|---------------|
| GET | `/health` | процесс backend жив | всегда 200 |
| GET | `/health/db` | соединение берётся и `SELECT 1` выполняется | 503 `{"status":"degraded","database":"unavailable"}` |

Пробы отвечают вне конверта ошибки: их читают машины, и тело `/health/db` намеренно не
содержит текста ошибки драйвера (в нём есть host, user и пароль строки подключения, а
маршрут открыт без логина).

`/health` не лимитируется ничем: монитор, получивший 429, объявит сервис мёртвым в час пик,
которого не было. `/health/db` стоит 60 запросов в минуту на адрес — не потому, что он дорогой
для процессора, а потому, что каждый его запрос берёт соединение из пула, который делят настоящие
пользователи, и цикл по этому маршруту без ответа может оставить их без пула. 429 здесь приходит
в обычном конверте (`rate_limited`), поэтому алертер, который опрашивает оба маршрута чаще раза в
секунду, должен читать 429 как «я слишком часто спрашиваю», а не как «сервис падает».

Когда база недоступна, любой обычный эндпоинт отвечает тем же 503 и заголовком
`Retry-After: 5` в стандартном конверте:

```json
{ "error": { "code": "database_unavailable", "message": "BeFoS is sorting itself out for a moment. Try again in a few seconds." } }
```

Это не «ошибка запроса» и не повод выбрасывать сессию: 5xx означает «попробуй позже», и
клиент сохраняет токены и набранный текст. Детали — в [`OPERATIONS.md`](OPERATIONS.md).

---

## Auth

| Метод | Путь | Тело | Ответ |
|-------|------|------|-------|
| POST | `/auth/register` | `{email, password, password_confirm}` | `201` `AuthResponse` |
| POST | `/auth/login` | `{email, password}` | `AuthResponse` |
| POST | `/auth/refresh` | `{refresh_token}` | `AuthResponse` |
| POST | `/auth/logout` | `{refresh_token}` | `200` |

`AuthResponse`:

```json
{
  "user": { "id": "uuid", "email": "user@mail.com", "is_active": true, "created_at": "ISO-8601" },
  "tokens": { "access_token": "…", "refresh_token": "…", "token_type": "bearer", "expires_in": 900 }
}
```

Ошибки: несовпадение `password_confirm` → `422`; занятый email → `409`; неверный пароль → `401`.

---

## Users / Profile

| Метод | Путь | Тело | Ответ |
|-------|------|------|-------|
| GET | `/users/me` | — | `ProfileOut` |
| POST | `/users/me/onboarding` | `OnboardingProfile` | `ProfileOut` |
| PATCH | `/users/me` | `ProfileUpdate` (частичное) | `ProfileOut` |
| POST | `/users/me/photo` | `multipart` поле `file` | `ProfileOut` |
| GET | `/users/interests` | — | `{interests: [{slug, name, category}]}` |
| GET | `/users/{user_id}` | — | `PublicProfile` |

`ProfileOut`:

```json
{
  "user_id": "uuid", "name": "Алекс", "age": 30, "city": "Москва",
  "gender": "male", "about": "…", "dating_goal": "relationship",
  "photos": [{ "id": "uuid", "url": "/uploads/x.png", "is_primary": true, "position": 0 }],
  "interests": [{ "slug": "hiking", "name": "Походы", "category": "active" }],
  "lifestyle": {}, "age_min": 18, "age_max": 60, "gender_preference": ["female"]
}
```

`OnboardingProfile` (POST `/users/me/onboarding`):

```json
{
  "name": "Алекс", "birth_date": "1996-05-10", "city": "Москва",
  "gender": "male", "about": "…", "dating_goal": "relationship",
  "interests": ["hiking", "cinema", "coffee"], "lifestyle": {},
  "age_min": 18, "age_max": 60, "gender_preference": ["female"]
}
```

`birth_date` — строка `YYYY-MM-DD`; возраст должен быть 18..120.

**Фото.** `photos` отдаётся в одном порядке на всех эндпоинтах: выбранный владельцем
(`is_primary`) первым, далее `position`, `created_at`, `id` — два последних как
детерминированный разрыв ничьих, потому что `position` у всех снимков 0 и порядок без них
не факт, а то, что отдаст heap. Экраны берут `photos[0]` как аватар, поэтому это контракт,
а не деталь реализации. `POST /users/me/photo` принимает JPEG/PNG/WEBP; тело читается с
пределом `MAX_UPLOAD_SIZE_MB` (дефолт 5) и отказывается на 422 `validation_error`, не
дочитывая остаток; слишком большой объявленный холст — тоже 422, а не 500. `DELETE
/users/me` удаляет и строки `photos`, и файлы: `/uploads` — публичная статика без
авторизации, поэтому скрытие анкеты не означает, что снимков больше нет.

`PublicProfile` (GET `/users/{id}`):

```json
{
  "user_id": "uuid", "name": "…", "age": 27, "city": "…", "about": "…",
  "dating_goal": "…", "gender": "…",
  "interests": ["Походы", "Кино"],
  "photos": ["/uploads/a.png"],
  "compatibility": 82,
  "categories": [{ "category": "values", "label": "Ценности", "score": 88, "weight": 0.25 }],
  "shared_interests": ["hiking", "cinema"]
}
```

**Кого этот маршрут показывает.** Чужой профиль отдаётся тому же правилу, которым колода решает,
кого показывать: аккаунт жив, активен, не спрятан и прошёл анкету. Поэтому профиль, который
человек спрятал, аккаунт, который отключили, и недоделанная регистрация отвечают `404 not_found` —
как и `POST /users/{id}/like` с `/pass`, — а не `403` и не анкетой без фото. Владелец читает свой
профиль в любом из этих состояний: прятаться — не значит отключаться, и недоделанную анкету надо
чем-то доделывать. Удалённый аккаунт не читает ничего — его токен отвергается на 401, ещё до
маршрута. Блокировка отвечает 404 в обе стороны, чтобы маршрут не подтверждал существование того,
кого уже не видно.

---

## Tests (профиль совместимости)

| Метод | Путь | Тело | Ответ |
|-------|------|------|-------|
| GET | `/tests` | — | `{questions: [...], total, answered}` |
| GET | `/tests/progress` | — | `{answered, total, percent, remaining, completed}` |
| POST | `/tests/answers` | `{answers: [{question_id, option_id}]}` | прогресс |
| POST | `/tests/complete` | — (без тела) | `{categories: [...], completed_at}` |

Вопрос:

```json
{
  "id": 1, "category": "values", "trait": "…", "text": "…", "position": 0,
  "options": [{ "id": 11, "text": "…", "position": 0 }]
}
```

`categories[]` после завершения — `CategoryScore`: `{category, label, score (0..100), weight}`.

---

## Discovery (подбор)

| Метод | Путь | Query | Ответ |
|-------|------|-------|-------|
| GET | `/discover` | `limit` (1..50, по умолчанию 20), `cursor` | `Paged<DiscoveryCard>` |
| POST | `/users/{user_id}/like` | — (без тела) | `{liked, match, match_id, compatibility}` |
| POST | `/users/{user_id}/pass` | — (без тела) | `{passed}` |

`Paged`: `{items: [...], next_cursor, has_more}`.

`cursor` — непрозрачная метка последнего просмотренного места в колоде, её выдаёт сам
сервер и меняет только он. Позиции (`offset`) нет: свайп убирает кандидата из выборки,
и номер следующей карты тут же начинает указывать на другого человека. Колода
ранжируется один раз и хранится в таблице `discovery_queue`, поэтому страницы не
повторяются и не пропускают кандидатов, даже если между запросами кто-то скрылся или
был заблокирован.

Метка проверяется на входе, а не доверяется как число: `cursor`, который нельзя
расшифровать, и номер за пределами колонки `rank` дают `validation_error` / 422 — общее
правило для таких чисел записано в начале этого документа.

`DiscoveryCard`:

```json
{
  "user_id": "uuid", "name": "…", "age": 27, "city": "…", "about": "…",
  "dating_goal": "…", "photo_url": "/uploads/x.png",
  "interests": ["Походы"], "compatibility": 82, "shared_interests_count": 3,
  "highlight": "Общие интересы: Походы, Каякинг"
}
```

`highlight` — короткая «расшифровка» подбора на экране карточки («почему этот человек мне показан»), всегда производная от реальных данных: имена общих интересов, совпадение города, либо сильнейшая категория совместимости ≥ 70%. Поля нет, если ни одно правило не сработало.

Подбор исключает самого пользователя, заблокированных и уже «пропущенных»/лайкнутых. Взаимный лайк создаёт `match` и возвращает `match: true` с `match_id`.

---

## Matches

| Метод | Путь | Query | Ответ |
|-------|------|-------|-------|
| GET | `/matches` | — | `{matches: [MatchSummary]}` |
| GET | `/matches/{match_id}` | — | `{match_id, compatibility, created_at, other_user: PublicProfile}` |
| GET | `/matches/{match_id}/compatibility` | — | `CompatibilityOut` |
| GET | `/matches/{match_id}/recommendations` | `force` | `{match_id, recommendations: [...]}` |
| POST | `/matches/{match_id}/recommendations/{activity_id}/select` | — | `204`; `404`, если активности нет в каталоге |

`GET /matches/{match_id}` смотрит на собеседника глазами участника пары, а не колоды.
«Скрыть из подбора» снимает анкету из выдачи, с публичной карточки `GET /users/{id}` и с
путей `like`/`pass`, но не стирает матч, который оба уже подтвердили: список пар, история
сообщений и `/compatibility` продолжают его отдавать, поэтому и заголовок пары обязан
отвечать 200, а не «Match not found» под открытым чатом. Из правила колоды здесь исключено
только `is_hidden` — удалённый, деактивированный или не прошедший анкету аккаунт остаётся
недоступен и для того, кто с ним матчился.

`score` совместимости и рекомендаций — процент `0..100`; границы объявлены в выходных
Pydantic-схемах (`CategoryScoreOut.score`, `CompatibilityOut.overall`, `DiscoveryCard.
compatibility`, `LikeResponse.compatibility`, `MatchSummary.compatibility`, `RecommendationOut.score`),
поэтому оценка вне диапазона не уходит на экран, а валится на сериализации ответа.

Процент в списке пар (`/matches`) и в заголовке пары (`/matches/{match_id}`) — тот же, что
считает `/matches/{match_id}/compatibility`. Он хранится на строке матча, но перезаписывается
когда меняется любой из входов движка: после пересдачи теста и после правки
`interests`/`dating_goal` в профиле. До этой правки на одной паре было замерено расхождение
`list=100 single=100 live=46`.
Ответ `POST /users/{id}/like` остаётся честным описанием момента лайка: он говорит процент,
на который лайк был поставлен, и не меняется задним числом.

`MatchSummary`:

```json
{
  "match_id": "uuid", "user_id": "uuid", "name": "…", "age": 27, "city": "…",
  "photo_url": "…", "compatibility": 82, "last_message": "…",
  "last_message_at": "ISO-8601", "unread": 2, "created_at": "ISO-8601"
}
```

`CompatibilityOut`:

```json
{
  "overall": 82, "engine_version": 1,
  "categories": [{ "category": "values", "label": "Ценности", "score": 88, "weight": 0.25 }],
  "strengths": [{ "category": "values", "label": "Ценности", "text": "…", "score": 0.9 }],
  "differences": [{ "category": "leisure", "label": "Досуг", "text": "…", "score": 0.4 }],
  "shared_interests": ["hiking", "cinema"]
}
```

`recommendations[]`:

```json
{
  "activity": { "id": 3, "slug": "…", "title": "…", "description": "…", "category": "…", "energy": 0.6, "social": 0.8, "cost": 0.3 },
  "score": 87, "position": 0, "reasons": ["Общий интерес — Походы", "Проходит в вашем городе"]
}
```

Доступ к матчу имеют только его участники; иначе `404` с `error.code = "not_found"` — ровно так
же, как отвечает маршрут о несуществующей паре. `403` здесь означал бы «такая пара есть, но не
твоя», то есть был бы оракулом для перебора id, поэтому ни один маршрут с идентификатором пары
его не возвращает.

---

## Chat

| Метод | Путь | Query / Тело | Ответ |
|-------|------|--------------|-------|
| GET | `/matches/{match_id}/messages` | `limit` (1..100), `before_id` | `{messages: [MessageOut], has_more}` |
| POST | `/matches/{match_id}/messages` | `{body, client_msg_id?}` (body 1..4000, id ≤ 64) | `201` `MessageOut`; повтор с тем же `client_msg_id` → `200` тот же объект |
| POST | `/matches/{match_id}/read` | — | `{marked_read: N}` |

Сообщения, отправленные через REST, и отметки о прочтении дополнительно транслируются в WebSocket матча (`type: message` / `type: read`), поэтому подключённый второй клиент получает их без повторного запроса истории.

`client_msg_id` — имя, которое отправитель даёт своей отправке. POST, ответ на который не дошёл,
неотличим от POST, который отказали, поэтому повтор без имени записывает вторую копию того же
предложения. С именем на `(match_id, sender_id, client_msg_id)` в БД стоит частичный уникальный
индекс: повтор возвращает уже сохранённое сообщение, а analytics-событие и трансляция в комнату
идут только на первую запись. Имя необязательно: отправку без имени нельзя отличить от
намеренного повтора текста, и она пишется как обычное сообщение. `client_msg_id` длиннее 64
символов — `422` на REST и `type: error` в сокете (сокет остаётся жив).

`MessageOut`:

```json
{
  "id": "uuid", "match_id": "uuid", "sender_id": "uuid", "body": "…",
  "created_at": "ISO-8601", "is_read": false, "is_own": true, "client_msg_id": "local-uuid"
}
```

### WebSocket `/ws/chat/{match_id}?token=<access>`

Авторизация по JWT на рукопожатии, но токен — не пропуск: перед тем как принять сокет, сервер
проверяет строки пользователя и матча. Close `1008` (на клиенте проявляется как `403` при
handshake) бывает когда токен нечитаем, когда аккаунт удалён или отключён, и когда пары больше
нет; то же проверяется перед каждым кадром `message`, `read` и `typing`, потому что и токен, и
открытое соединение живут дольше, чем решение о блокировке, удалении или отключении. Кадр
«печатает» здесь не исключение: он доходит до экрана другого человека, значит спрашивает строки
не дешевле сообщения.

У соединения два окна, и ни одно из них не видят лимитеры REST. До расшифровки токена: 30
рукопожатий в минуту на адрес — каждое стоит разбор JWT и два чтения строк. Внутри соединения:
120 кадров в минуту на аккаунт, считаются и исправные, и испорченные; ответ — кадр
`{"type":"error","message":"Too many messages, slow down."}`, а не разрыв, потому что слишком
быстрый клиент не нарушил политику, он просто опередил окно.

**Клиент → сервер:**

```json
{ "type": "message", "body": "текст", "client_msg_id": "local-uuid" }
{ "type": "typing", "typing": true }
{ "type": "read" }
```

**Сервер → клиент:**

```json
{ "type": "message", "id": "…", "client_msg_id": "…", "match_id": "…", "sender_id": "…", "body": "…", "created_at": "…", "is_read": false }
{ "type": "typing", "user_id": "…", "typing": true }
{ "type": "read", "user_id": "…" }
{ "type": "presence", "user_id": "…", "online": true }
{ "type": "error", "message": "…" }
```

Отправитель получает кадр `message` всегда: при первой записи — от комнаты, при повторе — только
ему, с тем же `id`. Вторая попытка не добавляет в комнату второе сообщение, а клиент, у которого
такой id уже есть в списке, кадр пропускает.

---

## Safety

| Метод | Путь | Тело | Ответ |
|-------|------|------|-------|
| POST | `/users/{user_id}/block` | — (без тела) | `200` |
| POST | `/users/{user_id}/report` | `{reason (2..40), details?}` | `200` |
| POST | `/users/me/visibility` | `{hidden: bool}` | `200` |
| DELETE | `/users/me` | — | `200` (удаляет аккаунт, доступ отзывается) |

Блокировка скрывает пользователя из подбора обеих сторон.
