---
id: TASK-0047
title: Jail the kernel on Linux with brig's strict_linux preset
status: To Do
assignee: []
created_date: '2026-10-07 03:05'
labels:
  - jail
  - security
dependencies: []
priority: high
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
brig:jail refuses anything but darwin, so on Linux bh-02 runs unjailed and every input asks the person. Auto-approving inputs by reading their code cannot prove them harmless; confinement can.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 brig:jail starts the kernel and the extensions' worker on Linux under brig's strict_linux preset
- [ ] #2 The jail's report grades writes and network as enforced when they are, so inputs run without asking
- [ ] #3 The interpreter and its imports are readable under the preset's allowlist; the credential files and session state are not
- [ ] #4 Integration tests run on Linux
<!-- AC:END -->
