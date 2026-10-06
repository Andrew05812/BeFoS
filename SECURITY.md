# Security policy

BeFoS is a portfolio project with a real attack surface behind it: JWT sessions, uploaded
images, a WebSocket chat, an object-level authorization model, and personal data that people
would not want leaked. Findings about this codebase are welcome and will be treated as work, not
as noise.

## Reporting a vulnerability

Please report security issues **privately**, and do not open a public issue, discussion or pull
request describing them.

1. **Private vulnerability reporting** — use the “Report a vulnerability” form on the
   repository's Security tab (`Andrew05812/BeFoS` → Security → Report a vulnerability). The
   report is visible only to you and to the repository owner.
2. If private reporting is unavailable for this repository, contact the owner through the
   GitHub profile at [Andrew05812](https://github.com/Andrew05812) and describe the problem in
   the first message only as far as needed to route it (“authentication bypass on X”, not the
   working exploit).

There is no published email address or PGP key for this project, and none is invented here.

## What to include

- The affected endpoint, screen or component, and the commit or release you tested.
- Steps to reproduce, ideally against a local stand (`docker compose up --build`) rather than a
  description in the abstract.
- The impact you believe it has, and any suggested fix if you have one — optional.

Redacted or synthetic request/response bodies are preferred over real ones. Do not include data
belonging to other users.

## What happens next

- An acknowledgement within a few days — this is a single-maintainer project, so the fix may take
  longer than a company's SLA, but the response will not be silence.
- If the report is valid: a fix on a private branch, then the public commit. The commit message
  describes the class of defect and the guard that closes it, not the exploit path.
- Coordinated disclosure: no public details until the fix is released, or until the reporter
  agrees the issue is public.
- A line in [`CHANGELOG.md`](CHANGELOG.md) under **Security**, and credit to the reporter if they
  want it.

## Scope

In scope:

- Authentication, session handling and token rotation.
- Object-level authorization — reading or writing another user's profile, photos, test answers,
  matches, chat rooms, recommendations or safety records.
- The WebSocket gateway: handshake authorization, frame authorization, and whether a socket can
  outlive its pair or a block.
- Upload handling (size, decoding, storage, and what happens on account deletion).
- Injection, SSRF, path traversal, and any way to reach `/uploads` content that is not yours.
- Rate limiting, and the production configuration gates that refuse an unsafe deployment.
- Leakage of secrets or personal data into logs, error bodies or client-visible messages.
- Third-party components pinned by this repository, when the flaw they describe is reachable from
  it (see *Third-party components* below).

Out of scope, currently:

- Anything requiring a hosted instance. There is no deployed BeFoS service to attack — see
  *Project Status* in [`README.md`](README.md). Reports about the local stand are in scope.
- The known, documented limits listed below.

## Known and accepted limits

These are stated in the documentation and are not vulnerabilities to re-report; they are open
design work:

- `/uploads` is served as unauthenticated static content. Access control rests on unpredictable
  file names and on deleting the file together with the account, not on a permission check.
  Closing this needs signed URLs or an authorized media route.
- Account deletion is soft at the row level (`users` survives so foreign keys and pair history
  stay intact); everything that describes the person is erased, but the row itself is not.
- A block cannot be lifted from the app; removal is a documented SQL operation and does not
  restore the deleted pair.
- Reports have no in-app reader; resolving one currently means `psql`.
- Backups are a documented, verified procedure without a scheduler and without an off-host copy.

## Development defaults are not production settings

The repository ships with development credentials that are deliberately visible: the demo
account (`demo@befos.app` / `Demo12345`), the database password `befos_password`, and
placeholder JWT secrets. With `ENVIRONMENT=production` the service refuses to start while any of
them remain in place — that refusal is the guard, and a report that the guard can be bypassed is
in scope, while a report that the values exist is not.

## Third-party components

Most of what this service runs is other people's code: FastAPI, PyJWT, Pillow,
python-multipart, SQLAlchemy, Ktor, Compose, and two container images. Dependabot is enabled on
the repository and the pinning policy, the alert inventory and the review cadence are written
down in [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).

What that means for a report here:

- A dependency with a published advisory and an available patched release is treated as a defect
  in this repository, not as upstream's problem. It is closed by upgrading the version, and the
  alerts are not hand-dismissed to make the badge look better.
- Whether a flaw is *reachable* in BeFoS is stated per package family in `docs/DEPENDENCIES.md`,
  with the reasoning (which call sites exist, which are absent). That judgement decides
  priority, never status: an unreachable advisory is still closed by the patched version.
- A finding against a version this tree no longer pins is worth re-checking against the current
  pins first; the version you tested is the first line of the report.
- The audit is reproducible without trusting any document in this repository:
  `backend/ops/check_advisories.py` asks the same GitHub advisory database Dependabot uses about
  the *resolved* dependency graph, and exits non-zero when something is affected.

As of the 2026-10-06 hardening: 40 open alerts (1 critical, 20 high, 15 medium, 4 low) sat in
`backend/requirements.txt`; the four packages that carried them moved to patched versions and the
resolved graph of the backend container (30 artefacts) and of the Gradle runtime classpath
(165 artefacts) measured 0 affected. What is deliberately *not* upgraded — an Android stack with
no advisory on it today, and the container images that trail their distributions by newer
packages rather than by open advisories — is listed with its reason and its update plan in
`docs/DEPENDENCIES.md`, and is not claimed to be safe in general.

## Note on contributions

BeFoS is maintained as a proprietary project. Security **reports** are accepted and appreciated;
code contributions are not, and pull requests will not be merged.
