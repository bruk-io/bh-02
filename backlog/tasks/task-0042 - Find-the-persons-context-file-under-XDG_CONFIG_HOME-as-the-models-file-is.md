---
id: TASK-0042
title: 'Find the person''s context file under $XDG_CONFIG_HOME, as the models file is'
status: Done
assignee: []
created_date: '2026-10-07 03:05'
updated_date: '2026-10-07 03:05'
labels:
  - context
dependencies: []
references:
  - 'https://github.com/bruk-io/bh-02/pull/8'
priority: low
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The person's context file was always ~/.config/bh-02/context.toml while the models file honours XDG_CONFIG_HOME, so a person with XDG set had their context file silently ignored.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The default is `$XDG_CONFIG_HOME/bh-02/context.toml`, else `~/.config/bh-02/context.toml`
- [x] #2 A file found there inside the project is held to the project's terms
- [x] #3 Docs and error messages name the path the way the models file's do
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Landed in 60efd2b (context_file._located). Verified on branch ccr-934e6775-vdsnnr: ruff, mypy and scripts/arch-check clean; pytest bh-02 libs/cordis-helpers -m 'not real_launch' 560 passed (brig jail tests deselected, they fail in a Linux container); real-launch tests 24 passed (test_the_terminal_going_away_leaves_and_ends_the_kernel fails on main in this container too).
<!-- SECTION:FINAL_SUMMARY:END -->
