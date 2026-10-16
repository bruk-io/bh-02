---
id: TASK-0108
title: >-
  Check startup files' docstrings against decision-0006's convention, with no
  model
status: To Do
assignee: []
created_date: '2026-10-16 02:03'
updated_date: '2026-10-16 02:51'
labels:
  - python
  - size-3
  - finish-moved
dependencies:
  - TASK-0106
  - TASK-0107
references:
  - >-
    backlog/decisions/decision-0006 -
    Tell-the-model-of-the-functions-the-startup-files-define-by-progressive-disclosure-with-no-decorator.md
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Build decision-0006 point 7's docstring half: ruff (--isolated, D101, D103, D205, D415, D419) plus bh-02's own rule for what ruff has none for (an example; doctest blocks that parse, each with a blank line before it), run in the jail at each REPL start; ruff becomes a dependency of the python plugin. Waits for TASK-0106 (acceptance) and TASK-0107 (it rewrites the aside and the set of told functions this reports on). Open for the plan: the example rule's command name and home, since plugin-layering keeps the app's CLI from importing the python plugin.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Confined, at each REPL start, ruff with bh-02's flags and bh-02's example rule check each startup file in the jail (the person's from the text the host hands the REPL), and tests cover each finding and a file with none
- [ ] #2 The aside names each told function that misses and the rule codes it breaks, never a tool's message text, and a finding never stops a file running or hides a function; unconfined, nothing runs unasked and the python section gives the model the commands
- [ ] #3 The ruff line for CI and a pre-commit hook is documented, and the example rule runs as a command with no session and no model, exiting 1 on a finding and 0 on none
- [ ] #4 scripts/check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-16: finish moved before any work, on the owner's word: ruff does what it has rules for (the probe showed it calls public what decision-0006 point 1 tells, __all__ included), bh-02's own rule only for examples, and it runs in the jail rather than the host. Typing (mypy) split to TASK-0109.
<!-- SECTION:NOTES:END -->
