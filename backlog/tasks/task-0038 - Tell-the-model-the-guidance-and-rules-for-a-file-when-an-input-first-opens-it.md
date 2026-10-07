---
id: TASK-0038
title: Tell the model the guidance and rules for a file when an input first opens it
status: Done
assignee: []
created_date: '2026-10-07 03:05'
updated_date: '2026-10-07 03:05'
labels:
  - agent
  - kernel
  - context
dependencies: []
references:
  - 'https://github.com/bruk-io/bh-02/pull/8'
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Claude Code loads a subdirectory's CLAUDE.md and path-scoped rules when its Read, Write or Edit touches a matching file. bh-02's one tool carries code, not a path, so bh-02 had no way to bring guidance in on demand; the model was only told such files existed. The kernel's worker is where every input runs, so it is where file use can be heard.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `agent:memory` binds a broker of functions the loop calls after every input with `{code, result, touched}`; each adds a note and none changes the result; notes are sorted (Def. 44)
- [x] #2 `kernel.touched()` is the project files the input's own Python code opened with `open()`/`pathlib`: not `os.open`, imports, listings, tracebacks or a subprocess's files; normalised and treated as the model's word
- [x] #3 `kernel:shell_hints` tells an input that ran cat/sed/ls through a shell how Python does it, once per kind of work a conversation
- [x] #4 A context-file section may name `on_touch`; `context:on_touch` gives a subdirectory's AGENTS.md/CLAUDE.md or a matching path-scoped rule (brace patterns included) whole, once a conversation, through the `system` value's own context files
- [x] #5 `/clear` starts the contributors afresh; a stop after notes were made still tells them
- [x] #6 A booted-app test shows the guidance, the rule and the shell hint reaching the model
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Landed in 6a948bf, 499ae6e, 0586fca and b79e37a: agent:memory, kernel.touched() via a worker audit hook (bounded cost: ~2 hook calls per open at any depth), kernel:shell_hints, context:on_touch with place_touched/rules_touched; cordis_helpers Hooks registrations are now each their own entry. Verified on branch ccr-934e6775-vdsnnr: ruff, mypy and scripts/arch-check clean; pytest bh-02 libs/cordis-helpers -m 'not real_launch' 560 passed (brig jail tests deselected, they fail in a Linux container); real-launch tests 24 passed (test_the_terminal_going_away_leaves_and_ends_the_kernel fails on main in this container too).
<!-- SECTION:FINAL_SUMMARY:END -->
