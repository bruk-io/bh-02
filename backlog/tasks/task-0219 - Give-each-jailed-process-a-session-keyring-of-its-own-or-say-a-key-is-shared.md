---
id: TASK-0219
title: 'Give each jailed process a session keyring of its own, or say a key is shared'
status: To Do
assignee: []
created_date: '2026-11-09 01:17'
labels:
  - brig
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Measured for TASK-0074 in the Linux container (Docker seccomp unconfined), as an unprivileged user with namespaces held: a process adding a key with add_key to KEY_SPEC_SESSION_KEYRING was found by a sibling with KEYCTL_SEARCH, with the same key id in one shared jail and across two jails started by the same process. So a jailed program can leave a key for another program, in another jail, through the session keyring of what started bh-02. The user keyring is kept apart by the nested user namespace. decision-211 names this as not closed, since two jails do not keep it apart. A likely small fix is keyctl(KEYCTL_JOIN_SESSION_KEYRING, NULL) for each process, not tried. Docker's default seccomp profile may refuse keyctl, so a host's real exposure needs measuring.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A key one jailed process adds to its session keyring is not found by a sibling or a process of another jail, in a test with a control
- [ ] #2 SPEC.md's decision-211 and the jail-and-approval page no longer name it as shared
<!-- AC:END -->
