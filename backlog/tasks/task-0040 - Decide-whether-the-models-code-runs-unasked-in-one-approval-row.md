---
id: TASK-0040
title: Decide whether the model's code runs unasked in one approval row
status: Done
assignee: []
created_date: '2026-10-07 03:05'
updated_date: '2026-10-07 03:05'
labels:
  - kernel
  - agent
  - extensions
  - security
dependencies: []
references:
  - 'https://github.com/bruk-io/bh-02/pull/8'
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The rule 'run without asking when the jail confines writes and network, otherwise ask the person' was written twice, in the loop and in the extensions host (with a copy of is_confined), so the two could drift apart on a security decision.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `kernel:approval` binds `approval`: `confined` and `approve(request)` (yes when confined, else the person's answer, no when nobody can be asked)
- [x] #2 It depends on `jail` and `output`, not `kernel`, so `/clear` leaves it up
- [x] #3 `agent:loop` and `extensions:extensions` ask it; the duplicate rule is gone and the request shapes are unchanged
- [x] #4 Only a layer may replace it; a booted unjailed test shows an input and an extension load both asked through it
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Landed in 58a5cec (kernel_cordis_plugin/approval.py, wiring, loop and extensions use, bh-02.toml row). Verified on branch ccr-934e6775-vdsnnr: ruff, mypy and scripts/arch-check clean; pytest bh-02 libs/cordis-helpers -m 'not real_launch' 560 passed (brig jail tests deselected, they fail in a Linux container); real-launch tests 24 passed (test_the_terminal_going_away_leaves_and_ends_the_kernel fails on main in this container too).
<!-- SECTION:FINAL_SUMMARY:END -->
