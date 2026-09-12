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
3. Engineer implements it
4. QA verifies it
5. On FAIL, back to step 3 with the QA comment as input. After two failed
   rounds, stop and report what is still failing
6. On PASS, close the issue
7. Stop and report. Move to the next issue only when asked

Rules

- Do not skip step 2
- The engineer does not close the issue
- QA does not fix the code, only outputs PASS or FAIL
- The orchestrator closes the issue only after QA outputs PASS
- Acceptance criteria are frozen after step 2. Disagreement is a comment
  on the issue, not an edit
- The engineer creates the branch `codex/<short-task-name>`. Merging is
  not the orchestrator's call
