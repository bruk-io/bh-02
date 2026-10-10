---
id: TASK-0077
title: >-
  Count a zombie as gone in teardown and liveness, so a jail ends cleanly where
  PID 1 doesn't reap
status: To Do
assignee: []
created_date: '2026-10-10 21:58'
labels:
  - brig
dependencies: []
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Teardown decides a process group is gone by listing its members with `/bin/ps` (libs/brig/src/brig/run/teardown.py), which lists zombies too, and brig reaps only the leader it parented. Where PID 1 doesn't reap (this container's `process_api`, Docker without `--init`), a killed child stays a zombie in the group, so a dead jail can read as surviving. In such a container 5 kill, teardown and probe tests fail (checked 2026-10-10); that brig's own kill report is fooled the same way is read from the code, not run.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Teardown and liveness count a zombie member as gone (process state Z on Linux and darwin)
- [ ] #2 A test plants a zombie in a jail's group under a PID 1 that doesn't reap, and the kill reports the jail ended; it fails before the fix
- [ ] #3 brig's kill, teardown and probe tests pass in a container whose PID 1 doesn't reap
<!-- AC:END -->
