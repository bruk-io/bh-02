---
id: TASK-0078
title: Never signal a process group named by a record brig can't verify
status: To Do
assignee: []
created_date: '2026-10-10 21:58'
labels:
  - brig
  - runner
dependencies: []
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`recycled(pid, stamp)` returns False for an empty stamp (libs/brig/src/brig/run/_identity.py:159), so teardown goes on to signal the group a record names. Exec registrations are files under `<jail_dir>/execs/`, and SPEC.md calls a `jail_dir` writable from inside 'the ordinary arrangement', so a forged registration with an empty stamp could aim the kill ladder at any group. Whether bh-02's jails can write their `jail_dir` (a `/tmp/bh-j-*` directory) is unchecked. Found by the brig-internals review of decision-0001, which treats records as kill authority.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Teardown never signals a group whose record's identity it can't verify, and says so in the kill report
- [ ] #2 A test plants a registration with an empty stamp naming a decoy group; the decoy survives the jail's kill; the test fails before the fix
- [ ] #3 The task records whether bh-02's jails can write their jail_dir, checked on Linux and macOS
<!-- AC:END -->
