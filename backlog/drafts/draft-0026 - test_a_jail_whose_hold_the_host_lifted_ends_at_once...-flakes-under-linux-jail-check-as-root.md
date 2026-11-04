---
id: DRAFT-0026
title: >-
  test_a_jail_whose_hold_the_host_lifted_ends_at_once... flakes under
  linux-jail-check --as-root
status: Draft
assignee: []
created_date: '2026-11-04T02:41:00Z'
updated_date: '2026-11-04T04:44:00Z'
labels:
  - brig
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reviewing TASK-0176.07 on 2026-11-04 at 448a4e3: scripts/linux-jail-check --as-root failed once in two runs (1 failed, 359 passed), FAILED bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py::test_a_jail_whose_hold_the_host_lifted_ends_at_once_whatever_its_programs_do_with_sigterm; the rerun passed (360 passed). The test bounds wall-clock time (survived < 1.0 s, stamp stops changing), so a loaded container can trip it. The failing assertion was not captured.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The failing assertion is identified from a repeated --as-root run
- [ ] #2 The test passes 20 runs in 20 under linux-jail-check --as-root, or its bound is changed to what the property needs with the reason in its docstring
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed directly in 8d08424 (2026-11-04). The failing assertion was the control, not the 1 s bound: the program rewrites its stamp by truncating then writing, so two reads landing between saw '' twice and compared equal under load. The control now waits for a time in the stamp, then for a later one. Evidence: the test passed 20 of 20 as root under linux-jail-check, and scripts/check passed twice; linux-jail-check --as-root passed twice in full (364 passed, 1 skipped, 1 xfailed).
<!-- SECTION:NOTES:END -->
