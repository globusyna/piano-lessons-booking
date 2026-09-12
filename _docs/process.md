- Tasks are GitHub issues, one at a time
- Read the acceptance criteria before starting and before closing
- Commit regularly

Roles

- PM - grooms a task before anyone implements it, follows _docs/team/pm.md
- Engineer - implements one groomed task, follows _docs/team/software-engineer.md
- QA - checks the result against the acceptance criteria, follows _docs/team/qa-engineer.md

Orchestrator

The main session is the orchestrator. It launches the PM, the engineer
and QA as subagents. It does not groom, implement or test itself.

- To launch a role, read its file in `_docs/team/` and pass it to the
  subagent verbatim, with the issue number. Do not summarise it.
- The issue is the only handoff. Roles read it with
  `gh issue view <N> --comments` and write back with `gh issue comment`
  or `gh issue edit`. Nothing passes through chat.
- Before advancing a step, check the previous role's definition of done
  by reading the issue. If it is not met, send the same agent back with
  what is missing.

Lifecycle

1. Pick the next issue in the order given at the top of `_docs/backlog.md`,
   skipping any whose listed dependencies are still open
2. PM grooms it
3. Engineer implements it and opens a draft PR linked to the issue
4. QA verifies it and posts PASS or FAIL on the issue
5. On FAIL, back to step 3 with the QA comment as input. After two failed
   rounds, stop and report what is still failing
6. On PASS, mark the PR ready for review and add a row to the merge log
7. Stop and report. The human reviews, approves and merges. The merge
   closes the issue, not the orchestrator

Branches and merge order

- The engineer branches from the previous issue's branch, not from
  master, so each task is built and verified on top of everything before
  it: `master -> codex/b-53 -> codex/b-20 -> codex/b-01`
- Ten branches cut from master give ten green QA runs that say nothing
  about the merged result. The stack is what makes a PASS mean something
- Each PR targets the branch below it and its body says `Closes #N`.
  When the PR below merges, GitHub retargets this one to master on its own
- As each issue passes, append its row to `_docs/merge-log.md`
- Merge top to bottom and stop at the first row that is not PASS. The
  rows after it were built on a tree that never passed

Rules

- Do not skip step 2
- The engineer does not close the issue
- QA does not fix the code, only outputs PASS or FAIL
- Acceptance criteria are frozen after step 2. Disagreement is a comment
  on the issue, not an edit
- The engineer creates the branch `codex/<short-task-name>`
- The orchestrator never approves and never merges. An agent cannot
  approve its own PR in any case - the token belongs to the human
- Issues carrying an unresolved design decision do not go into an
  unattended run. Ask first
