---
id: task-0035
title: >-
  On darwin a jailed program that leaves its process group still ends with the
  jail
status: To Do
assignee: []
created_date: '2026-10-01 02:33'
labels: []
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0029. Seatbelt has no namespace, so brig's teardown and the new tether are process-group-shaped. A program a cell starts in its own session (setsid, start_new_session=True, a double-forking daemon) survives a SIGKILLed bh-02, a normal stop and /restart kernel, and keeps the jail's write access to the project. Linux closes this with bwrap's pid namespace. Measured before and after task-0029 and documented in the plugin README.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 On darwin a cell's program that calls setsid (and one that double-forks) is ended when the jail stops normally, on /restart kernel, and when bh-02 is SIGKILLed; real seatbelt tests show each
- [ ] #2 Programs outside the jail are never touched by that teardown (a negative control)
- [ ] #3 If some escape can't be ended on darwin, the README and the jail's report say exactly which, and the task notes give the evidence
- [ ] #4 scripts/check passes
<!-- AC:END -->
