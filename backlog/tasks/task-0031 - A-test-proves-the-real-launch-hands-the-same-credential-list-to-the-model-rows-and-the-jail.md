---
id: task-0031
title: >-
  A test proves the real launch hands the same credential list to the model rows
  and the jail
status: To Do
assignee: []
created_date: '2026-09-30 14:48'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0023. test_credential_search shows credential_search() and unreadable() agree by construction, but nothing checks that bh_02.cli's launch actually passes the same list to layers.credentials (what the model rows search) and to the jail's secrets. A later edit to the launch could split them again and reopen the planted-credential hole.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A test boots the composition the way the bh-02 command does and asserts every path in layers.credentials is among the jail's secrets
- [ ] #2 The test fails when the launch passes a different list to either side (shown by a deliberate break, then reverted)
- [ ] #3 scripts/check passes
<!-- AC:END -->
