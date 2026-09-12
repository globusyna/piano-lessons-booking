# Backlog

Improvement tasks derived from a review of the repository at commit `8ced983`.

Each task is sized (S = under half a day, M = about a day, L = multi-day) and lists its
dependencies. Nothing here has been implemented — this document is for review and
prioritisation. Tick a task off by linking the PR that closed it.

**Suggested order:** B-53 (#34) → B-20 (#15) → B-01 (#9) → B-10 (#12) → B-11 (#13) → B-02 (#10) → B-03 (#11) → B-30 (#22) → B-54 (#35) → the rest.

---

## P0 — The core loop does not close

### B-01 · Lessons never complete, so packages never consume — #9
**Size:** M · **Depends on:** B-20 (#15)

`package.used` is written once in `_seed_if_empty` (`backend/store.py:153`) and never changes
again. No endpoint and no job ever moves a lesson from `scheduled` to `done`. Consequences for
any student created through the app:

- `list_alerts` (`backend/store.py:754`) filters on `used >= size`, so the invoice alert never fires.
- `PackageProgress` is permanently stuck at `0/10`.
- The student page never reaches its "That was lesson 10 of 10" state (`frontend/src/routes/s.$token.tsx:128`).

`_docs/specs.md` §6 specifies a nightly job for this. The seeded students hide the gap because
their `used` values are hard-coded.

**Acceptance**
- Past `scheduled` lessons become `done` and increment their package's `used`, either through a
  scheduled job or a catch-up performed on read (pick one and document the trade-off).
- An admin endpoint can mark a single lesson done / undo it, for the case where a lesson is
  cancelled on the day.
- Tests cover the transition with a controlled clock (see B-51 (#32)), including the boundary where the
  final lesson of a package passes and the invoice alert appears.

### B-02 · Move requests can be approved but never declined — #10
**Size:** M

`POST /admin/move-requests/{id}/approve` is the only action on a request. There is no decline, and
nothing expires a stale request. While one is pending:

- the requested slot counts as taken for everyone (`_open_slots`, `backend/store.py:414`);
- the student cannot submit another request — `request_lesson_move` raises
  `MOVE_ALREADY_REQUESTED` (`backend/store.py:517`);
- once the requested time passes, approving it fails with `SLOT_TAKEN`, which is a misleading
  message for a request that simply expired.

The teacher's only escape is to delete the lesson entirely.

**Acceptance**
- `POST /admin/move-requests/{id}/decline` removes the request, frees the slot and lets the student
  try again.
- Requests whose requested time has passed are expired automatically and reported with their own
  error code rather than `SLOT_TAKEN`.
- Decline is available in both the alerts list and the week-view popover, next to the existing
  approve button.

### B-03 · Generated packages ignore blackouts and availability — #11
**Size:** M

`_open_package_record` (`backend/store.py:652`) places `size` lessons on `slot_day`/`slot_time` for
`size` consecutive weeks with no reference to blackouts, to the availability grid, or to whether
the teacher still works that hour. The only thing that can stop it is the unique constraint on
`lessons.starts_at`, which surfaces as `SLOT_TAKEN` — "A generated lesson time is already booked" —
even when the real cause is a holiday.

**Acceptance**
- Generation skips blackouts and rolls the affected lesson forward to the next valid week.
- Generation refuses, with a clear message, when the student's weekly slot is not in the
  availability grid.
- The admin sees the dates that will be created before confirming.

---

## P1 — Student management

### B-10 · Pause a student for 1–6 weeks — #12
**Size:** L · **Depends on:** B-20 (#15)

`store.pause()` (`backend/store.py:580`) flips `status` to `paused` and stops there. Nothing is
released, nothing resumes, and there is no duration. The pause is therefore both permanent and
invisible: the student's scheduled lessons stay on the calendar, keep occupying slots that no one
can book, and keep appearing on the student's own page as upcoming. `_docs/specs.md` states the
weekly slot should be released.

**Scope**
- *Schema:* a `student_pauses` table (`student_id`, `weeks`, `starts_on`, `ends_on`, `created_at`,
  `ended_early_at`) rather than columns on `students`, so the history survives repeated pauses.
- *Store:* `pause_student(student_id, weeks)` validating `1 <= weeks <= 6`; releases the scheduled
  lessons falling inside the window and shifts the rest of the package forward by `weeks`.
- *Numbering:* `seq` is preserved — the README rule is that lesson numbers are never renumbered —
  and `used` is untouched, so a pause costs the student nothing.
- *Resume:* automatic when `ends_on` passes, plus `resume_student(student_id)` for an early return;
  both restore `status` to `active`.
- *Student API:* `POST /s/{token}/pause-request` takes `{"weeks": 1..6}`; the `/s/{token}` response
  carries `pausedUntil` so the page can say when lessons restart.
- *Admin API:* pause and resume on behalf of a student from the student detail screen.

**Acceptance**
- Only future lessons move; anything already `done` is untouched.
- Slots released by a pause become bookable by other students immediately.
- `weeks` outside 1–6 is rejected with a named error code.
- The student dialog offers a 1–6 week choice and states the return date; today it hard-codes copy
  about the slot being released, which is not what the backend does
  (`frontend/src/routes/s.$token.tsx:230`).
- Admin student detail shows "Paused until *date*" with a Resume now action, replacing the current
  bare three-way status toggle.
- Tests cover: pause across a package boundary, early resume, automatic expiry, and a pause
  requested while a move request is pending.

### B-11 · Renew a package by topping up the lessons already available — #13
**Size:** L · **Depends on:** B-20 (#15), B-03 (#11)

When a student confirms their next package, the 5 or 10 new lessons should be **added to the
lessons they already have**. Neither existing path does that:

- `mark_invoiced` (`backend/store.py:699`) creates a *new* `PackageRecord` at `period_no + 1` with
  `used = 0` and generates a fresh run of lessons, resetting the student's progress display.
- `open_package` (`backend/store.py:690`) refuses outright while any scheduled lesson exists
  (`PACKAGE_OPEN`), so it cannot be used to extend a running package.

Two schema constraints block a top-up as written: `CheckConstraint("size IN (5, 8, 10)")`
(`backend/db_models.py:44`) and `size: Literal[5, 8, 10]` (`backend/models.py:29`). A package
topped up from 10 to 20 satisfies neither.

**Scope**
- `POST /admin/students/{id}/package/renew` with `{"size": 5 | 10}`, extending the *current*
  package instead of opening a new one.
- New lessons are numbered from the current maximum `seq + 1` and placed on the weekly slot
  following the last scheduled lesson, skipping blackouts and any active pause window.
- Represent the larger total either by relaxing the constraints to `size >= 1`, or by recording
  top-ups in their own table and deriving `size`. The derived option keeps the audit trail of what
  was sold when; decide and write the decision down.
- Keep `mark_invoiced` as the invoice flag only. Coupling "invoice sent" to lesson generation is
  why the teacher currently has no say in the next package's size — it silently reuses the old one.
- Student page reads `7 / 20` and shows a line confirming the lessons were added.

**Acceptance**
- Renewing preserves `used`, `seq` numbering and every existing scheduled lesson.
- Renewing a finished package (`used == size`) and a mid-flight one both work.
- Renewal is reachable from the invoice alert as well as student detail.
- Tests cover 5-lesson and 10-lesson top-ups, a top-up over a blackout, and a top-up for a paused
  student.

### B-12 · Round out student management — #14
**Size:** M · **Depends on:** B-10 (#12)

Gaps in `/admin/students/{id}` once pause and renewal exist:

- No rename. `create_student` sets the name and nothing can change it.
- No archive or delete. A student who leaves stays in the table and the week view forever.
- No token rotation. `students.token` is the only credential a student has; a link shared in the
  wrong chat cannot be revoked.
- No email field, although `_docs/specs.md` §2 includes `student.email` and every notification idea
  in the backlog depends on it.

**Acceptance**
- Rename, archive (soft delete — hidden from lists, week view and alerts, history retained) and
  rotate-token actions, each with a confirm step.
- Archiving releases the student's future lessons.
- Optional email on the student record, validated, not required.

---

## P2 — Data model and reliability

### B-20 · Add migrations — #15
**Size:** M · **Blocks:** B-01 (#9), B-10 (#12), B-11 (#13), B-12 (#14)

`DatabaseStore.__init__` calls `Base.metadata.create_all` (`backend/store.py:54`), which creates
missing tables and nothing else — it will not add a column to a table that already exists.
`_upgrade_legacy_seed_data` (`backend/store.py:189`) is a bespoke one-off patcher for a seed bug,
which is the shape this problem takes when there are no migrations.

Every P1 task adds columns or tables. Without migrations, an existing `piano.db` breaks on upgrade.

**Acceptance**
- Alembic wired up with an initial revision matching the current schema.
- `make migrate` applies revisions; startup no longer relies on `create_all`.
- `_upgrade_legacy_seed_data` is retired into a migration or deleted.
- Document the upgrade path for an existing local `piano.db`.

### B-21 · The studio timezone is hard-coded — #16
**Size:** S

`STUDIO_TZ = ZoneInfo("Europe/Oslo")` is a module constant (`backend/store.py:35`) while
`teacher_settings.timezone` is stored at seed time and never read. Changing studios means editing
source. Worth checking the DST edges at the same time: `_at()` localises a naive `datetime` with
`ZoneInfo`, which silently picks a side on the ambiguous autumn hour and produces a non-existent
time on the spring gap.

**Acceptance** — timezone read from settings; a test covers a lesson on each DST boundary.

### B-22 · The week grid is pinned to a duplicated `ROW_TIMES` — #17
**Size:** S

`ROW_TIMES` is declared in `backend/store.py:36` and again in `frontend/src/lib/piano-data.ts:75`.
`/admin/api/week` iterates only those seven times, so a slot the teacher adds outside them is
bookable through `_open_slots` but invisible in the week view — a lesson that exists and cannot be
seen or clicked.

**Acceptance** — grid rows derive from stored availability (or `ROW_TIMES` is served by the API and
consumed by the frontend); the duplicate constant is gone.

### B-23 · Weekends are impossible by constraint — #18
**Size:** S

`weekday >= 1 AND weekday <= 5` on availability and `slot_day >= 1 AND slot_day <= 5` on students
(`backend/db_models.py:21`, `:32`), reinforced by `Weekday = Annotated[int, Field(ge=1, le=5)]`.
Saturday lessons cannot be represented at all. This may well be deliberate — it is not written down
anywhere, so it reads as an accident.

**Acceptance** — either widen to 1–7, or record the restriction in the specs as a decision.

### B-24 · `SLOT_TAKEN` is doing too many jobs — #19
**Size:** S

The global `UniqueConstraint("starts_at")` on `lessons` is the only concurrency guard, so every
`IntegrityError` is translated to `SLOT_TAKEN` regardless of cause — a genuine race, a package
generated over an existing booking, a duplicated move request. The constraint also spans `done`
lessons, which is correct for a single teacher but worth stating.

**Acceptance** — distinct error codes per cause; the catch-all mapping is narrowed to real races.

### B-25 · The store is a module-level singleton built at import — #20
**Size:** M

`store = DatabaseStore()` at `backend/store.py:780` connects to a database and seeds it as a side
effect of importing the module. `tests/conftest.py` works around this by setting
`PIANO_DATABASE_URL` before its import of `backend.main`, with a comment explaining that the reset
fixture must not be pointed at a real database — a comment that exists because the design makes
that mistake easy.

**Acceptance** — the store is constructed in the FastAPI lifespan and injected as a dependency;
tests build their own instance instead of relying on import order.

### B-26 · Seeding runs against any empty database — #21
**Size:** S

`_seed_if_empty` runs on every startup and populates any database it finds empty, including a fresh
production one — six fictional students and a teacher whose password is `piano`.

**Acceptance** — seeding is behind an explicit flag (`PIANO_SEED=1` or a `make seed` target) and
off by default.

---

## P3 — Security

### B-30 · The JWT secret has a working default — #22
**Size:** S

`JWT_SECRET = os.getenv("PIANO_JWT_SECRET", "local-development-secret-change-me")`
(`backend/auth.py:14`). A deployment that forgets the variable accepts admin tokens minted by
anyone who has read this repository. The runbook mentions setting it; nothing enforces it.

**Acceptance** — startup fails when the variable is unset outside an explicit dev mode.

### B-31 · The demo password is printed on screen — #23
**Size:** S · **Depends on:** B-26 (#21)

The seeded teacher password is `piano`, and both the landing page
(`frontend/src/routes/index.tsx:35`) and the admin login form
(`frontend/src/routes/admin.tsx:68`) display it. Correct for a demo, unacceptable the moment this
is deployed anywhere.

**Acceptance** — both strings are behind a build-time demo flag, default off.

### B-32 · Student tokens are guessable and unthrottled — #24
**Size:** M

`create_student` uses `secrets.token_urlsafe(24)` — fine. The seeded tokens are `anna`, `jonas`,
`mira`, `teodor`, `selma`, `oskar`, and `/s/{token}` has no rate limit, so the endpoint can be
enumerated freely. The token is the whole credential: it exposes the student's name, schedule and
the ability to move lessons.

**Acceptance** — rate limiting on the student routes; seeded tokens are random (printed by the seed
command); token rotation exists (B-12 (#14)).

### B-33 · Admin token in `sessionStorage`, with no refresh — #25
**Size:** M

`frontend/src/lib/api-client.ts:17` stores the bearer token in `sessionStorage`, readable by any
injected script. The token has an 8-hour TTL (`backend/auth.py:13`) and there is no refresh, so it
expires mid-session and drops the teacher back to the login form with whatever they were doing
lost.

**Acceptance** — evaluate an httpOnly cookie plus CSRF token; add refresh or a warning before
expiry.

### B-34 · CORS is hard-coded to localhost — #26
**Size:** S

Four localhost origins are compiled in with `allow_credentials=True`
(`backend/main.py:12`). Not configurable per environment.

**Acceptance** — origins come from configuration.

---

## P4 — Performance

### B-40 · `/admin/api/week` is N+1, badly — #27
**Size:** M

`get_week` (`backend/routers/admin.py:20`) loops 5 days × 7 times and, per cell, calls
`store.scheduled_lesson_at`, `store.blackout_at` and — for a lesson — `store.student` and
`store.move_request_for_lesson`. Each of those opens its own session. One week view costs between
70 and 140 round trips to satisfy a query that is three range selects.

**Acceptance** — the endpoint issues a bounded number of queries; a test asserts the count.

### B-41 · The student view queries each move request twice — #28
**Size:** S

`_view` in `backend/routers/student.py:12` calls `store.move_request_for_lesson(lesson.id)` once
for `canMove` and again for `requestedStartsAt`, per lesson.

**Acceptance** — fetched once per lesson, or once for the whole set.

### B-42 · `list_students` fetches packages one student at a time — #29
**Size:** S

The `students` property (`backend/store.py:69`) calls `_current_package` per record.

**Acceptance** — one grouped query.

### B-43 · The admin router reaches into store internals — #30
**Size:** S

`backend/routers/admin.py:29` and `:50` call `store._at(...)`, a private helper.

**Acceptance** — promoted to a public API on the store.

---

## P5 — Testing, docs, tooling

### B-50 · No frontend tests exist — #31
**Size:** M

`frontend/package.json` has no test runner and `frontend/src` contains no test files. Untested:
the move flow, the `SLOT_TAKEN` refetch path the README calls out by name, the admin login gate,
and every non-active student state.

**Acceptance** — Vitest and Testing Library configured, `npm run test` wired into `make check`,
covering the move flow including `SLOT_TAKEN`, the paused/flagged/finished/invalid-token states,
and the admin auth gate.

### B-51 · The backend suite cannot control time — #32
**Size:** M

18 tests pass, but every one of them derives "now" from the real clock — `test_admin.py` computes
the current Monday at runtime. The 48-hour move rule, the day lock, the +3-week window and the
`_open_slots` boundaries are only tested wherever today happens to fall, so the suite behaves
differently on a Friday than on a Monday and cannot test a DST weekend at all.

**Acceptance** — a clock seam (injected `now()` or `freezegun`, which needs approval per
`AGENTS.md`) with tests pinned to fixed dates covering each boundary.

### B-52 · `openapi.yaml` can drift silently — #33
**Size:** S

A 32 KB hand-maintained `openapi.yaml` sits at the root with nothing comparing it to the schema
FastAPI generates.

**Acceptance** — a test asserts equivalence, or the file is generated by `make build`.

### B-53 · `AGENTS.md` points at documents that do not exist — #34
**Size:** S

`AGENTS.md` instructs contributors to read `_docs/process.md` for how work is organised and
`_docs/testing-guidelines.md` before writing tests. Neither file is in the repository, so the two
rules are unfollowable — and every test task above inherits the ambiguity.

**Acceptance** — both documents written, or the references corrected.

### B-54 · Nothing runs `make check` — #35
**Size:** S

`make check` runs tests, lint and build. There is no `.github/` directory, so it runs only when
somebody remembers.

**Acceptance** — a workflow runs `make check` on push and pull request.

### B-55 · The README is the design brief — #36
**Size:** S

`README.md` is the frontend design brief pasted verbatim with Lovable boilerplate appended. It
still documents API shapes that have moved on — the `/s/:token` response it shows omits
`requestedStartsAt` and `canRequestPause`, both of which the frontend now relies on. It offers no
"how do I run this", which lives in `_docs/RUNBOOK.md`.

**Acceptance** — README covers what the project is, how to run it and where the docs are; the brief
moves to `_docs/design-brief.md` and is marked as the original brief rather than current truth.

### B-56 · Prune scaffolding that is not used — #37
**Size:** S

`frontend/src/components/ui/` holds roughly 45 shadcn components, of which the app imports a
handful (alert-dialog, popover, and little else). The dependencies behind the unused ones —
`recharts`, `embla-carousel-react`, `vaul`, `cmdk`, `input-otp`, `react-resizable-panels`,
`react-day-picker` — are all installed. `frontend/src/lib/lovable-error-reporting.ts` forwards
errors to an editor hook that only exists inside Lovable's preview, and `.lovable/project.json`
belongs to that toolchain too.

**Acceptance** — unused components, dependencies and editor scaffolding removed; the build still
passes.

### B-57 · Decide what happens about notifications — #38
**Size:** S (decision) / L (implementation)

`_docs/specs.md` §1 and §6 describe email as part of the loop — an invoice email to the teacher
when a package is consumed — and `teacher_settings.notify_email` is in the spec's data model. The
implementation has no email at all, and `notify_email` is not in `backend/db_models.py`. The
alerts screen is the de facto replacement. Either that is the decision, or the email is still
owed.

**Acceptance** — the choice is written down in the specs; if email stays, it gets its own task.

### B-58 · Response envelopes are inconsistent — #39
**Size:** S

Mutations return `{ok: true, data}`, `/s/{token}` returns the bare object, `/admin/students`
returns `{students}`, `/admin/api/week` returns `{days}`. Errors are consistent — `{ok: false,
error: {code, message}}` — so this is a documentation problem rather than a bug, but a client
cannot handle success generically.

**Acceptance** — the convention is documented, or the envelope is made uniform.
