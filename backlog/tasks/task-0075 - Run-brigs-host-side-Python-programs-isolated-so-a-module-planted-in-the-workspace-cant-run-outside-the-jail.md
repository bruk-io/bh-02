---
id: TASK-0075
title: >-
  Run brig's host-side Python programs isolated, so a module planted in the
  workspace can't run outside the jail
status: To Do
assignee: []
created_date: '2026-10-10 21:58'
updated_date: '2026-10-11 15:30'
labels:
  - brig
  - runner
  - size-3
dependencies: []
priority: high
type: bug
parent_task_id: TASK-0079
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
brig's exit wrapper runs `python -c` with its working directory set to the workload's (libs/brig/src/brig/run/launcher.py:236), and no interpreter brig starts runs with `-I`, so the workload's directory is first on its import path. Reproduced 2026-10-10 with the empty stack: a `subprocess.py` planted in the workspace ran inside the wrapper (argv `-c`), outside any jail. The rlimits trampoline and the egress proxy run `python -m`, which puts the working directory first too (not reproduced). In bh-02 the Python process's working directory is the project root, which jailed code can write, so the next jail start (the Python process started again, the extensions process starting, the first input after /release) would run a planted module unconfined. Not yet reproduced end to end through bh-02. Found by the brig-internals review of decision-0001.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every Python interpreter brig starts on the host runs isolated (`-I`), and a test lists them all
- [ ] #2 A test plants `subprocess.py`, `signal.py` and a `brig/` package in the workload's working directory and shows none is imported by the exit wrapper, the trampoline or the egress proxy; the same test fails before the fix
- [ ] #3 In bh-02, a test plants a module in the project root, starts the Python process again, and nothing runs outside the jail
- [ ] #4 brig's test tiers, `scripts/linux-jail-check` and `scripts/check` pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Sized size-3 (2026-10-11): the change is small (-I on three interpreters), but it is a jail escape across two codebases, -I's effect on editable installs and PYTHONPATH is unchecked, and bh-02 needs an end-to-end test.
<!-- SECTION:NOTES:END -->
