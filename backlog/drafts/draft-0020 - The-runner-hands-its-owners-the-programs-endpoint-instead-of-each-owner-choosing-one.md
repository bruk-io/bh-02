---
id: DRAFT-0020
title: >-
  The runner hands its owners the program's endpoint, instead of each owner
  choosing one
status: Draft
assignee: []
created_date: '2026-11-02T17:24:00Z'
labels:
  - runner
  - size-3
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the architecture review of the bh-02/brig seam, 2026-11-02 (TASK-0176). Today the owners choose the program's socket path in their own directories (python_cordis_plugin.client, extensions_cordis_plugin.host) and pass it to runner.start(argv, cwd, endpoint). The new brig reserves the endpoint itself (reserve_channels) before the jail starts, so the runner must hand it to the owner before the owner builds argv. That changes CONTRACTS.md's runner shape, both owners, Unjailed and extensions_cordis_plugin.testing: the swap is not the adapter alone, as decision-0011 says. Landing the contract change first, against the old brig (a callable argv_for(endpoint), or a reserve-then-start pair), keeps the swap's diff to the adapter. Decision-0005 in the new brig makes readiness a property of one connection, so the owners' own re-dial is unverified; ask brig to hand back the verified connection (or a verifying connect) as part of this.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 runner.start's contract gives the owner its endpoint rather than taking one, in CONTRACTS.md and in every implementation and fake
- [ ] #2 scripts/check passes
<!-- AC:END -->
