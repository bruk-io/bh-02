---
id: DRAFT-0022
title: >-
  Full-suite-only setup ERROR in cordis test_invariants under the parallel check
  on darwin
status: Draft
assignee: []
created_date: '2026-11-07 05:35'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The full scripts/check at f6ce185a (recorded on TASK-0169.04) shows ERROR libs/cordis/tests/test_invariants.py::test_invariants_hold_when_operations_interleave[73], absent from the 7733f854 run. The setup ERRORs under the full parallel run rotate between runs (host-paths appender and warden victims differ each time), so this is likely the same cause as the draft 'Full-suite-only setup ERRORs in host-paths appender and warden tests on darwin'; merge into it if so.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The cause of the cordis test_invariants setup error under the full run is explained, or it is shown to share the host-paths/warden setup-error cause and merged there
<!-- AC:END -->
