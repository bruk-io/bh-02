---
id: TASK-0211
title: >-
  Make
  test_a_linux_jail_ends_when_the_host_replaces_or_removes_a_secret_it_holds
  hold under the parallel run
status: To Do
assignee: []
created_date: '2026-11-07 22:25'
labels:
  - runner
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
In the default scripts/linux-jail-check run on a Mac host (Docker, as the unprivileged user under tini) the third start of this test once found project/seen already there: assert not seen.exists() failed. Alone it passed 6 of 6. The likely cause is the test itself: seen is never removed between starts, and the second jail's program may write it in the window between absent.rmdir and the tripwire ending the jail. Seen while doing TASK-0079.31.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The test removes or checks seen per start so a write by an earlier jail cannot fail a later assertion
- [ ] #2 The test passes 20 of 20 in the default scripts/linux-jail-check run
<!-- AC:END -->
