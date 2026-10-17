---
id: TASK-0134
title: >-
  Run brig's supervisor on Python 3.15 only, the interpreter brig and bh-02 run
  on (decision-0007)
status: To Do
assignee: []
created_date: '2026-10-17 14:50'
updated_date: '2026-10-17 19:04'
labels:
  - brig
  - runner
  - size-2
dependencies: []
references:
  - >-
    backlog/decisions/decision-0007 -
    Run-brigs-supervisor-on-Python-3.15-the-interpreter-brig-and-bh-02-run-on-never-an-older-one.md
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Builds decision-0007, the owner's ruling of 2026-10-17: brig's supervisor, each jail's PID 1, runs only under Python 3.15 or later, never the system Python. Read the decision first; it says what holds today (the runner's host_interpreters puts /usr/bin/python3 first) and why the fallback can fail closed (TASK-0124, TASK-0126, TASK-0127).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 brig's SPEC gets a dated ruling amending decision-190: the supervisor runs under 3.15 or later, its default the interpreter brig itself runs on (its base interpreter, never a venv's)
- [ ] #2 bh-02's runner offers the supervisor its own base interpreter only; a host where it cannot be held in the jail gets InterpreterNotMounted with what to do, and a test shows it
- [ ] #3 In a container, the supervisor is used only when the image's python3 is 3.15 or later, else docker exec; a test with bh-02-linux-jail (3.12) shows the exec path and says why
- [ ] #4 The supervisor program refuses to start under an older interpreter, naming the version it needs; the 3.9 parse test is gone and the program is checked by strict mypy with the rest of brig
- [ ] #5 scripts/check and scripts/linux-jail-check pass, the supervisor running under uv's 3.15 in both
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Archived 2026-10-17: brig moved to a repository of its own (TASK-0135, archived), and the old libs/brig is frozen until the new one replaces it. The new brig's decision-0001 (rule 17) carries decision-0007: the supervisor runs only on Python 3.15.
<!-- SECTION:NOTES:END -->
