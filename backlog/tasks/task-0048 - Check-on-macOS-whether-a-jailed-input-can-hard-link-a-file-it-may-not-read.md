---
id: TASK-0048
title: Check on macOS whether a jailed input can hard-link a file it may not read
status: To Do
assignee: []
created_date: '2026-10-07 03:05'
labels:
  - jail
  - security
dependencies: []
priority: medium
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The context files skip hard links in the project, but whether Seatbelt lets a jailed input create one to a read-denied file (local.env, ~/.ssh) is unknown. If it can, other readers in bh-02's own process (the models file's path checks, startup files) need the same guard.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A test on darwin records whether `os.link` to a read-denied file succeeds inside brig's jail
- [ ] #2 If it does, every file bh-02 reads on the model's behalf refuses a hard-linked one, with a test
<!-- AC:END -->
