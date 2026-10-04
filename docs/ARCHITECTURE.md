# Архитектура BeFoS

## Общая схема

```
┌─────────────────────────┐        REST (JSON) / WebSocket        ┌──────────────────────────┐
│  Android (Jetpack        │ ───────────────────────────────────▶ │  FastAPI (async)          │
│  Compose, Material 3)    │ ◀─────────────────────────────────── │                           │
└─────────────────────────┘                                       │  API (v1) → Service →     │
         │                                                         │  Repository → PostgreSQL  │
         │ data / domain / presentation                           │                           │
         ▼                                                         │  Compatibility Engine     │
   Ktor HttpClient + WebSocket                                     │  Recommendation Engine    │
   DataStore (токены)                                              │  WS Chat Gateway          │
                                                                   └──────────────────────────┘
```

Принцип: **тонкие контроллеры, логика в сервисах, доступ к данным в репозиториях**. Ни один слой не «перепрыгивает» через соседний.

## Backend

### Слои

- **`app/api/v1/`** — HTTP-маршруты. Контроллеры валидируют вход (Pydantic), вызывают сервис и формируют ответ. Маршруты сгруппированы по тегам: `auth`, `users`, `tests`, `discover`, `matches`, `chat`, `safety`, `health`. Все подключаются под префиксом `settings.api_v1_prefix` (`/api/v1`).
- **`app/services/`** — бизнес-логика: `auth_service`, `profile_service`, `test_service`, `compatibility_service`, `discovery_service`, `match_service`, `matches_service`, `chat_service`, `recommendation_service`, `photo_service`, `safety_service`. Сервисы не знают про HTTP.
- **`app/repositories/`** — доступ к данным через SQLAlchemy 2.0 (async). Инкапсулируют запросы, возвращают модели/примитивы.
- **`app/models/`** — декларативные SQLAlchemy-модели (21 таблица), см. [`DATABASE.md`](DATABASE.md).
- **`app/schemas/`** — Pydantic-схемы запросов/ответов (DTO-граница).
- **`app/core/`** — `config` (pydantic-settings, `.env`), `database` (async engine, `get_session`), `security` (bcrypt, JWT), `rate_limit` (скользящее окно), `exceptions` (единый конверт ошибок).

### Движок совместимости (`app/compatibility/`)

- `traits.py` — определение семи категорий и их компонентов.
- `weights.py` — `DEFAULT_WEIGHTS` (сумма = 1.0), `ENGINE_VERSION`, валидация конфигурации весов.
- Формула: `Score = Σ normalize(component_i) × weight_i`. Полностью детерминированно: одинаковый вход → одинаковый выход, никаких случайных величин.
- `explain_pair(a, b)` возвращает `CompatibilityResult` (общий процент, разбивка по категориям, версия движка) и `CompatibilityExplanation` (сильные стороны, отличия, общие интересы — пересечение множеств интересов пары).

### Движок рекомендаций (`app/recommendations/`)

- Каталог активностей (`activities`) несёт сигналы `energy / social / cost` (0..1).
- Оценка пары по активностям детерминированная: учитываются интересы, досуг, образ жизни, локация и цель знакомства обоих пользователей. Каждая рекомендация содержит `score`, `position` и человекочитаемые `reasons`.

### WebSocket-шлюз (`app/websocket/`)

- Эндпоинт `/ws/chat/{match_id}?token=<access>`.
- Авторизация по JWT на рукопожатии; невалидный токен → закрытие соединения с кодом `1008`.
- Проверяется участие пользователя в матче.
- Входящие типы: `message`, `typing`, `read`. Исходящие: `message`, `typing`, `read`, `presence`, `error`.

### Безопасность

- Пароли — bcrypt-хэш; refresh-токен хранится как SHA-256 и ротируется при обновлении.
- Rate limiting — скользящее окно; отдельный лимитер для `/auth`.
- Загрузки изображений перекодируются Pillow (защита от вредоносных файлов), каталог загрузок отдаётся отдельно.
- Секреты только в `.env` (исключён из Git). В логах не выводятся пароли, токены и чувствительные данные.

## Android

Слоистая архитектура, зависимость направлена внутрь (presentation → domain ← data):

- **`core/`**
  - `designsystem/` — тема Material 3 (`BeFosTheme`), палитра, типографика, формы и единая библиотека компонентов: `AppButton`, `AppTextField`, `AppCard`, `AppTopBar`, `SectionHeader`, `LoadingState`, `ErrorState`, `EmptyState`, `MessagePane`, `Avatar`, `CompatibilityScore`, `CompatibilityBadge`, `InterestChip`, `MessageBubble`, `MatchCard`, `ProfileCard`, `scoreColor`. Все экраны используют только эти компоненты — локальных дублей UI-логики в `presentation/` нет.
  - `network/` — `ApiConfig` (базовые URL из `BuildConfig`), `befosJson` (конфигурация kotlinx-serialization), `createHttpClient` (Ktor + OkHttp, ContentNegotiation, WebSockets, bearer-авторизация с автообновлением токенов), `TokenStore` (DataStore), `SafeApiCall` (`ApiResult`, `apiCall`).
  - `di/` — `AppContainer` (ручная DI-граф: scope, TokenStore, HttpClient, ApiService, репозитории) и `beFosViewModel`-фабрика.
  - `common/` — `UiState` (Loading/Success/Error).
- **`data/`** — `model/Dtos.kt` (`@Serializable` DTO c `@SerialName`), `remote/ApiService` (типизированные вызовы, возвращают `ApiResult`), `mapper/` (DTO → domain), `repository/` (реализации доменных интерфейсов; `ChatRepositoryImpl` содержит устойчивый `ChatSocket` с автопереподключением).
- **`domain/`** — `model/Models.kt` (чистые модели) и `repository/Repositories.kt` (интерфейсы + `ChatEvent`).
- **`presentation/`** — по фиче: `ViewModel` (StateFlow) + Compose-экран. Навигация — `navigation/BeFosNavHost` + `Routes`; корневой роутинг (`splash → auth/onboarding/main`) решает `RootViewModel` на основе реального состояния сессии и заполненности профиля.

### Сетевое взаимодействие

- Все вызовы через `ApiService` возвращают `ApiResult<T>` — сетевые ошибки и не-2xx не бросают исключение, а превращаются в `ApiResult.Error(code, message)` (сообщение берётся из конверта ошибки backend).
- Автообновление access-токена настроено в Ktor `Auth` (bearer): при 401 выполняется `POST /auth/refresh`, токены обновляются в `TokenStore`.
- Чат: история/отправка — через REST (надёжная доставка и персистентность), realtime-события (входящие, typing, read, presence) — через WebSocket; входящие сообщения дедуплицируются по `id`. Сообщения и отметки о прочтении, принятые через REST, backend транслирует в `manager.broadcast_to_match`, поэтому открытый сокет второго участника получает их мгновенно.
- WebSocket-клиент настроен с keepalive-пингом 10 с (`install(WebSockets) { pingIntervalMillis = 10_000 }`): оборванный без close-фрейма TCP (например, рестарт backend) обнаруживается по pong-таймауту, и цикл `ChatSocket` переподключается с фиксированным backoff. События публикуются через `tryEmit`, чтобы переполнение буфера не могло заморозить петлю reconnect.
- WebSocket не может инициировать обновление токенов (токен передаётся query-параметром при рукопожатии), поэтому `ChatSocket` перед подключением выполняет probe-запрос `GET /users/me` через REST-клиент с автообновлением и берёт свежий access-токен из `TokenStore`.

### Тестирование

- Unit-тесты ViewModel (JUnit4 + MockK + Turbine + kotlinx-coroutines-test): валидация авторизации, поведение лайка/мэтча в подборе, дедупликация и отправка сообщений в чате.

## Наблюдательность

- Каждый HTTP-запрос получает correlation id в `X-Request-Id`: клиентский id принимается только если он является одним печатным токеном `[A-Za-z0-9_.-]{1,64}`, иначе генерируется свой 16-hex. Значение возвращается в заголовке ответа — по нему пользователь или поддержка называет конкретный запрос.
- Формат лога — `время | уровень | логгер | request_id | сообщение`. Id берётся из `contextvars` (`RequestIdFilter`), поэтому error-строка, analytics-событие и access-строка одного запроса читаются как одна история.
- `befos.access` пишет `request METHOD path -> STATUS in X ms`; дольше 1000 мс — отдельный `WARNING slow request`; `/api/v1/health` уходит в DEBUG, чтобы пробы живости не заполняли поток. Middleware — чистый ASGI, а не `BaseHTTPMiddleware`: сокеты проходят сквозь него нетронутыми.
- Жизненный цикл WebSocket пишется целиком: отказ без пригодного токена и отказ «не пара» (WARNING с причиной), connect, disconnect с числом оставшихся слушателей в комнате, close с длительностью соединения, `WS room closed` при блоке или удалении аккаунта.
- В лог не попадают пароли, access/refresh-токены и заголовок `Authorization`; строка запроса пишется без query-части (рукопожатие сокета несёт токен именно там), а `SensitiveFilter` дописывает `[redacted]` к `token=`, `"password":` и похожие ключи в строках uvicorn.
- Покрыто набором `backend/tests/test_observability.py` (19 тестов), включая проверку, что заголовок-инъекция не может дописать вторую строку в лог.

## Деплой

`docker-compose.yml` поднимает `postgres` (16-alpine) и `backend`. При старте backend применяет миграции (`alembic upgrade head`), сеет данные (`python -m app.seed --if-empty`) и запускает `uvicorn`. Загрузки хранятся в именованном томе `befos_uploads`, БД — в `befos_pgdata`. Android-клиент собирается отдельно (`:app:assembleDebug`).

## Резюме архитектуры (для защиты проекта)

Один запрос — весь путь данных, без «магии»:

```
Android (Compose UI → ViewModel → Repository)
   ↓  REST (JSON, Ktor) / WebSocket
FastAPI (маршруты api/v1)
   ↓
Services (бизнес-логика, не знает про HTTP)
   ↓
Repositories (SQLAlchemy 2.0 async)
   ↓
PostgreSQL 16 (21 таблица)
```

- **Compatibility Engine** (`app/compatibility/`): семь взвешенных категорий —
  ценности (0.25), характер, интересы, коммуникация, образ жизни (по 0.15), досуг (0.10), цели (0.05);
  `Score = Σ normalize(component_i) × weight_i`, Σ weights = 1.0. Детерминирован: одинаковый вход →
  одинаковый результат; версия движка (`ENGINE_VERSION`) фиксируется в каждом ответе. Результат
  сопровождается объяснением (сильные стороны, отличия, общие интересы) — всё выводится из реальных
  данных пары. Это инженерная эвристика на основе анкет и теста, а не психологическая диагностика.
- **Recommendation Engine** (`app/recommendations/`): каталог активностей с сигналами
  `energy / social / cost`; оценка пары по интересам, досугу, образу жизни, городу и цели знакомства
  обоих. Каждая рекомендация несёт `score`, позицию и человекочитаемые `reasons`.
- **Realtime Chat**: WebSocket `/ws/chat/{match_id}` с JWT-авторизацией на рукопожатии и проверкой
  участия в матче. Надёжность доставки даёт REST (сообщение сохраняется в БД и транслируется второму
  участнику через `broadcast_to_match`); сокет отвечает за мгновенность (входящие, typing, read,
  presence). Клиент: keepalive-пинг 10 с, авто-переподключение с backoff, дедупликация по `id`.
- **Authentication**: JWT access + refresh; refresh хранится на сервере как SHA-256 и ротируется при
  каждом обновлении; на клиенте — DataStore, автообновление по 401 в Ktor `Auth`. WebSocket перед
  подключением получает свежий токен через probe `GET /users/me` (сокет не может сам инициировать refresh).
- **Security**: bcrypt для паролей; скользящий rate limiting (отдельный лимитер `/auth`); CORS без
  wildcard+credentials, в production — только https-origins; конфигурация отклоняет плейсхолдер- и
  короткие/совпадающие JWT-секреты при `ENVIRONMENT=production`; загрузки изображений перекодируются
  Pillow; SQL-инъекции исключены параметризацией SQLAlchemy; авторизация проверена IDOR-набором тестов.
