# Changelog

All entries below are read out of the commit history on `production-readiness`; nothing here is
a planned release dressed up as a shipped one. `v0.1.0-beta` is the first tag this project has
had, so the entry is a grouped summary of the six days of work behind it (2026-10-01 →
2026-10-06) rather than an increment over a previous version. Per-stage detail, with the commits
that carry each change, is in [`docs/DEVELOPMENT_HISTORY.md`](docs/DEVELOPMENT_HISTORY.md).

Numbers are measurements, not aspirations: 191 backend tests, 131 Android unit tests and 64
live-journey checks, re-run on 2026-10-06 against this tree.

## [0.1.0-beta] — 2026-10-06

The first publishable state of BeFoS: a working product chain end to end — register → onboarding
→ 21-question test → compatibility profile → discovery → like/pass → match → realtime chat →
compatibility breakdown → joint activity recommendation — with no stubbed step in it.

### Added

- **Backend**: async FastAPI service with layered `api → service → repository` structure,
  Pydantic schemas, and 22 tables under Alembic migration control on PostgreSQL 16.
- **Compatibility engine** (`app/compatibility/`): deterministic, versioned scoring across seven
  weighted categories (values 0.25, personality / interests / communication / lifestyle 0.15,
  leisure 0.10, goals 0.05, weights validated to sum to 1.0), plus the explanation layer that
  returns strengths, differences and shared interests derived from the pair's own data.
- **Recommendation engine** (`app/recommendations/`): activities scored against both profiles,
  their city and their answers, and refreshed when either profile changes.
- **Discovery**: a stored, ranked deck read with cursor pagination, so a page stays stable while
  the pool changes, and a per-card `highlight` computed from the two profiles.
- **Realtime chat**: WebSocket gateway at `/ws/chat/{match_id}` authorised by JWT; REST-sent
  messages and read receipts broadcast into the pair's socket; a client-generated idempotency key
  makes a retried send store one message; a reconnect backfills the gap it missed.
- **Safety**: block, report, profile visibility, and account deletion that erases what describes
  the person.
- **Observability**: request id, latency and structured log lines for every request.
- **Android client**: Kotlin 2.2 / Jetpack Compose (Material 3) app in `data / domain /
  presentation` layering — auth, onboarding, test, discovery, matches, chat, compatibility,
  recommendations, profile, edit profile, public profile, settings — with session-aware routing
  that sends an unfinished profile back to onboarding instead of onto a dead screen.
- **Release pipeline**: signing configuration with an explicit key source, production URL gates
  that reject the emulator address at packaging time, R8 mapping retained, and a pre-publication
  checklist in `docs/RELEASE.md`.
- **Documentation**: `README.md` (English), `docs/ARCHITECTURE.md`, `docs/API.md`,
  `docs/DATABASE.md`, `docs/OPERATIONS.md`, `docs/RELEASE.md`, `DEMO.md`, plus
  `LICENSE`, `THIRD_PARTY_NOTICES.md` and `SECURITY.md`.
- **Screenshots**: ten real captures of the running app in `screenshots/`.

### Improved

- **Visual redesign (2026-10-02)**: a warm-ember token system and a component rebuild, then every
  screen migrated onto it — full-bleed discovery hero with a stacked next candidate, brand-led
  auth, onboarding stepper, question-counter test flow, animated category bars, pill chat
  composer, floating tab bar, duotone placeholder avatars, Compose previews for the design system.
- **Failure states**: the HTTP stack builds lazily and fails fast on an unreachable backend; a
  dead session is handled as a sign-out rather than a permanent error while a 5xx or a network
  failure keeps the session; skeletons became readable; a screen holding stale data now says the
  refresh did not land; the chat header reports the socket's real state.
- **Copy**: one voice across explanations, identity line that says one thing when only one thing
  was answered, refusals phrased as advice rather than as an HTTP status, and backend error text
  localised instead of leaking English strings onto Russian screens.
- **Performance**: N+1 removed from the discovery feed and the match list; the two hot reads that
  scanned a whole table now scan a page; discovery reads a stored deck instead of re-ranking the
  pool per request; query-count ceilings asserted by tests.
- **Accessibility**: the keyboard/IME matrix measured at 320/360/393 dp and font scale up to 1.3
  (report dialog, sign-in form's last row, pinned onboarding button), icon-only controls given
  semantics, text-carrying accents solved against the pixels behind them, and interest chips made
  geometrically stable — a tap moves none of its six neighbours, the touch target is 48 dp.

### Fixed

- **Compatibility consistency**: one pair of answers now yields one percent in every process; a
  pair displays the percent it has rather than the one it met on; `0..100` is enforced by the
  response models; the seeded demo pair carries the number the engine gives it.
- **Session**: the bearer token Ktor cached at first load — which made an in-process account
  switch keep sending the previous user's `Authorization` header — is now taken from the live
  session at the last moment before the request leaves.
- **Data quality**: a city written as spaces is refused rather than stored as nothing; an account
  that never answered the test is nobody's discovery card; repeated social writes and the
  remaining check-then-insert races in the test engine are settled by database constraints.
- **Test screen**: the question header no longer sits under the status bar (the screen is not a
  `Scaffold`, so no inset was applied to it).

### Security

- The authentication rate limiter no longer trusts a client-supplied `X-Forwarded-For`.
- The JWT in a WebSocket handshake never reaches the log; socket handshake **and** every frame in
  an already-open socket re-check authorisation, so a socket cannot outlive its pair or a block.
- An oversized or malformed image is refused as input instead of surfacing as a 500; the request
  body is read to a ceiling rather than buffered whole.
- Production configuration validation extended until no setting can silently undo another:
  placeholder/short/duplicated JWT secrets, wildcard or `http://` CORS origins, `DEBUG=true`,
  the demo account, the database password this repository ships, and an unrecognised value of
  `ENVIRONMENT` itself all refuse to start.
- Account deletion became a data lifecycle rather than a visibility flag: test answers, results,
  compatibility vector, activity affinity and deck entries are erased, profile fields are set to
  values no form can produce, and uploaded photo rows **and files** are removed — because
  `/uploads` is public static. Reports deliberately survive.
- A block became a server-side wall: the pair and its history are removed, both directions get
  404 on history and send, and the behaviour is pinned by tests, including an identifier sweep
  covering the object-level routes that had no guard test.
- `.gitignore` closed against what a public repository must never carry, and the development
  database now publishes on `127.0.0.1:5432` only instead of every interface.

### Reliability

- Backup procedure with a **verified restore drill** (`pg_dump` → fingerprint → restore into a
  scratch database → compare → drop), documented with the numbers of the run that proved it.
- Health endpoints split between liveness and database-backed readiness, so "process up" is not
  reported as "can serve"; a database that is not there can no longer pretend to be.
- Connection-pool sizing, overflow and `pool_recycle` justified against the Postgres
  `max_connections` of the stand, in `docs/OPERATIONS.md`.
- Migrations applied on container start, `alembic check` clean against the models, and every
  revision carrying a working downgrade.
- Chat send idempotency and reconnect backfill, so a lost response or a dropped socket does not
  duplicate or lose a message.

### Known limitations

See *Project Status* in [`README.md`](README.md) for the full list. The ones that matter most to
an evaluator: there is no deployed instance and no CI (every number above was measured by hand),
push notifications are designed but unimplemented, reports have no in-app reader, unblocking is a
SQL operation, backups have no scheduler and there is no point-in-time recovery, `/uploads` is
unauthenticated static, and Android unit tests must be run from an ASCII path on Windows because
the Gradle test worker cannot resolve a non-ASCII classpath.

[0.1.0-beta]: https://github.com/Andrew05812/BeFoS/releases/tag/v0.1.0-beta
