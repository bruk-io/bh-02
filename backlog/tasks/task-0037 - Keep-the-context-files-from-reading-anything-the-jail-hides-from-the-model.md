---
id: TASK-0037
title: Keep the context files from reading anything the jail hides from the model
status: Done
assignee: []
created_date: '2026-10-07 03:05'
updated_date: '2026-10-07 03:05'
labels:
  - context
  - security
dependencies: []
references:
  - 'https://github.com/bruk-io/bh-02/pull/8'
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
bh-02 reads the files a context file names in its own unjailed process, and the project's `.bh-02/context.toml` is the model's to write. A review reproduced fake secrets (`../local.env`, `~/.ssh/...`) leaking into the prompt through it, through a symlink found by bh-02's own defaults, and later through a context file the model linked in from the jail's scratch directory.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The project's context file may name only bh-02's own functions and non-hidden files in the project, and may not `replace` the person's sections
- [x] #2 A context file is the project's when its path as named or as resolved is in the project (a link to a file outside it included)
- [x] #3 A file reached from the project stays in it; a symlink in the project counts only when it leads to another file the section found; a hard link in the project is not read
- [x] #4 No file named like a secret (`local.env`, `.env`, `*.env`) is ever read
- [x] #5 Regression tests reproduce each leak with fake secrets and fail without the fix
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed in ea5d7a2 and 3d25fae (`_kept`, `_writable`, `parse`'s untrusted checks). The leak repros now read nothing; tests for symlinked file, symlinked directory and hard link fail without the fix. Verified on branch ccr-934e6775-vdsnnr: ruff, mypy and scripts/arch-check clean; pytest bh-02 libs/cordis-helpers -m 'not real_launch' 560 passed (brig jail tests deselected, they fail in a Linux container); real-launch tests 24 passed (test_the_terminal_going_away_leaves_and_ends_the_kernel fails on main in this container too).
<!-- SECTION:FINAL_SUMMARY:END -->
