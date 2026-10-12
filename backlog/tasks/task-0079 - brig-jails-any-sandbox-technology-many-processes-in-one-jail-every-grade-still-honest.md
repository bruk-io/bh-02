---
id: TASK-0079
title: >-
  brig jails: any sandbox technology, many processes in one jail, every grade
  still honest
status: To Do
assignee:
  - '@bruk'
created_date: '2026-10-11 15:31'
updated_date: '2026-10-12 16:46'
labels: []
dependencies: []
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem
brig can only run a jail as a command prefix around processes it starts itself, so a Docker container, a VM or a remote sandbox can't be a jail, and a jail holds one process per instance. bh-02 therefore starts a jail per program, and sub-agents would start one per REPL, which is too expensive to be the default. Reviewing the design also found brig's own host-side helpers import from the workload's directory (TASK-0075). decision-0001 (proposed) is the design so far.

## Open questions
- [ ] Does decision-0001 describe the brig we want? Its own open questions: nested user namespaces on bh-02's hosts, where records live, a control battery without privileges, the namespace bundle's cost.
- [ ] Is Docker a goal now, or a shape the design must not rule out?
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Must not break: every grade in a report is backed by a probe that plants the violation, and no grade rises without one (laws 1 and 10)
- [ ] #2 Must not break: bh-02's jail guarantees hold: writes only where spec_for allows, no network, secrets unreadable, the mount tripwire, a jail ends with bh-02
- [ ] #3 Must not break: brig stays standalone, the standard library and itself only
- [ ] #4 A runtime is a seam of its own: a fake runtime implements the protocol and proves it in tests (a container runtime, Docker included, is TASK-0084's)
- [ ] #5 One bwrap jail holds several processes, each started, waited for and stopped without stopping the others, each with its own socket reserved in the jail's channel directory (keeping them apart from each other is TASK-0084's)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Scope narrowed by the owner (2026-10-12, option B of four): this intent closes on brig's runtime seam, Jail and Process, the channel directory with reserve-then-start and the Spec naming channels (TASK-0079.05, .31, .32, and .33's socket check), and bh-02's one jail per session (TASK-0074); then the sub-agents milestone. Deferred to a new intent, TASK-0084: bwrap's supervisor, per-process isolation, the control battery, OCI and Docker, the macOS checks, and follow-ups .21, .22 and .29. Criteria 1 and 2 were narrowed to match (counted as a finish line changed after work started); the three must-not-breaks stand.

Order changed by the owner (2026-10-12): the sub-agents milestone (M6) runs now; TASK-0079.31, .32 and TASK-0074 follow the owner's Mac run of the darwin dial (TASK-0079.34), because .31 makes bh-02 on macOS depend on it.
<!-- SECTION:NOTES:END -->
