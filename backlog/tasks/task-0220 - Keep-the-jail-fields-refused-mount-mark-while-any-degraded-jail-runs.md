---
id: TASK-0220
title: Keep the jail field's refused-mount mark while any degraded jail runs
status: To Do
assignee: []
created_date: '2026-11-09 17:04'
labels:
  - tui
  - runner
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0074's last review. The status bar's jail field follows only the last start (status.py:299): if one program's jail lost a mount and a later start of the other program gets a healthy jail, the ⚠ clears while the degraded jail still runs, a false all-clear. Unlikely in practice, since a refusal is a property of the host. After /release the mark stays though nothing runs. Also: the Pilot test in test_app.py:309-326 builds the jail forms by hand rather than driving GradesField; the boot-gap fix is covered only with a fake runner; the fakes in test_runner_hooks.py:16-26 and test_python_tool.py lack degraded().
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The mark shows while any running start is degraded, and clears on its stop or on /release, shown by a test with two programs
- [ ] #2 A Pilot test drives GradesField from a runner start to the drawn status bar
- [ ] #3 Every runner fake implements degraded()
<!-- AC:END -->
