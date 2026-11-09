---
id: TASK-0218
title: >-
  Make
  test_a_linux_jail_ends_when_the_host_renames_over_a_write_deny_and_a_new_one_holds_it
  hold: a write in the tripwire's window fails its later assertion
status: To Do
assignee: []
created_date: '2026-11-08 23:07'
labels:
  - runner
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The test's program appends to .git/config every 100 ms. The host's rename detaches the mount, and in the milliseconds before the tripwire ends the jail the program can get one write in, which the module docstring already names. The test never clears that line, so the second jail's 'planted not in config' assertion fails on it. Measured in the Linux container as the unprivileged user: 1 of 30 at main d1c60cf7's plugin code, 2 of 30 with TASK-0074, each failure one planted line. Same shape as TASK-0211.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The test checks the second jail against what the file held when that jail started, so a write by the first jail in its known window cannot fail it, and a write by the second still does
- [ ] #2 The test passes 30 of 30 in the Linux container
<!-- AC:END -->
