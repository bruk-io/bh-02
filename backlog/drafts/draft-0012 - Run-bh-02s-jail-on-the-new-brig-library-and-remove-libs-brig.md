---
id: DRAFT-0012
title: 'Run bh-02''s jail on the new brig library, and remove libs/brig'
status: Draft
assignee:
  - '@bruk'
created_date: '2026-10-19 03:47'
labels:
  - runner
  - brig
dependencies: []
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem
brig is being rewritten from scratch in its own repository, with a focus on architecture and as little knowledge of bh-02 as it can have (TASK-0135, archived here when it moved). bh-02 still carries the old brig in libs/brig and keeps changing it: on 2026-10-18 alone it gained decisions 204 and 205 and a rework of its test directories (TASK-0150, 0151, 0164 to 0166). The two are diverging, and every fix made here is one the new brig has to make again or show it doesn't need. bh-02 should run its jail on the new library and stop carrying the old one.

## Affected users and systems
- Me, working on brig and bh-02 separately.
- runner-cordis-plugin: jail.py is the only module that imports brig (the brig-one-adapter gate), and its README and CONTRACTS.md's runner row.
- libs/brig, its tests and gate, the root pyproject (workspace members, pytest's pythonpath for brig), scripts/linux-jail-check and the linux-jail CI workflow.
- bh-02's open brig tasks: TASK-0084 (one jail keeps its processes apart, a container as a jail) and TASK-0074 under it.

## Open questions
- [ ] When the new brig is ready to switch to: which of its milestones bh-02 waits for.
- [ ] How bh-02 depends on it: a git dependency pinned to a commit, a path dependency while both change, or a published package.
- [ ] Whether the runner's adapter keeps its shape or follows the new brig's API (reserve-then-start, channels, one jail per session).
- [ ] What happens to TASK-0084, TASK-0074 and the other brig tasks on this board: moved to brig's own board, or closed here.
- [ ] Where brig's Linux jail CI runs after the move: in brig's repository, here, or both.

Drafted by the orchestrator from a conversation with the owner (2026-10-19); the owner corrects it before anyone accepts it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 bh-02's runner jails the Python process and the extensions process through the new brig library, depended on from its own repository, and libs/brig is gone from this workspace
- [ ] #2 Every guarantee of the jail that bh-02 relies on still holds, shown by the runner's tests and the Linux jail tests (writes and network confined, grades reported, /release, the mount tripwire, placeholders, channels, egress decisions), or each one dropped is listed with my agreement
- [ ] #3 What libs/brig gained after the split (decisions 204 and 205, the test-directory fixes) is in the new brig, or recorded as not needed there
- [ ] #4 Must not break: only runner_cordis_plugin imports brig, and --no-jail behaves as before
- [ ] #5 Must not break: scripts/check and the Linux jail CI pass, and the Seatbelt jail works on my Mac
<!-- AC:END -->
