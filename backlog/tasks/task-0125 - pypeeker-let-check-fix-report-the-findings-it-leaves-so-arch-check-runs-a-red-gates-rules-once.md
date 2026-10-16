---
id: TASK-0125
title: >-
  pypeeker: let check --fix report the findings it leaves, so arch-check runs a
  red gate's rules once
status: To Do
assignee: []
created_date: '2026-10-16 14:12'
labels:
  - gates
  - size-2
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
<!-- AC:END -->
