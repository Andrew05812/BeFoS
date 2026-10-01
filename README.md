# BeFoS

BeFoS — мобильное приложение для знакомств, в основе которого лежит **детерминированный, объяснимый алгоритм многокритериальной совместимости**. Вместо «свайпов по фото» BeFoS оценивает пару по семи категориям (ценности, характер, интересы, коммуникация, образ жизни, досуг, цели), показывает **почему** люди подходят друг другу, и рекомендует **совместные активности** на основе реальных данных обоих профилей.

> Алгоритм совместимости — это инженерная эввристика на основе анкет и теста. Он **не является** психологической или медицинской диагностикой.

## Ключевая цепочка продукта

```
РЕГИСТРАЦИЯ → ПРОФИЛЬ → ИНТЕРЕСЫ → ТЕСТИРОВАНИЕ → ПРОФИЛЬ СОВМЕСТИМОСТИ
→ АЛГОРИТМ → ПОДБОР → ПРОСМОТР → LIKE/PASS → MATCH → ЧАТ
→ АНАЛИЗ СОВМЕСТИМОСТИ → РЕКОМЕНДАЦИЯ СОВМЕСТНЫХ АКТИВНОСТЕЙ
```

Каждый шаг реализован «вживую»: без заглушек, без случайных процентов, без фейковых пользователей.

## Архитектура (обзор)

```
Android (Kotlin, Jetpack Compose, Material 3)
        │  REST (Ktor) + WebSocket
        ▼
FastAPI (Python, async)  →  Service  →  Repository  →  PostgreSQL
        │
        ├── Compatibility Engine (детерминированный, versioned)
        ├── Recommendation Engine (детерминированный)
        └── WebSocket-шлюз чата (JWT-авторизация)
```

- **Backend:** `backend/` — FastAPI + SQLAlchemy 2.0 (async) + asyncpg + Alembic + PostgreSQL 16.
- **Android:** `android/` — Kotlin 2.2, Jetpack Compose (Material 3), Ktor 3, Navigation Compose, DataStore, Coil. Чистая слоистая архитектура `data / domain / presentation`.

Подробности:
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — слои, модули, движок совместимости.
- [`docs/API.md`](docs/API.md) — все REST/WebSocket эндпоинты с форматами запросов и ответов.
- [`docs/DATABASE.md`](docs/DATABASE.md) — схема БД (21 таблица), миграции.

## Быстрый старт

### Вариант A — Docker (рекомендуется)

```bash
cp .env.example .env          # при необходимости отредактируйте секреты
docker compose up --build
```

Compose поднимет PostgreSQL и backend, автоматически применит миграции (`alembic upgrade head`), засеет каталоги и демо-данные (`python -m app.seed --if-empty`) и запустит API на `http://localhost:8000`.

Демо-вход (если `DEMO_ENABLED=true`): `demo@befos.app` / `Demo12345`.

Swagger UI: `http://localhost:8000/docs`.

### Вариант B — локально без Docker

**Backend** (Python 3.12):

```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
cp ../.env.example .env                                  # укажите DATABASE_URL на ваш PostgreSQL
alembic upgrade head
python -m app.seed            # каталоги + демо-пользователи
uvicorn app.main:app --reload --port 8000
```

**Android:** откройте `android/` в Android Studio (или соберите из CLI):

```bash
cd android
./gradlew :app:assembleDebug     # APK: app/build/outputs/apk/debug/app-debug.apk
```

Эмулятор обращается к хосту по `10.0.2.2`, поэтому backend на `localhost:8000` доступен приложению без дополнительных настроек (см. `API_BASE_URL` в `android/app/build.gradle.kts`).

### Тесты

**Backend** (35 тестов: 16 unit + 19 integration, требуют запущенный PostgreSQL и отдельную БД `befos_test`):

```bash
cd backend
pytest
```

**Android** (12 unit-тестов ViewModel):

```bash
cd android
./gradlew :app:testDebugUnitTest
```

## Технологии

| Слой | Стек |
|------|------|
| Backend | Python 3.12, FastAPI 0.115, Pydantic 2.10, SQLAlchemy 2.0 (async), asyncpg, Alembic 1.14 |
| БД | PostgreSQL 16 |
| Auth/Security | JWT (access + rotating refresh, refresh хранится как SHA-256 hash), bcrypt, CORS, sliding-window rate limiting, Pillow (перекодирование загружаемых изображений) |
| Realtime | WebSocket (`/ws/chat/{match_id}`) с JWT-авторизацией |
| Android | Kotlin 2.2, Jetpack Compose (BOM 2024.09), Material 3, Navigation Compose 2.8, Ktor 3.0, kotlinx-serialization, Coil 2.7, DataStore 1.1, Coroutines/Flow |
| Инфра | Docker Compose, pytest, JUnit4 + MockK + Turbine |

## Безопасность

- Секреты (`JWT_SECRET`, `JWT_REFRESH_SECRET`, `DATABASE_URL`) задаются только через `.env`; `.env` и `backend/.env` исключены из Git (`.gitignore`). В репозитории лежит только `.env.example` с плейсхолдерами.
- Пароли хранятся исключительно как bcrypt-хэш; в логах не выводятся пароли, access/refresh-токены и чувствительные пользовательские данные.
- Запросы защищены от SQL-инъекций (SQLAlchemy параметризует запросы), загрузки изображений — перекодированием через Pillow, авторизация WebSocket проверяет JWT (невалидный токен → close 1008).
- Применено скользящее rate limiting (в т.ч. отдельный лимитер для `/auth`).

## Структура репозитория

```
myapp/
├── backend/            # FastAPI-приложение
│   ├── app/
│   │   ├── api/v1/     # маршруты: auth, users, tests, discover, matches, chat, safety, health
│   │   ├── services/   # бизнес-логика
│   │   ├── repositories/
│   │   ├── models/     # SQLAlchemy-модели (21 таблица)
│   │   ├── compatibility/  # детерминированный движок совместимости
│   │   ├── recommendations/# движок рекомендаций активностей
│   │   ├── websocket/  # шлюз чата
│   │   ├── schemas/    # Pydantic-схемы
│   │   └── core/       # config, database, security, rate_limit, exceptions
│   ├── alembic/        # миграции
│   ├── tests/          # unit + integration
│   └── requirements.txt
├── android/            # клиент Jetpack Compose
│   └── app/src/main/java/app/befos/
│       ├── core/       # designsystem, network (Ktor), di, common
│       ├── data/       # model (DTO), remote (ApiService), repository, mapper
│       ├── domain/     # model, repository (интерфейсы)
│       └── presentation/  # экраны + ViewModel (auth, onboarding, test, discovery, matches, chat, compatibility, recommendations, profile, editprofile, publicprofile, settings, main, root, navigation)
├── docs/               # ARCHITECTURE.md, API.md, DATABASE.md
├── docker-compose.yml
└── .env.example
```

## Движок совместимости

Итоговый процент — взвешенная сумма нормированных оценок по категориям (детерминированно, без случайности):

```
Score = Σ ( normalize(component_i) × weight_i ),   Σ weight_i = 1.0
```

| Категория | Вес |
|-----------|-----|
| values (ценности) | 0.25 |
| personality (характер) | 0.15 |
| interests (интересы) | 0.15 |
| communication (коммуникация) | 0.15 |
| lifestyle (образ жизни) | 0.15 |
| leisure (досуг) | 0.10 |
| goals (цели) | 0.05 |

Один и тот же вход всегда даёт одинаковый результат. Помимо общего процента API возвращает разбивку по категориям, списки «сильных сторон» и «отличий», а также общие интересы — всё это выводится из реальных данных пары. Версия движка (`engine_version`) фиксируется в результате.

## Известное ограничение окружения

Запуск `./gradlew :app:testDebugUnitTest` **из пути, содержащего кириллицу** (проект расположен в `…\Рабочий стол\…`), на Windows завершается ошибкой `ClassNotFoundException` для всех тест-классов: форкаемый Gradle test-worker наследует `sun.jnu.encoding=Cp1251` и не может разрешить classpath с не-ASCII-символами. Те же тесты из ASCII-пути проходят (12/12). Обход: запускать unit-тесты из каталога с ASCII-путём (например, в CI). На сборку приложения (`assembleDebug`) это не влияет.
