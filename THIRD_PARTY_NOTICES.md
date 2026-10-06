# Сторонние компоненты

BeFoS — проприетарная работа (см. `LICENSE`). Перечисленные ниже компоненты принадлежат их
правообладателям и остаются на собственных условиях; ничего в этом репозитории не даёт вам
дополнительных прав на них.

Как составлен этот список — чтобы его можно было воспроизвести, а не принять на веру:

- Лицензии backend'а прочитаны из установочных метаданных запиненных версий в
  `backend/.venv` (`License` / `License-Expression` / классификаторы `License ::`); проверка
  перезапущена 2026-10-06 на версиях из таблиц ниже.
- Лицензии мобильной части прочитаны из блока `<licenses>` POM-артефакта: из локального кэша
  Gradle, где POM был, и из вышестоящего Maven-репозитория, где его не было.
- Уведомление о шрифте извлечено из таблицы `name` (nameID 13) самого прилагаемого TrueType-файла
  и перенесено в `backend/app/seed_data/fonts/LICENSE.DejaVu` дословно.
- Внизу те версии, которые репозиторий пинит в `backend/requirements.txt` (runtime — единственное,
  что ставит образ), `backend/requirements-dev.txt` (тестовый инструментарий, который в образ не
  попадает) и `android/gradle/libs.versions.toml`. Политика зависимостей и аудит по базе
  уведомлений — в [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).

## Приложено в этом репозитории

| Что | Где | Лицензия |
|---|---|---|
| DejaVu Sans Bold 2.37 | `backend/app/seed_data/fonts/DejaVuSans-Bold.ttf` | Bitstream Vera Fonts Copyright + Arev Fonts Copyright; изменения DejaVu переданы в public domain. Полный текст — `LICENSE.DejaVu` рядом со шрифтом |
| Gradle wrapper 9.3.1 | `android/gradle/wrapper/gradle-wrapper.jar` | Apache License 2.0 (текст внутри jar) |

DejaVu нужен для одного: сид рисует демонстрационные карточки профилей через Pillow, а у
встроенного битмап-шрифта Pillow нет кириллицы (`backend/app/seed_data/placeholder_images.py`).
В APK Android этот шрифт не попадает.

Всё остальное двоичное в дереве создано самим проектом: демонстрационные снимки рисуются во время
сида через Pillow, а иконка приложения — рукописный векторный путь
(`android/app/src/main/res/drawable/ic_launcher_foreground.xml`). Сторонних изображений, иконок и
шрифтов в репозитории нет.

## Backend — прямые зависимости

Runtime (`backend/requirements.txt`, единственный файл, который читает сборка образа):

| Пакет | Версия | Лицензия |
|---|---|---|
| fastapi | 0.115.6 | MIT |
| uvicorn[standard] | 0.34.0 | BSD-3-Clause |
| pydantic | 2.10.4 | MIT |
| pydantic-settings | 2.7.0 | MIT |
| email-validator | 2.2.0 | Unlicense (public domain) |
| python-multipart | 0.0.32 | Apache-2.0 |
| SQLAlchemy[asyncio] | 2.0.36 | MIT |
| asyncpg | 0.30.0 | Apache-2.0 |
| alembic | 1.14.0 | MIT |
| greenlet | 3.1.1 | MIT |
| PyJWT | 2.15.1 | MIT |
| bcrypt | 4.2.1 | Apache-2.0 |
| pillow | 12.3.0 | MIT-CMU (разрешительный текст в стиле CMU/HPND) |

Тестовый инструментарий (`backend/requirements-dev.txt`, не в образе):

| Пакет | Версия | Лицензия |
|---|---|---|
| pytest | 9.1.1 | MIT |
| pytest-asyncio | 1.4.0 | Apache-2.0 |
| httpx | 0.28.1 | BSD-3-Clause (тесты и скрипт живого пути) |

## Backend — транзитивные пакеты, разрешённые этими пинами

annotated-types MIT · anyio MIT · certifi MPL-2.0 · click BSD-3-Clause · colorama
BSD-3-Clause · dnspython ISC · h11 MIT · httptools MIT · httpcore BSD-3-Clause · idna
BSD-3-Clause · iniconfig MIT (тесты) · Mako MIT · MarkupSafe BSD-3-Clause · packaging
Apache-2.0 OR BSD-2-Clause · pluggy MIT (тесты) · Pygments BSD-2-Clause (тесты) · pydantic_core
MIT · python-dotenv BSD-3-Clause · PyYAML MIT · starlette BSD-3-Clause · typing_extensions
PSF-2.0 · uvloop Apache-2.0 OR MIT · watchfiles MIT · websockets BSD-3-Clause

`uvloop` достижим только через `uvicorn[standard]` на не-Windows-платформе, поэтому набор,
разрешённый в контейнере, и набор виртуального окружения на Windows различаются; аудит в
[`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md) по этой причине читает граф самого контейнера.

## Android-клиент — зависимости

| Группа | Артефакты (версия) | Лицензия |
|---|---|---|
| AndroidX | core-ktx 1.13.1, activity-compose 1.9.2, lifecycle 2.8.6, navigation-compose 2.8.5, datastore-preferences 1.1.1 | Apache License 2.0 |
| AndroidX Compose | BOM 2024.09.03 → ui / ui-graphics / ui-tooling / foundation / animation / material3 1.3.0 / material-icons-extended 1.7.3 | Apache License 2.0 |
| Ktor | ktor-client-core / -okhttp / -auth / -content-negotiation / -websockets / -logging 3.0.1, ktor-serialization-kotlinx-json 3.0.1 | Apache License 2.0 |
| kotlinx | kotlinx-serialization-json 1.7.3, kotlinx-coroutines-android 1.8.1 | Apache License 2.0 |
| Coil | coil-compose 2.7.0 | Apache License 2.0 |
| Тестирование | mockk 1.13.13, turbine 1.1.0, kotlinx-coroutines-test 1.8.1, ktor-client-mock 3.0.1, androidx.test.ext:junit 1.2.1, espresso-core 3.6.1, compose ui-test-junit4 | Apache License 2.0 |
| JUnit | junit 4.13.2 | Eclipse Public License 1.0 |

## Здесь не распространяется, но присутствует при сборке или запуске

- **Gradle 9.3.1, Android Gradle Plugin 9.1.1, Kotlin 2.2.10, Android SDK / эмулятор** —
  инструмент сборки. Их скачивает тулчейн, они не закоммичены, и каждый живёт по своей лицензии
  (Android SDK — по своему лицензионному соглашению).
- **`python:3.12-slim`** — базовый образ backend'а, берётся с Docker Hub; у него свои CPython и
  пользовательская часть Debian со своими лицензиями.
- **`postgres:16-alpine`** — образ базы данных, берётся с Docker Hub; PostgreSQL распространяется
  под PostgreSQL Licence, и образ несёт её текст вместе с собой.

## Вопросы к этому списку

Лицензии меняются между релизами. Если вы читаете версию BeFoS, чьи пины отличаются от таблиц
выше, — перезапустите проверку, а не доверяйте этому файлу: источники пинов названы в начале, и
тот же поиск применим к любой версии.
