---
id: TASK-0039
title: >-
  Read the prompt and memory off the event loop, and tell the date with the
  message
status: Done
assignee: []
created_date: '2026-10-07 03:05'
updated_date: '2026-10-07 03:05'
labels:
  - agent
  - context
dependencies: []
references:
  - 'https://github.com/bruk-io/bh-02/pull/8'
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The loop rebuilt the system prompt (every section function, searches of up to 20,000 directories) synchronously before every model call, on the event loop the TUI shares, so a slow section froze the app. And `Today:` in the prompt made every midnight an 'instructions changed' note plus a full copy of the prompt in the transcript.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The prompt and the memory functions run in a worker thread; a test shows the event loop ticking while a slow `system.text()` runs
- [x] #2 A reply stopped at any of the new await points leaves the transcript whole (every call answered once, the person's message kept)
- [x] #3 The date is not in the system prompt; the loop prefixes `(Today's date: ...)` to the first message of a conversation and of each new day, recorded as `today` on the entry
- [x] #4 Providers send only the entry's content; resume does not re-tell the same day's date and `/clear` does
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Landed in c4d9e1a: _told is async with asyncio.to_thread; remembered runs in a thread; describe() lost `today`; LoopModel takes the clock as `today`. Verified on branch ccr-934e6775-vdsnnr: ruff, mypy and scripts/arch-check clean; pytest bh-02 libs/cordis-helpers -m 'not real_launch' 560 passed (brig jail tests deselected, they fail in a Linux container); real-launch tests 24 passed (test_the_terminal_going_away_leaves_and_ends_the_kernel fails on main in this container too).
<!-- SECTION:FINAL_SUMMARY:END -->
