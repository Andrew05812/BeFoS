# BeFoS — CONTINUATION.md

Документ для нового разработчика / AI-агента, продолжающего проект **без истории предыдущих сессий**.
Состояние актуально на 2026-10-02, после завершения RELEASE PASS (коммиты `c67fecc…c2a3ae0`, 8 коммитов, дерево чистое).

## 1. Что такое BeFoS

Мобильное приложение для знакомств с **детерминированным объяснимым алгоритмом многокритериальной совместимости** (ВКР). Не «свайпы по фото»: пара оценивается по семи категориям, показывается *почему* люди подходят друг другу и *что им делать вместе* (рекомендации совместных активностей). Все данные реальные: нет фейковых процентов, случайных объяснений, заглушек.

> Важно для формулировок: алгоритм — инженерная эвристика на анкетах и тесте, **не психологическая/медицинская диагностика**. Название продукта строго «BeFoS».

Цепочка продукта: регистрация → онбординг (профиль + интересы + цели) → тест 21 вопрос → профиль совместимости → подбор (discovery) → like/pass → взаимный like = match → realtime-чат → анализ совместимости пары → рекомендации встреч → безопасность (block/visibility/report) → настройки.

## 2. Архитектура (фактическая)

```
Android (Kotlin 2.2, Jetpack Compose Material 3)
        │  REST (JSON, Ktor) + WebSocket
        ▼
FastAPI 0.115 (Python 3.12, async)
  API (routers /api/v1) → Services → Repositories → PostgreSQL 16 (SQLAlchemy 2.0 async + asyncpg)
        ├── Compatibility Engine (app/compatibility, versioned, детерминированный)
        ├── Recommendation Engine (app/recommendations)
        └── WS-шлюз чата (app/websocket, JWT на handshake)
```

Принцип: тонкие роутеры, логика в сервисах, SQL в репозиториях; слои не перепрыгивают друг друга. Подробности: `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DATABASE.md` (21 таблица + alembic_version).

## 3. Android stack

- `android/` — Kotlin 2.2, Compose BOM 2024.09 (Material 3), Navigation Compose 2.8, Ktor client 3.0.1 (OkHttp engine), kotlinx-serialization, Coil 2.7, DataStore 1.1, Coroutines/Flow; тесты JUnit4 + MockK + Turbine.
- Слои `data / domain / presentation`; DI — ручная `AppContainer` (`core/di`), ViewModel через фабрику `beFosViewModel`.
- **Дизайн-система** (`core/designsystem/Components.kt`) — единственные UI-примитивы: `AppButton`, `AppTextField`, `AppCard`, `AppTopBar`, `SectionHeader`, `LoadingState`, `ErrorState`, `EmptyState`, `MessagePane`, `Avatar`, `CompatibilityScore`, `CompatibilityBadge`, `InterestChip`, `MessageBubble`, `MatchCard`, `ProfileCard`, `scoreColor`. Все 13 экранов уже мигрированы — новых дублей не создавать.
- Сеть: `ApiResult`-конверт (ошибки не исключения), Ktor `Auth` bearer с авто-refresh; WebSocket-клиент с keepalive-пингом 10 с (`pingIntervalMillis = 10_000`) — оборванный TCP обнаруживается по pong-таймауту и переподключается (цикл `ChatSocket`, события через `tryEmit`).
- Root-маршрутизация (`RootViewModel`): splash → auth/onboarding/main по состоянию сессии и заполненности профиля.
- Доступность: contentDescription у иконок, цели ≥48dp, haptics при фиксации свайпа-решения.

## 4. Backend stack

Python 3.12, FastAPI, Pydantic 2.10 + pydantic-settings, SQLAlchemy 2.0 async, asyncpg, Alembic 1.14, bcrypt, PyJWT (access + rotating refresh), slowapi-подобный sliding-window rate limit, Pillow (перекодирование изображений), pytest (asyncio_mode=auto).

Структура: `app/api/v1/*` (auth, users, tests, discover, matches, chat, safety, health), `app/services/*`, `app/repositories/*`, `app/models/*`, `app/schemas/schemas.py`, `app/core/*` (config, database, security, rate_limit, exceptions), `app/compatibility/`, `app/recommendations/`, `app/websocket/`.

## 5. Docker

Основной runtime. `docker compose up --build` поднимает `befos_postgres` (16-alpine) и `befos_backend`; при старте — `alembic upgrade head` + `python -m app.seed --if-empty` (справочники + 50 демо-пользователей + демо-матчи; детерминированный `RNG_SEED=20240501`). API: `http://localhost:8000`, Swagger `/docs`, health: **`/api/v1/health`** (корневого `/health` нет). Тома: `befos_pgdata`, `befos_uploads`. Эмулятор Android ходит на host через `http://10.0.2.2:8000`.

## 6. Database

PostgreSQL 16, 21 доменная таблица (users, profiles, photos, interests/user_interests, test_questions/test_options/test_answers/test_results, compatibility_profiles, likes, passes, matches, messages, message_reads, activities, recommendations, blocks, reports, refresh_tokens + alembic_version). Индексы на горячих путях (`ix_likes_from/to_user_id`, уникальность `uq_like_pair`, CHECK `from<>to`). Миграции — Alembic; актуальная head в `backend/alembic/`.

## 7. Authentication

Email+пароль → bcrypt-хэш. JWT access (короткий) + refresh (хранится как SHA-256, ротация при обновлении, `POST /auth/refresh` — плоский TokenPair без конверта). Bearer на REST; WebSocket авторизуется `?token=` на handshake (невалидный → close 1008). Android: токены в DataStore, авто-refresh в Ktor Auth; перед WS-подключением `ChatSocket` делает probe `GET /users/me`, чтобы ротировать токен (socket сам refresh не может).

## 8. Compatibility Engine

`app/compatibility/`: `traits.py` — 7 категорий (Ценности, Личность, Общение, Образ жизни, Досуг, Интересы, Цели знакомства) с компонентами; `weights.py` — `DEFAULT_WEIGHTS` (values .25; personality/interests/communication/lifestyle .15; leisure .10; goals .05; сумма 1.0), `ENGINE_VERSION`. Формула `Score = Σ normalize(component_i) × weight_i` — полностью детерминирована. Результат хранится в `compatibility_profiles.vector` (JSON). API возвращает процент, разбивку по категориям, сильные стороны, отличия, общие интересы. **Алгоритм и веса в этом прогоне менять нельзя** (заморожено мандатом).

## 9. Discovery + «Почему показан»

`discovery_service.feed()` — batch-загрузка (профили/фото/векторы одним запросом на пул; regression-тест `test_perf_discovery.py` ограничивает ≤25 SQL на ленту, фактически ~9). Карточка несёт `highlight: str | None` — однострочное объяснение, производное только от реальных данных, по приоритету:
1. ≥2 общих интереса → «Общие интересы: a, b»; ровно 1 → «Общий интерес: X» (ярлык, а не
   предложение: множественное название интереса ломает любую фразу вида «нравится …»);
2. совпадение города (без учёта регистра) → «Из вашего города»;
3. категория ≥70% → «Высокое совпадение: {категория} — {percent}%»;
4. иначе `null` (строка скрывается).
Никаких внутренних имён компонентов и случайности.

## 10. Recommendation Engine

`app/recommendations/` — каталог `activities` с сигналами `energy/social/cost`; скор на основе интересов/досуга/образа жизни/города/целей обоих; каждая рекомендация: `score`, `position`, человекочитаемые `reasons` — все с заглавной буквы, по одной на категорию («Общий интерес — Велосипед», «Проходит в вашем городе», «У вас близкий ритм жизни»…). Экран показывает блок «ПОЧЕМУ ПОДХОДИТ», кнопка «Предложить в чате» отправляет в пару реальное сообщение (`Идея для нас: … Что скажете?`) и только после успешной отправки фиксирует выбор; при ошибке сети выбор откатывается. Проверено на устройстве и покрыто `RecommendationsViewModelTest` (3 теста).

## 10.1 UI-копирайт ошибок

Контракт API англоязычный, продукт русскоязычный. Шов — `core/network/BackendErrorText.kt`: известные сообщения переводятся, параметризованные (`Image exceeds N MB limit.`) ловятся по константному префиксу, незнакомые — падают на русскую формулировку по machine-коду (`unauthorized`, `validation_error`, …) и только затем по HTTP-статусу. Английский текст бэкенда не показывается ни в одном из 23 мест UI; транспортные сбои локализованы там же (`friendlyNetworkMessage`/`defaultHttpMessage`). Покрыто `BackendErrorTextTest` (5 тестов).

## 11. Realtime Chat

REST — надёжная запись (история/отправка/прочтение), WebSocket — доставка `message/typing/read/presence`; REST-события backend ретранслирует в сокет пары (`broadcast_to_match`), поэтому второй клиент видит всё без перезагрузки. Входящие дедуплицируются по `id`. Прочтение показано бейджем «прочитано»: он ставится только по факту прочтения **парой** — REST-квитанция читается с `exclude_user`, чтобы клиент не получал «прочитано» о собственном действии, а свежесозданное сообщение отдаётся с `is_read=false`. Оффлайн: баннер «Подключение… переподключаемся» занимает отдельную строку (над списком он закрывал первое сообщение), после восстановления соединения переподключение **автоматическое** (проверено на устройстве, фикс `22b7635`). Время в пузырях — `java.time` с переводом UTC → локальная зона; обрезка ISO-строки показывала серверные часы.

## 12. Security (текущий уровень)

- IDOR: все эндпоинты с чужими ID проверяют membership/принадлежность; набор `backend/tests/test_idor_authorization.py` (6 тестов: чтение/отправка/read/compatibility/recommendations/select чужого match → 403/404; партнёр доступ сохраняет).
- Config-гарды production (`core/config.py` model_validator): плейсхолдер-секреты, короткие секреты, совпадение JWT_SECRET/REFRESH, CORS `*` и `http://` — приложение не стартует.
- Rate limiting (отдельный лимитер /auth), JWT в query только для WS, секреты только в `.env` (в git — `.env.example` с плейсхолдерами), в логи — без паролей/токенов.
- Загрузки изображений — перекодирование Pillow.
- Release-бинарник не может содержать http-адрес эмулятора: без `BEFOS_API_BASE_URL`/`BEFOS_WS_BASE_URL` сборка падает (fail-fast).
- Протухшая сессия не является тупиком: `bearer`-плагин при неудачном refresh очищает токены, `TokenStore.clear()` публикует событие `signedOut`, а `BeFosNavHost` по нему уводит на экран входа с очисткой стека. Без этого пользователь оставался на «Сессия истекла. Войдите снова.» с кнопкой «Повторить», которая не может сработать никогда. Проверено на устройстве: ротация `JWT_SECRET` в `.env` + перезапуск backend → тап по вкладке «Профиль» → экран входа с предзаполненным email → повторный вход возвращает в подбор.

## 13. Текущие результаты тестов (воспроизводимо)

| Набор | Команда | Результат |
|---|---|---|
| Backend unit+integration | `cd backend && ./.venv/Scripts/python.exe -m pytest -q` (нужен запущенный `docker compose up -d`; тестовая БД `befos_test`) | **62/62** |
| Живой journey | `PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe backend/e2e_journey.py` | **46/46** |
| Android unit | `cd android && ./gradlew :app:testDebugUnitTest` — **только из ASCII-пути** (см. §17.1) | **31/31** |
| Release | `BEFOS_API_BASE_URL=… BEFOS_WS_BASE_URL=… ./gradlew :app:assembleRelease :app:bundleRelease` | APK 1.88 МБ + AAB 4.59 МБ (R8); без `android/keystore.properties` — `app-release-unsigned.apk`, что и проверялось |
| On-device E2E | эмулятор `befos_avd` | пройден полностью, см. §14 |

## 14. On-device E2E flow (как повторять)

AVD `befos_avd` (540x1140, density 220), запуск headless:
`powershell Start-Process emulator.exe -ArgumentList '-avd','befos_avd','-no-window','-gpu','swiftshader_indirect','-accel','on','-no-snapshot-load','-no-snapshot-save' -WindowStyle Hidden`.

Пройденный сценарий: регистрация нового пользователя (email+пароль; чистая установка открывает именно форму регистрации) → онбординг 3 шага (дата строго `ГГГГ-ММ-ДД`) → тест 21 вопрос → профиль совместимости → подбор (карточка со строкой «Почему показан: …») → like → «ВЗАИМНЫЙ ЛАЙК» с аватаром пары и раскрытием процента → чат: отправка, realtime-ответ, «прочитано» → совместимость (7 категорий, по одной причине на категорию) → рекомендации («Предложить в чате» → сообщение в чате) → список пар → logout → повторный login (root-роутинг в MAIN) → офлайн: ErrorState «Не удалось загрузить пары»+«Повторить» (проверено остановкой контейнера backend и восстановлением по «Повторить»), пустое состояние «Пока никого нет»+«Обновить», пустые пары «Пар пока нет»+«Смотреть анкеты», баннер WS → битое фото (файл временно убран с сервера) → брендовый monogram-fallback, без broken-image → responsive: `adb shell wm density 270` (320dp) и `240` (360dp), reset — `wm density reset`; текст: `settings put system font_scale 1.15/1.3` и возврат в `1.0` (клиппинга нет) → state: вкладка MAIN сохраняется через `rememberSaveable` (back из редактора возвращает на «Профиль», а не на «Подбор»), лента подбора помнит позицию (2/20) при уходе в чат и обратно.

Отдельно проверены «вторые» случаи, которые обычно и ломаются: **повторный match в той же сессии** (второй «ВЗАИМНЫЙ ЛАЙК» с другим именем и другим процентом, CTA «Написать сообщение» открывает чат именно этой пары) и **match, начатый партнёром**, пока main-демонстратор смотрит ленту — пушей нет (осознанно), поэтому событие честно появляется в списке пар при открытии вкладки (`refreshSilently`), без выдуманного realtime-диалога. **Протухшая сессия**: после ротации JWT-секрета тап по вкладке уводит на экран входа (см. §12), а не оставляет «Повторить» в вечной ошибке. **Release-сборка**: `app-release-unsigned.apk`, подписанный локальным debug-ключом только для установки на эмулятор, проходит тот же путь (логин → лента) — R8 не ломает сериализацию и навигацию.


Взаимный match для демо с одного устройства: второй аккаунт создаётся скриптом через API и «лайкает» устройства-пользователя (пример — §15 шаг 10 в DEMO.md).

Windows/adb-подводные камни (экономия времени):
1. `adb shell input text` не печатает кириллицу — тестовые данные вводить латиницей.
2. Git-Bash ломает `/sdcard/...` пути → `export MSYS_NO_PATHCONV=1`; цель `adb pull` — в Windows-формате (`C:/...`).
3. Состояние shell не сохраняется между вызовами — хелперы надо `source ./…sh` в каждой команде.
4. После загрузки эмулятора у app-контента может отсутствовать маршрут в per-UID таблице `wlan0` (все соединения «Network is unreachable» при валидном Wi-Fi). Лечение: `adb shell svc wifi disable; sleep 2; adb shell svc wifi enable`.
5. `uiautomator dump` иногда отдаёт устаревший XML при анимациях — перетирать `/sdcard/ui.xml` перед дампом.
6. Мягкая клавиатура перехватывает тапы по кнопкам под ней: закрывать `keyevent 4` (BACK закрывает IME; второй BACK закрывает экран!) или `keyevent 111` (ESC).

## 15. Release build & signing

- Debug: `assembleDebug`, URL по умолчанию `http://10.0.2.2:8000/` (buildConfigField в debug-блоке).
- Release: требует env `-P`-свойств `BEFOS_API_BASE_URL`/`BEFOS_WS_BASE_URL` (только https/wss по смыслу; иначе GradleException с внятным текстом).
- Подпись: `android/keystore.properties` (вне git, см. `keystore.properties.example`: storeFile/storePassword/keyAlias/keyPassword + команда keytool). Без файла release собирается **unsigned** (`app-release-unsigned.apk`) — реальные секреты в репозитории отсутствуют намеренно и выдумывать их нельзя.

## 16. Production configuration

`.env` (не в git): `ENVIRONMENT=production`, сильные `JWT_SECRET`/`JWT_REFRESH_SECRET` (≥32, разные), `DATABASE_URL`, `CORS_ORIGINS=https://…` (без `*` и `http://`), `DEMO_ENABLED=false`. При нарушении любого правила приложение не стартует (тесты `test_security_config.py`). HTTPS терминировать на reverse proxy (в репо не входит).

Ловушка, из-за которой «смена секрета ничего не делает»: `docker-compose.yml` интерполирует `${JWT_SECRET}`/`${JWT_REFRESH_SECRET}` из **корневого** `.env`, а `backend/.env` читает только процесс, запущенный вне Docker. При пересоздании контейнера (`docker compose up -d`) compose подхватывает значения из корня; `--force-recreate` обязателен, иначе контейнер продолжит жить со старым окружением. `ACCESS_TOKEN_EXPIRE_MINUTES` в environment-блок compose не проброшен — в контейнере действует дефолт 30 минут.

## 17. Известные ограничения (честно)

1. **ASCII-путь для Android unit-тестов на Windows**: из кириллического пути Gradle test-worker падает (`sun.jnu.encoding=Cp1251`). Обход — копия проекта в ASCII-путь (например `<local-project-path>/befos_asciitest`, синхронизация `robocopy /MIR /XD build .gradle local.properties`). На сборку не влияет.
2. **Нет push-уведомлений (FCM)** — realtime работает при открытом приложении. Осознанно вне объёма.
3. **Нет офлайн-кэша сообщений**: при недоступном backend чат показывает пустое состояние + баннер переподключения; история восстанавливается после подключения. (Не добавлять без отдельного решения.)
4. Подписанный релизный артефакт не собран — нет реальных signing-credentials.
5. Git remote не настроен — push не выполнялся.
6. Сокет чата живёт в app-scope до конца процесса (закрытие per-chat не реализовано; на UX не влияет).
7. Демо-данные сидируются в БД (`--if-empty`); для «чистого» прода — отключить demo и не сидировать домен.
8. **Холодный старт зависит от типа сборки, а не от кода приложения**: на одном и том же эмуляторе debug-APK — `Displayed +31s662ms` (JIT без AOT/R8, `performTraversals` компилируется ~12 с), release-APK — `am start -W` TotalTime 6.1 с в первый запуск и 4.6 с во второй. Тяжёлый HTTP-стек (OkHttp/TLS) уже вынесен в `by lazy` в `AppContainer`, чтобы не платить его цену в `Application.onCreate`; дальнейший разгон — это baseline profile + release, а не правки приложения.

## 18. Возможные следующие задачи (не начаты, по убыванию ценности)

- Push-уведомления (FCM) о match/сообщениях — отдельный мандат.
- Офлайн-кэш истории чата (Room) + queued send.
- Загрузка фото профиля с устройства (фото отдаются API, UI камеры/галереи минимален).
- CI (GitHub Actions): pytest + journey + unit-тесты из ASCII-checkout, сборка release с секретами из CI-vault.
- Модерация-панель / админ API.
- Пагинация/курсор для длинной истории сообщений, индикатор «печатает…» в списке пар.
- Локализация (сейчас UI только русскоязычный).

## 19. Регламент для продолжающего

- Рабочий код менять только под конкретную обнаруженную проблему; не рефакторить без нужды; алгоритм совместимости и UI не трогать «на всякий случай».
- Не добавлять FCM/офлайн-кэш молча — это пункты §18.
- Коммиты логические, дерево чистое; секреты в git никогда; не называть «лимитацией» невыполненную задачу.
- Перед «готово»: pytest 62, journey 46, unit 31, сборки, и — для UI/чат-фич — реальный прогон на эмуляторе.
