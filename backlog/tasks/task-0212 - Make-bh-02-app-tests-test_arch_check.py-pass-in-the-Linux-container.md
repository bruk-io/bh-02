---
id: TASK-0212
title: Make bh-02/app/tests/test_arch_check.py pass in the Linux container
status: To Do
assignee: []
created_date: '2026-11-07 22:31'
labels:
  - app
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Run in the scripts/linux-jail-check container, serially, as the unprivileged user under tini, 25 of its 40 tests fail: the output that scripts/arch-check prints is empty where a pypeeker report or an index line is expected, and exits are 1 where 0 is expected. On the Mac they pass. The test loads only scripts/arch-check and the standard library. Seen while doing TASK-0079.31, whose diff it cannot reach.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Why the 25 fail in the container is found and said in the notes
- [ ] #2 The file passes in scripts/linux-jail-check run on it alone, or skips there by name saying why
<!-- AC:END -->
