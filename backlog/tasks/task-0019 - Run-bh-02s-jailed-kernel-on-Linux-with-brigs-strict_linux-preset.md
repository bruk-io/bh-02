---
id: task-0019
title: Run bh-02's jailed kernel on Linux with brig's strict_linux preset
status: To Do
assignee: []
created_date: '2026-09-28 12:26'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
brig:jail only runs on darwin (seatbelt); elsewhere it refuses and points at kernel:unjailed. brig already has a Linux stack (strict_linux: bwrap, rlimits, env scrub), but it reads by allowlist and has never run under bh-02, whose kernel needs the interpreter's whole tree readable. A Linux user should get the same jail guarantees as a darwin user.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 On Linux with bwrap, brig:jail starts the kernel and a cell can import the standard library and project code and write under the project root
- [ ] #2 In the Linux jail a cell cannot write the layer files, the host's import paths or brig's self-modify list, cannot read local.env or the sessions' state, and has no network
- [ ] #3 Verified by a real bwrap run (e.g. in a Linux container), not only by compile-path unit tests; the run is reproducible from a script or documented command
- [ ] #4 darwin behaviour is unchanged and scripts/check passes on darwin
<!-- AC:END -->
