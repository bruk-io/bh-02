---
id: TASK-0116
title: >-
  Run arch-check's gates at the same time: 115.6 s to 107.0 s now, more once the
  root gate is fast
status: To Do
assignee: []
created_date: '2026-10-16 08:19'
updated_date: '2026-10-16 08:21'
labels:
  - gates
  - scripts
  - size-2
dependencies: []
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0111. scripts/arch-check runs its five gates (the root and libs/brig, cordis, cordis-helpers, host-paths) one after another. They share nothing: each runs pypeeker in its own directory on its own .pypeeker. Warm, the root gate is 102.7 s and the other four together 12.7 s, so running them at the same time takes the longest, not the sum.

Measured saving: a local, uncommitted edit that submits run_gate for every gate to a ThreadPoolExecutor took scripts/arch-check --no-fix from 115.6 s (three runs: 115.9, 114.1, 115.6) to 107.0 s (107.4, 106.5, 107.0), 8.7 s or 7.5%, on 4 cores with nothing else running. It is worth more once the root gate is faster: with the root gate near 44 s (see TASK-0113, TASK-0114 and TASK-0115), the other four gates' 12.7 s (brig 8.6 of them) would be a fifth of the run, and running them beside the root gate would hide all of it.

What the edit leaves to do: each gate's output must not interleave (capture each gate's output and print it whole, in gate order, as scripts/check does for its steps), a failing gate must still name itself and the exit code stay non-zero if any failed, and the --fix mode (pypeeker applies fixes as a transaction per gate) must be checked for two gates fixing at once; keep --fix as it is if it cannot.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 scripts/arch-check runs its gates at the same time, prints each gate's output whole in gate order, names each failed gate and exits non-zero if any failed; a test shows the gates overlap, as test_check_script does for scripts/check's steps
- [ ] #2 scripts/arch-check --no-fix wall time before and after is recorded in the notes (115.6 s before, warm, 4 cores, nothing else running), and --fix still works or is kept sequential with the reason in the script
<!-- AC:END -->
