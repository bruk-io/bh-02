---
id: DRAFT-0020
title: 'Full-suite-only setup ERRORs in host-paths, warden and cordis tests on darwin'
status: Draft
assignee: []
created_date: '2026-11-07 05:00'
updated_date: '2026-11-07 19:23'
labels:
  - tests
  - darwin
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
scripts/check on a 28-core Mac (2026-11-07, recorded on TASK-0169.06) reports 25 ERRORs; 17 are brig (TASK-0198), but 8 are in libs/host-paths/tests/test_host_paths_appender.py (3) and examples/warden/** (5). Run alone (-p no:cacheprovider, same files) they all pass (56 passed). The recorded output is truncated so the error text is not visible; the cause under the full parallel run is unknown and no task owns it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The cause of the setup errors under the full run is explained
- [ ] #2 scripts/check on the 28-core Mac shows no setup ERROR in host-paths, warden or cordis tests across three runs in a row, or each one left is filed under the task that owns its cause
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner stand-in (Opus), 2026-11-06: Accept this as the owner of every full-run-only setup ERROR under the parallel check on darwin (host-paths appender, warden, and cordis test_invariants[73] from DRAFT-0022, which is folded in here and archived). Promote through accept-work. TASK-0169.06 #2 depends on this being an accepted task, not on it being fixed.

Folded in from the draft 'Full-suite-only setup ERROR in cordis test_invariants under the parallel check on darwin' (archived), 2026-11-07: the full scripts/check at f6ce185a (recorded on TASK-0169.04) shows ERROR libs/cordis/tests/test_invariants.py::test_invariants_hold_when_operations_interleave[73], absent from the 7733f854 run. The setup ERRORs under the full parallel run rotate between runs (the host-paths appender and warden victims differ each time), so this is taken as the same cause: a setup failure that depends on the full parallel load, not on the test that hits it. If the investigation finds a distinct cause for the cordis one, file it separately.

Sized 2 (accept-work, 2026-11-07): the cause is unknown, but the work is bounded - capture the setup error text from one full run (no -q truncation), explain it, fix or hand off; one area (test setup under xdist on darwin), low risk, no product change expected. If the captured error shows a product race, re-size before fixing.
<!-- SECTION:NOTES:END -->
