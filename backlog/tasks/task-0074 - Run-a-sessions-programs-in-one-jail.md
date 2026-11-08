---
id: TASK-0074
title: Run a session's programs in one jail
status: To Do
assignee: []
created_date: '2026-10-10 18:42'
updated_date: '2026-11-08 20:51'
labels:
  - runner
  - finish-moved
  - size-5
milestone: m-5
dependencies:
  - TASK-0079.32
parent_task_id: TASK-0084
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`runner:confined` compiles a jail per start, so a session starts two jails from one policy (the Python process and the extensions process), and sub-agents would add one per REPL. With TASK-0073 a jail holds more than one process: the runner starts one jail per session and starts each program in it. The `runner` contract changes: `start` starts a program in the session's jail; the grades report is the jail's, not each start's; `/release` stops each program through its owner, then ends the jail; a stuck or dead Python process is started again inside the jail, not in a new one. `runner:unconfined` keeps plain processes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A session starts one jail, and the Python process and the extensions process both run in it (tested: one jail start for both)
- [ ] #2 Starting the Python process again (a stuck input, a crash) starts no new jail
- [ ] #3 `/release` stops each program through its owner, then ends the jail; the next start starts a new one
- [ ] #4 `--no-jail` behaves as before
- [ ] #5 CONTRACTS.md (`runner`), the runner plugin's README and the docs' jail-and-approval page describe one jail per session
- [ ] #6 `scripts/linux-jail-check` and `scripts/check` pass
- [ ] #7 The mount tripwire ends the session's jail with a kill that doesn't depend on the runtime, tells every owner `ended()`, and the next start creates a new jail
- [ ] #8 Read allows derived from argv, and `git_author`, are decided at create, not per start
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-11: rewired onto decision-0001's split. It no longer depends on TASK-0073 (superseded): it needs a channel per start (TASK-0079.05) and per-process isolation (TASK-0079.07), so the Python process and the extensions process can't reach each other in one jail.

Owner's trim, 2026-10-12: moved out of TASK-0079's finish line to the deferred brig intent TASK-0084. Sub-agents run with a jail each from the same policy until this lands (decision-0002).

Finish moved (recorded 2026-11-06): commit b6b09860 ("Accept the brig and sub-agent intents and decision-0001, and split them") added criteria #7 and #8 when this task was rewired onto decision-0001's runtime/confinement split, requiring the mount tripwire to end the jail independent of the runtime and read allows to be decided at create rather than per start.

Owner stand-in (Opus), 2026-11-06: Approved for this run on the orchestrator's report that Bruk put 0048 and 0074 in it today; it starts only after TASK-0079.31 closes, in the brig lane's order. Its AC #6 needs scripts/linux-jail-check as well as scripts/check; if the lane runs out of room, stopping here is fine (stuck is information).
<!-- SECTION:NOTES:END -->
