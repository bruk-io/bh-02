---
id: TASK-0131
title: >-
  brig: a jail whose later helper fails to start ends the helpers it already
  started
status: To Do
assignee: []
created_date: '2026-10-17 03:16'
updated_date: '2026-10-17 19:04'
labels:
  - brig
  - size-1
dependencies: []
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0079.29's worker (2026-10-17), reproduced on an untethered jail: Jail.create with a JAIL_LIFETIME helper followed by a LAUNCH_SCOPED one that fails raises HelperFailed and leaves the first helper running, since _start_helpers has no cleanup on failure. Nobody holds a Jail to destroy, so the helper is orphaned until the host reboots or someone kills it by hand.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 When a helper fails to start, Jail.create ends every helper it already started before raising HelperFailed; a test plants the failure after a JAIL_LIFETIME helper, seen leaving it running before the fix
- [ ] #2 brig's tiers pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Archived 2026-10-17: brig moved to a repository of its own (TASK-0135, archived), and the old libs/brig is frozen until the new one replaces it. The new brig has one helper, the egress proxy, started and stopped as part of the jail, so this cannot happen there.
<!-- SECTION:NOTES:END -->
