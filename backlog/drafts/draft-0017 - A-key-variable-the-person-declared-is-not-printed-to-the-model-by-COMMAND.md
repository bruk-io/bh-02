---
id: DRAFT-0017
title: A key variable the person declared is not printed to the model by !COMMAND
status: Draft
assignee: []
created_date: '2026-10-25 18:03'
labels:
  - size-2
dependencies: []
parent_task_id: TASK-0169
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the spike TASK-0169.01. `!COMMAND` (a line the person starts with a prefix) runs in bh-02's whole environment less `ANTHROPIC_*` and `CLAUDE*`, and what it prints is put in front of the model on the next message. Once provider keys come from the process environment (TASK-0169), `!env` or any command that prints its environment shows a key such as `OPENROUTER_API_KEY` to the model. The `ANTHROPIC_*`/`CLAUDE*` drop exists for exactly this reason; keys the person names in the models file are the same case.

`--no-jail` as a whole stays unscrubbed (a decision in TASK-0169); this concerns the `!COMMAND` output path.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A command run with `!` does not have, in its environment, any variable that a `key = { env = ... }` in the models file names, and a test shows `!env` output lacks it while other variables remain.
- [ ] #2 The commands plugin's docs and docstring say which variables are dropped and why, and scripts/check passes.
<!-- AC:END -->
