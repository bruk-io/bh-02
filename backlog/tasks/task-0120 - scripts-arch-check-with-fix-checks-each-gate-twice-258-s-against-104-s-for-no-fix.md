---
id: TASK-0120
title: >-
  scripts/arch-check with --fix checks each gate twice: 258 s against 104 s for
  --no-fix
status: To Do
assignee: []
created_date: '2026-10-16 12:19'
labels:
  - gates
  - scripts
  - size-2
dependencies: []
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0116 (its worker measured it; its close review noted it). scripts/arch-check's default mode runs pypeeker check --strict --fix, which prints a JSON report of the fixes it applied rather than findings, then a plain check --strict for the findings and the exit code, so every gate's rules run twice: 258 s with --fix against 104 s with --no-fix on a shared machine. Find whether pypeeker's --fix run can give the findings left after fixing (its report, a flag, or a check that runs only when a fix was applied), so a run that applied nothing checks once.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 scripts/arch-check (with --fix) runs each gate's rules once when no fix applies, and still reports the findings left and exits non-zero on any, shown by a test
- [ ] #2 Its wall time with --fix before and after is recorded in the notes
<!-- AC:END -->
