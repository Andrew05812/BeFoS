# Релиз: сборка, подпись, проверка

Документ описывает, как из этого репозитория получается артефакт, который можно поставить на
телефон, и что обязано быть проверено до публикации. Раздел «Что здесь не сделано» в конце —
часть документа, а не оговорка: часть шагов требует вещей, которых в репозитории нет намеренно.

## 1. Два независимых условия выпуска

Выпуск break-ается об одно из двух, и они проверяются в разных местах:

1. **Конфигурация прода.** Куда приложение ходит за API и сокетом (`BEFOS_API_BASE_URL`,
   `BEFOS_WS_BASE_URL`). Ошиблись здесь — получаем бинарник, который устанавливается, открывается
   и не может выполнить ни одного запроса.
2. **Подпись.** Кем собран артефакт. Ошиблись здесь — артефакт не примет ни магазин, ни (`adb
   install`) телефон с уже установленным приложением от другого ключа.

Обе проверки стоят в `android/app/build.gradle.kts` и обе падают на сборке, а не на устройстве.

## 2. Инструменты

| Что | Версия на этой машине | Где взять |
| --- | --- | --- |
| JDK | 17 (компиляция), `keytool` есть и в 11 | Android Studio / отдельный JDK |
| Gradle | 9.3.1 через wrapper | `./gradlew` (`android/gradlew.bat` на Windows) |
| Android SDK | `compileSdk`/`targetSdk` 35, `minSdk` 26 | `android/local.properties` → `sdk.dir` |
| apksigner | `C:\Android\build-tools\35.0.0\apksigner.bat` | SDK → Build-Tools 35.0.0 |

Пути ниже в PowerShell (одной строкой, как принято в этом проекте), и в bash — где это удобно.

## 3. Ключ подписи

В репозитории нет ни keystore, ни паролей к нему: `.gitignore` закрывает `*.keystore` и
`keystore.properties` (исключения — `debug.keystore` и `keystore.properties.example`).
Выдумывать «значение по умолчанию» для прода нельзя: такой ключ попадёт в историю git и перестанет
быть ключом.

Создание (делать вне машины разработки, хранение — в менеджере паролей + резервная копия
файла ключа):

```powershell
keytool -genkeypair -v -keystore befos-release.keystore -alias befos -keyalg RSA -keysize 2048 -validity 10000
```

Потеря этого ключа означает, что обновления выпущенного приложения невозможны: магазин сверяет
подписывающий сертификат, а не название пакета. Восстановить его нечем, поэтому копия файла
ключа и паролей — часть релизной процедуры, а не «если останется время». При использовании Play
App Signing роль локального ключа — upload-ключ; его потеря меньше разрушительна, чем потеря
account key, и это надо решить до первого выпуска, а не после.

Файл `android/keystore.properties` (вне git) — четыре ключа:

```
storeFile=../befos-release.keystore
storePassword=…
keyAlias=befos
keyPassword=…
```

`storeFile` разрешается относительно `android/app`, то есть `../befos-release.keystore` — это
`android/befos-release.keystore`. Сборка проверяет этот файл целиком и падает сразу, а не через
четыре минуты после R8:

- `android/keystore.properties is missing storePassword, keyPassword. Either fill all four keys
  (see keystore.properties.example) or delete the file to build release unsigned.`
- `android/keystore.properties points at storeFile="C:\…\android\nope.keystore", which does not
  exist. Fix the path (it is resolved relative to android/app) or delete the file to build
  release unsigned.`

Оба текста получены прогоном на этой машине. Удаление файла возвращает сборку в состояние
«unsigned»: это не ошибка, а осознанный режим, чтобы release-ветка оставалась собираемой без
секретов.

## 4. Продуктовые адреса

Release-сборка обязана указать оба адреса, и проверка смотрит на граф задач, а не на набранные
слова: достаточно, чтобы в граф попал `assembleRelease`, `bundleRelease` или `packageRelease`
(туда попадают и простые `assemble`/`build`). Задачи, которые ничего не упаковывают
(`lintRelease`, `compileReleaseKotlin`), работают без продуктовых адресов.

Требования к значению: `https://` для API и `wss://` для сокета, хост не `10.0.2.2` /
`localhost` / `127.0.0.1` / `::1`, без `логин:пароль` внутри URL. Клиртект запрещён не на словах:
`android/app/src/main/res/xml/network_security_config.xml` разрешает его только локальным хостам,
поэтому адрес `http://` собрался бы, установился и падал бы на каждом запросе — это и есть причина
проверять на сборке.

```powershell
cd android; $env:BEFOS_API_BASE_URL="https://api.example.com/"; $env:BEFOS_WS_BASE_URL="wss://api.example.com/"; .\gradlew.bat :app:assembleRelease :app:bundleRelease
```

## 5. Что получается на выходе

```powershell
cd android; .\gradlew.bat :app:assembleRelease :app:bundleRelease
```

| Артефакт | Путь | Замерено |
| --- | --- | --- |
| APK (unsigned, без `keystore.properties`) | `app/build/outputs/apk/release/app-release-unsigned.apk` | 1 893 445 Б, сборка 4м05с |
| APK (подписанный) | `app/build/outputs/apk/release/app-release.apk` | 1 905 733 Б |
| AAB | `app/build/outputs/bundle/release/app-release.aab` | 4 631 598 Б |
| карта R8 | `app/build/outputs/mapping/release/mapping.txt` | есть; рядом `seeds.txt`, `usage.txt`, `resources.txt` |

Размеры и время — фактические результаты прогонов этой конфигурации (R8 включён:
`isMinifyEnabled` + `isShrinkResources`). `mapping.txt` обязана храниться вместе с выпущенным
артефактом: стектрейсы в Play Console без неё нечитаемы, а следующая сборка выдаёт другую.

## 6. Проверка подписи

```powershell
C:\Android\build-tools\35.0.0\apksigner.bat verify --print-certs --verbose app\build\outputs\apk\release\app-release.apk
```

Замеренный вывод на собранном артефакте (ключ — временный тестовый, созданный для проверки
процедуры и удалённый после неё):

```
Verified using v1 scheme (JAR signing): false
Verified using v2 scheme (APK Signature Scheme v2): true
Verified using v3 scheme (APK Signature Scheme v3): false
Signer #1 certificate DN: CN=BeFoS local signing test, OU=test, O=none, L=none, C=RU
Signer #1 certificate SHA-256 digest: 8e979e69b90e36386bfa64e547e13d0186e2419011c3bfbf4f6a7351d0874f88
```

`v1: false` — не поломка: v1 (JAR-подпись) нужен устройствам ниже Android 7.0, а `minSdk` здесь
26, поэтому достаточно v2. Отсюда практическое следствие: `jarsigner -verify` на этом же APK
честно говорит `jar is unsigned` — им проверять нельзя, только `apksigner`.

Признак того, что подпись не применилась, виден без инструментов: файл называется
`app-release-unsigned.apk`, а не `app-release.apk`.

## 7. Версия

`versionCode`/`versionName` — `android/app/build.gradle.kts`, `defaultConfig` (сейчас `1` /
`1.0.0`). `versionCode` обязан строго расти для каждого выпуска того же пакета: понижение
магазин не примет, а «переиздать то же число» — это не переиздание. Правило на каждый релиз:
поднять `versionCode`, поднять `versionName`, закоммитить изменение отдельным коммитом, чтобы по
истории было видно, какой сборке какая версия принадлежит.

## 8. Чек-лист перед публикацией

- [ ] `docker compose up -d --build backend` на целевом стенде; `/api/v1/health` отвечает `ok`,
      `environment` — `production`.
- [ ] `.env` прода: `ENVIRONMENT=production`, сильные и разные `JWT_SECRET`/`JWT_REFRESH_SECRET`,
      свой `DATABASE_URL`, `CORS_ORIGINS` только `https://` без `*`, `DEBUG=false`,
      `DEMO_ENABLED=false`. Каждое нарушение — контейнер не поднимается (`docs/OPERATIONS.md` §11).
- [ ] Миграции применены (`alembic upgrade head`), откат прогонян на копии по `docs/OPERATIONS.md`.
- [ ] Резервная копия и drill восстановления сделаны до выпуска, а не после (`docs/OPERATIONS.md` §6).
- [ ] Тесты: backend **183/183**, Android **131/131**, живой путь **64/64** (`CONTINUATION.md` §13).
- [ ] Сборка release прошла с реальными адресами; `apksigner verify --print-certs` показывает
      ожидаемый сертификат, а не тестовый.
- [ ] `mapping.txt` сохранена рядом с артефактом.
- [ ] На устройстве проверены: вход, онбординг, подбор, пара, чат (WebSocket работает именно с
      `wss://`-адресом), загрузка фото.

## 9. Публикация

Здесь процедура заканчивается там, где начинаются вещи, которых в репозитории нет: аккаунта
разработчика Play нет, поэтому загрузка AAB, internal-testing-трек и staged rollout **не
выполнены и не проверены**. Первый реальный прогон обязан добавить в этот файл фактические
строки: номер сборки, track, долю раскатки и окно, за которым смотрим на краши.

## 10. Откат релиза

Откатить установленное приложение «назад» нельзя: `versionCode` понизить нельзя, а пользователи
уже получили сборку. Поэтому откат = выпуск вперёд: `revert` коммита (не `reset`, история
сохраняется), поднятие `versionCode`, пересборка, повторная загрузка. Если поломка в данных —
сначала читается `docs/OPERATIONS.md` (playbook аварий), и только потом трогается клиент:
обратимая миграция предпочтительнее «починим потом».

## 11. Что здесь не сделано (по состоянию на этот прогон)

1. Боевого ключа подписи нет: артефакт в §6 подписан временным тестовым ключом, созданным только
   чтобы доказать, что процедура работает, и удалённым. Published-артефакт обязан быть подписан
   ключом, которого нет в этой истории git и на этой машине.
2. Аккаунта Play нет, значит путь публикации (загрузка AAB, треки, раскатка) не пройден.
3. Push-уведомления не настроены (нет FCM-консоли) — см. `CONTINUATION.md` §17; сборка без них
   работоспособна, realtime живёт при открытом приложении.
4. CI нет: сборка и проверки выше выполняются руками, и порядок шагов здесь — единственная
   защита от «соберём как-нибудь».
