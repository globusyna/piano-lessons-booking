# Merge log

One row per issue that reached QA PASS, in the order it was built. Merge
top to bottom and stop at the first row that is not PASS - the rows after
it were built on a tree that never passed.

| # | Issue | Branch | PR | Built on | QA | make check |
|---|-------|--------|----|----------|----|------------|
| 1 | [#15 B-20 Add migrations](https://github.com/globusyna/piano-lessons-booking/issues/15) | `codex/b-20` | [#46](https://github.com/globusyna/piano-lessons-booking/pull/46) | `master` | PASS | backend PASS, frontend pre-existing FAIL (#35) |
| 2 | [#9 B-01 Lessons never complete](https://github.com/globusyna/piano-lessons-booking/issues/9) | `codex/b-01` | [#49](https://github.com/globusyna/piano-lessons-booking/pull/49) | `codex/b-20` (merged, so PR targets `master`) | PASS | backend PASS, frontend pre-existing FAIL (#35) |
| 3 | [#12 B-10 Pause a student](https://github.com/globusyna/piano-lessons-booking/issues/12) | `codex/b-10` | [#50](https://github.com/globusyna/piano-lessons-booking/pull/50) | `codex/b-01` (merged, so PR targets `master`) | PASS | backend PASS, frontend pre-existing FAIL (#35) |
| 4 | [#13 B-11 Top up a package](https://github.com/globusyna/piano-lessons-booking/issues/13) | `codex/b-11` | [#55](https://github.com/globusyna/piano-lessons-booking/pull/55) | `codex/b-10` | PASS | backend PASS, frontend pre-existing FAIL (#54) |
