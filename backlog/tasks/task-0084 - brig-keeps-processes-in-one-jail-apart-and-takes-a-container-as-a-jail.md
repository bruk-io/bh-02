---
id: TASK-0084
title: 'brig keeps processes in one jail apart, and takes a container as a jail'
status: To Do
assignee:
  - '@bruk'
created_date: '2026-10-12 14:45'
updated_date: '2026-10-12 22:22'
labels: []
dependencies: []
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem
Deferred from TASK-0079 by the owner's scope call (2026-10-12, option B). TASK-0079 gives brig a runtime seam, Jail and Process, a channel directory and one jail many processes; bh-02 runs a session in one jail on it. Processes in one bwrap jail still share it: they can reach each other's sockets and signal each other (decision-0001 grades that as shared media). And no runtime but the host exists: a container can't be a jail yet.

## Outcome
Processes in one bwrap jail can't reach each other's sockets or signal each other, with control graded per scope by a battery that plants survivors; and a container is a brig jail through an OCI mechanism and runtime, Docker included.

## Must not break
TASK-0079's guarantees: every grade backed by a probe that plants the violation, none rising without one; bh-02's jail guarantees; brig standalone.

## The work, moved here from TASK-0079
TASK-0079.06 (bwrap's supervisor), .07 (the namespace bundle), .08 (the control battery), .09 (the OCI mechanism and runtime), .10 (the supervisor as a container's agent), .15 (the macOS checks), .21 (interpreters' start cost), .22 (bwrap's writable /dev), .29 (helpers ending with their creator). decision-0001 is the design; TASK-0079.01's notes hold the measurements.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One bwrap jail's processes can't reach each other's sockets or signal each other (decision-0001's per-process namespace bundle), each stopped without stopping the others
- [ ] #2 Control is graded per scope from a battery that plants survivors; no grade rises without it
- [ ] #3 A sandbox technology with a life of its own (a container) is added as a mechanism plus a runtime without changing brig's other mechanisms, Docker included
- [ ] #4 Must not break: every grade backed by a probe that plants the violation; bh-02's jail guarantees; brig standalone, the standard library and itself only
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner's trim, 2026-10-12: TASK-0074 (one jail per session) joins this deferred intent.
<!-- SECTION:NOTES:END -->
