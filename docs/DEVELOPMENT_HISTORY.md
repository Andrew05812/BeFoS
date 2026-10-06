# Development history

Everything here is read out of `git log` on the `production-readiness` branch. No dates are
invented, and no stage is claimed that has no commits behind it. Reproduce any row:

```bash
git log --reverse --format='%ad %s' --date=short      # the whole timeline
git log --since=2026-10-04 --until=2026-10-05 --oneline
git rev-list --count HEAD                             # history length
```

The project was built in six days (2026-10-01 → 2026-10-06). The counts below are a snapshot
taken at 2026-10-06 02:39 with `git rev-list --count HEAD` = 125; commits made after that
moment — including the ones that publish this document — are not counted in the rows, so
re-derive them with the commands above before quoting a total.

The history is kept whole rather than squashed into a showcase: the early versions, the
redesign, the bugs found by breaking the app and the fixes they produced are all addressable by
commit.

Every hash quoted here is read from the published branch. The identity and local-path
sanitization pass rewrote all 128 commits — messages, author dates, committer dates, order and
count stayed identical, and the tree of every commit is byte-for-byte the same — so a hash from
a note written before that pass addresses a different commit object than the same commit does
now.

## Timeline

| Stage | Dates (from git) | Commits | What changed |
|---|---|---|---|
| Foundation | 2026-10-01 | 4 | FastAPI backend — 88 files, 6 663 insertions — with the deterministic compatibility engine, async SQLAlchemy, Alembic migrations and Docker Compose; the Jetpack Compose client — 75 files, 6 003 insertions; the first ViewModel unit tests; `README` + `ARCHITECTURE`/`API`/`DATABASE`. |
| Realtime, auth rules, first performance pass | 2026-10-02 | 14 | Chat broadcast over WebSocket and recovery after an abrupt server loss; session-aware root routing and refresh-token rotation; fail-fast production config that rejects wildcard/`http://` CORS origins; the IDOR suite; N+1 queries removed from the discovery feed and the match list; a real release-signing mechanism with the emulator URL split off the production one; handover and demo documents. |
| Visual redesign (v2) | 2026-10-02 | 12 | The warm-ember token set and a component rebuild, then every screen migrated onto it: full-bleed discovery hero with a stacked next candidate, brand-led auth, onboarding stepper, question-counter test flow, animated category bars, pill chat composer, floating tab bar, duotone placeholder avatars, Compose previews, and an on-device verification pass that fixed the overlaps the mockups had hidden. |
| UX excellence | 2026-10-03 | 19 | Failure states made honest rather than decorative: the HTTP stack builds lazily and fails fast on an unreachable backend, a dead session is treated as a sign-out instead of a permanent error, navigation stops throwing away state and duplicating screens, skeletons become readable, the chat header reports the socket's real state, report reasons become sendable, and one motion/haptics/number/image language replaces the ad-hoc one. A copy pass followed, so every explanation line reads in one voice. |
| Adversarial QA and reliability hardening | 2026-10-04 | 27 | A break-the-app pass: the auth limiter stopped trusting a forged `X-Forwarded-For`, the remaining check-then-insert races in the test engine and in repeated social writes were closed by constraints, a chat socket was bound to the lifetime of its pair, its screen and its frames, the token in a handshake was kept out of the log, an oversized image became an input refusal instead of a 500, and a too-long message is refused for the reason that is too long. Then the two hot reads that scanned a whole table were paginated, discovery began serving a stored deck instead of re-ranking the pool on every page, requests became nameable and timed (request id, latency, structured logs), the health probe stopped pretending about a database that is not there, and chat sends gained an idempotency key with room access granted by rows rather than tokens. The live journey was extended to drive the socket, not only the rows. |
| Accessibility, privacy lifecycle, engine consistency | 2026-10-05 | 38 | The keyboard matrix measured at 320/360/393 dp and font scale 1.0/1.3: the report dialog's only way to finish, the last row of the sign-in form and the pinned onboarding button were all under the IME or the gesture bar and are not now; icon-only controls got semantics, and accents that carry text are solved against the pixels behind them. A stale bearer token — Ktor caching the first token it loaded, so an in-process account switch kept sending the previous user's header — was fixed in the send pipeline. «Delete account» became a promise about data rather than about a screen, and a block became a server-side wall with tests written down. The engine was made consistent: one pair of answers gives one percent in every process, a pair displays the percent it has rather than the one it met on, `0..100` is a promise the response models keep, and the seeded demo pair carries the number the engine gives it. Production guards were extended to every setting that could silently undo the others, and the release build is now checked against the artifacts it actually produces. |
| Launch readiness | 2026-10-06 | 11 | The `.gitignore` holes a public repository cannot leave open were closed; production now refuses to start over the database password this repository ships; the development database binds to loopback instead of every interface; `LICENSE` and `THIRD_PARTY_NOTICES.md` state the terms the project runs under, including the bundled DejaVu font; the ten product screenshots in `screenshots/` were captured from the running app; the demo persona was renamed so public captures do not carry the author's own first name; and the test screen's question header was moved out from under the status bar. |
| Dependency security hardening | 2026-10-06 | 6 | The 40 Dependabot alerts the repository was carrying, all of them in `backend/requirements.txt`, closed by raising four packages to the versions that patch them (`PyJWT` 2.10.1 → 2.15.1, `pillow` 11.0.0 → 12.3.0, `python-multipart` 0.0.20 → 0.0.32, `pytest` 8.3.4 → 9.1.1 with `pytest-asyncio` 1.4.0) rather than by dismissing anything by hand; the image decoder now chosen from `ACCEPTED_PIL_FORMATS` instead of from the magic bytes a client labelled; 44 regression tests over forged, expired, claim-less and algorithm-substituted tokens, foreign-magic bodies, traversal-shaped filenames and five malformed multipart framings; a two-stage, non-root container image with the compiler left in the builder stage; `backend/ops/check_advisories.py`, which audits the resolved graph against the same advisory database Dependabot uses; and `docs/DEPENDENCIES.md` recording the policy, the reachability verdicts and what was deliberately not upgraded. |

## Why some stages share a date

The stage list a reader expects — backend, authentication, compatibility engine, Android MVP,
WebSocket chat, recommendations — does not map one-to-one onto days. The first backend commit
already contained the API layer, JWT auth with rotating refresh tokens, the compatibility
engine and the recommendation engine together, and the first Android commit already contained
the whole client flow. Those stages are real, but they were authored as single large commits
(`7eb8af3`, `f884eb0`) rather than as a sequence, so the timeline above records them as
delivered instead of inventing intermediate milestones.

What did arrive as separate stages, in order, is the harder part of the history: the visual
redesign, the failure-state and copy work, the adversarial QA pass that produced most of the
security fixes, the accessibility and privacy-lifecycle measurement, and the production
configuration gates.

## What each pass left behind in the tree

- **Tests as a record of defects.** Most `fix(...)` commits are paired with a `test(...)`
  commit or with assertions added inside the fix, so the IDOR sweep, the block-wall tests,
  the chat idempotency tests and the compatibility consistency tests are each traceable to
  the failure that motivated them.
- **Docs written from measurements.** `docs/OPERATIONS.md` and `docs/RELEASE.md` carry the
  numbers of the runs that produced them — backup and restore drill, pool sizing, health
  probes, artifact sizes — and several commits exist only to correct a number a doc had
  carried too long.
- **Nothing is a stub.** There is no fake realtime path, no random percentage and no
  placeholder screen in the history; where a capability is absent (push notifications, an
  admin panel for reports) the design is written down and the absence is stated.
