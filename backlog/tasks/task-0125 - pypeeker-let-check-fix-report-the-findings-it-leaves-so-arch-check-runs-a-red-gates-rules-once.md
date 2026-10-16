---
id: TASK-0125
title: >-
  pypeeker: let check --fix report the findings it leaves, so arch-check runs a
  red gate's rules once
status: To Do
assignee: []
created_date: '2026-10-16 14:12'
updated_date: '2026-10-16 22:59'
labels:
  - gates
  - size-2
  - finish-moved
dependencies: []
priority: low
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0120. scripts/arch-check now runs the plain check first and only runs check --strict --fix on a gate with findings, so a clean gate's rules run once (118 s to 48 s with --fix). A gate whose findings have no fix still runs them twice: pypeeker's --fix report holds fixes, skipped_conflicts, declined, residual_violations (a count only) and tx_id, and the plain check's output does not mark which findings a fix could repair, so the script cannot skip --fix nor print the findings left from the --fix run. The change is upstream: --fix's report carries the residual findings as text (or check marks fixable findings), then arch-check uses it, and the pin is bumped.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 pypeeker (upstream) gives the findings a --fix run leaves, as text in its report or a marker in check's output, and the root pin names the merged commit, uv.lock regenerated with uv
- [ ] #2 scripts/arch-check runs a gate's rules once when no fix applies, findings and exit code unchanged, shown by a test, and its time on a gate with findings is recorded before and after
- [ ] #3 A clean gate's `scripts/arch-check` run with --fix is no slower than before this task (TASK-0120 left it at the plain check's cost), measured paired on the same machine
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Orchestrator, 2026-10-16: finish moved after the work. The worker dropped the plain-check-first step so a red gate runs once (93.1 s to 56.2 s), but that made the clean gate, every green CI and pre-commit run, 17.7 s slower (37.1 s to 54.8 s): TASK-0120's gain undone. The worker's prototype (pypeeker's plan_check_fixes skips collecting repairs when the run has no findings) took a clean --fix from 54.8 s to about 37 s. Added criterion 3 so the clean gate does not regress; the skip goes into the same pypeeker change.
<!-- SECTION:NOTES:END -->
