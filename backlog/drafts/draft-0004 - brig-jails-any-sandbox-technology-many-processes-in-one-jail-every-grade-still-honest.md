---
id: DRAFT-0004
title: >-
  brig jails: any sandbox technology, many processes in one jail, every grade
  still honest
status: Draft
assignee:
  - '@bruk'
created_date: '2026-10-11 15:31'
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
- [ ] #1 A sandbox technology with a life of its own (a container) can be added as a mechanism plus a runtime without changing brig's other mechanisms; a fake runtime proves the protocol in tests, and Docker itself if it is in scope
- [ ] #2 One bwrap jail holds several processes, each stopped without stopping the others, none able to reach another's socket or signal it
- [ ] #3 Must not break: every grade in a report is backed by a probe that plants the violation, and no grade rises without one (laws 1 and 10)
- [ ] #4 Must not break: bh-02's jail guarantees hold: writes only where spec_for allows, no network, secrets unreadable, the mount tripwire, a jail ends with bh-02
- [ ] #5 Must not break: brig stays standalone, the standard library and itself only
<!-- AC:END -->
