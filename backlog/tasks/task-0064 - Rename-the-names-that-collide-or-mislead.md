---
id: TASK-0064
title: Rename the names that collide or mislead
status: To Do
assignee: []
created_date: '2026-10-09 03:08'
updated_date: '2026-10-09 03:08'
labels:
  - docs
  - tui
  - chat
dependencies:
  - TASK-0058
priority: low
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Some names say something other than what they name. `chat:session` collides with the glossary's session (a directory under `$XDG_STATE_HOME/bh-02/sessions` a run resumes). The shell pins a row called `harness` (the glossary gives harness four senses) and a key `sessions` that holds one session. The tui's app has three names: the function `tui`, the component `app`, the row `ui`. `layers` holds six unrelated fields (`paths`, `credentials`, `secrets`, `trusted`, `code`, `memory`), all but the first about the host, not the layer files. The docs say the loop classifies each turn where it classifies each step, and still say kernel and worker where the glossary now says Python process and extensions process. Best done with or after TASK-0058, which renames rows too, so `update-layer` translates one table. Found by the review against cordis of 2026-10-09 (the separation, duplicates and docs review).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `chat:session` has a name the glossary uses for nothing else (not `chat:chat`, which doubles as `python:python` did)
- [ ] #2 The `harness` row is `shell`, and the `sessions` key is `session`
- [ ] #3 The tui's app has one name for its function, component and row
- [ ] #4 `layers` is `host`, and `layers.memory` is `auto_memory`; where the person's config directory is stays out of it (`host_paths.config_home`)
- [ ] #5 `bh-02 update-layer` and a resumed session translate every old name, saying what changed
- [ ] #6 The docs say step where the code means a step, and Python process and extensions process where they mean those; GLOSSARY.md, CONTRACTS.md and the READMEs use the new names
<!-- AC:END -->
