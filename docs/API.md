# API BeFoS

Базовый префикс: `/api/v1`. Формат тела — JSON (кроме загрузки фото — `multipart/form-data`).
Аутентификация — Bearer access-токен в заголовке `Authorization: Bearer <token>`.

**Конверт ошибки** (все не-2xx ответы):

```json
{ "error": { "code": "STRING_CODE", "message": "Текст", "detail": null } }
```

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
  "user_id": "uuid", "name": "Андрей", "age": 30, "city": "Москва",
  "gender": "male", "about": "…", "dating_goal": "relationship",
  "photos": [{ "id": "uuid", "url": "/uploads/x.png", "is_primary": true, "position": 0 }],
  "interests": [{ "slug": "hiking", "name": "Походы", "category": "active" }],
  "lifestyle": {}, "age_min": 18, "age_max": 60, "gender_preference": ["female"]
}
```

`OnboardingProfile` (POST `/users/me/onboarding`):

```json
{
  "name": "Андрей", "birth_date": "1996-05-10", "city": "Москва",
  "gender": "male", "about": "…", "dating_goal": "relationship",
  "interests": ["hiking", "cinema", "coffee"], "lifestyle": {},
  "age_min": 18, "age_max": 60, "gender_preference": ["female"]
}
```

`birth_date` — строка `YYYY-MM-DD`; возраст должен быть 18..120.

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
| POST | `/matches/{match_id}/recommendations/{activity_id}/select` | — | `204` |

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

Доступ к матчу имеют только его участники; иначе `403/404`.

---

## Chat

| Метод | Путь | Query / Тело | Ответ |
|-------|------|--------------|-------|
| GET | `/matches/{match_id}/messages` | `limit` (1..100), `before_id` | `{messages: [MessageOut], has_more}` |
| POST | `/matches/{match_id}/messages` | `{body}` (1..4000) | `201` `MessageOut` |
| POST | `/matches/{match_id}/read` | — | `{marked_read: N}` |

Сообщения, отправленные через REST, и отметки о прочтении дополнительно транслируются в WebSocket матча (`type: message` / `type: read`), поэтому подключённый второй клиент получает их без повторного запроса истории.

`MessageOut`:

```json
{
  "id": "uuid", "match_id": "uuid", "sender_id": "uuid", "body": "…",
  "created_at": "ISO-8601", "is_read": false, "is_own": true
}
```

### WebSocket `/ws/chat/{match_id}?token=<access>`

Авторизация по JWT на рукопожатии; невалидный токен → close `1008` (на клиенте проявляется как `403` при handshake).

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

---

## Safety

| Метод | Путь | Тело | Ответ |
|-------|------|------|-------|
| POST | `/users/{user_id}/block` | — (без тела) | `200` |
| POST | `/users/{user_id}/report` | `{reason (2..40), details?}` | `200` |
| POST | `/users/me/visibility` | `{hidden: bool}` | `200` |
| DELETE | `/users/me` | — | `200` (удаляет аккаунт, доступ отзывается) |

Блокировка скрывает пользователя из подбора обеих сторон.
