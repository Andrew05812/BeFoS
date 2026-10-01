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
  - `designsystem/` — тема Material 3 (`BeFosTheme`), палитра, типографика, формы, переиспользуемые компоненты (`AsyncAvatar`, `ScoreRing`, `LoadingBox`, `MessagePane`, `scoreColor`).
  - `network/` — `ApiConfig` (базовые URL из `BuildConfig`), `befosJson` (конфигурация kotlinx-serialization), `createHttpClient` (Ktor + OkHttp, ContentNegotiation, WebSockets, bearer-авторизация с автообновлением токенов), `TokenStore` (DataStore), `SafeApiCall` (`ApiResult`, `apiCall`).
  - `di/` — `AppContainer` (ручная DI-граф: scope, TokenStore, HttpClient, ApiService, репозитории) и `beFosViewModel`-фабрика.
  - `common/` — `UiState` (Loading/Success/Error).
- **`data/`** — `model/Dtos.kt` (`@Serializable` DTO c `@SerialName`), `remote/ApiService` (типизированные вызовы, возвращают `ApiResult`), `mapper/` (DTO → domain), `repository/` (реализации доменных интерфейсов; `ChatRepositoryImpl` содержит устойчивый `ChatSocket` с автопереподключением).
- **`domain/`** — `model/Models.kt` (чистые модели) и `repository/Repositories.kt` (интерфейсы + `ChatEvent`).
- **`presentation/`** — по фиче: `ViewModel` (StateFlow) + Compose-экран. Навигация — `navigation/BeFosNavHost` + `Routes`; корневой роутинг (`splash → auth/onboarding/main`) решает `RootViewModel` на основе реального состояния сессии и заполненности профиля.

### Сетевое взаимодействие

- Все вызовы через `ApiService` возвращают `ApiResult<T>` — сетевые ошибки и не-2xx не бросают исключение, а превращаются в `ApiResult.Error(code, message)` (сообщение берётся из конверта ошибки backend).
- Автообновление access-токена настроено в Ktor `Auth` (bearer): при 401 выполняется `POST /auth/refresh`, токены обновляются в `TokenStore`.
- Чат: история/отправка — через REST (надёжная доставка и персистентность), realtime-события (входящие, typing, read, presence) — через WebSocket; входящие сообщения дедуплицируются по `id`.

### Тестирование

- Unit-тесты ViewModel (JUnit4 + MockK + Turbine + kotlinx-coroutines-test): валидация авторизации, поведение лайка/мэтча в подборе, дедупликация и отправка сообщений в чате.

## Деплой

`docker-compose.yml` поднимает `postgres` (16-alpine) и `backend`. При старте backend применяет миграции (`alembic upgrade head`), сеет данные (`python -m app.seed --if-empty`) и запускает `uvicorn`. Загрузки хранятся в именованном томе `befos_uploads`, БД — в `befos_pgdata`. Android-клиент собирается отдельно (`:app:assembleDebug`).
