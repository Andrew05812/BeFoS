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

## Note on contributions

BeFoS is maintained as a proprietary project. Security **reports** are accepted and appreciated;
code contributions are not, and pull requests will not be merged.
