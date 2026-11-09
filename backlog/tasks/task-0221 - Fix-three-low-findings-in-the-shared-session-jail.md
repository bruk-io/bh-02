---
id: TASK-0221
title: Fix three low findings in the shared session jail
status: To Do
assignee: []
created_date: '2026-11-09 17:04'
labels:
  - runner
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0074's first pre-merge review, read and not run: a cancelled start can orphan a program in a shared jail, because its to_thread isn't shielded as _launched is (jail.py, the start path near the old line 1250); release can report a dead jail as running after a tripwire kill with no owner stop (near the old line 1185); the jail is keyed on the resolved cwd but compiled from the raw one, so two spellings share a jail whose roots follow the first (near the old 1243, 1288). Also _every_jail_ended is duplicated in runner-cordis-plugin/tests/conftest.py and bh-02/app/tests/test_python_repl.py.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each of the three is shown by a test, then fixed, or the notes say why it cannot happen
- [ ] #2 _every_jail_ended lives in one place
<!-- AC:END -->
