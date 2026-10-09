---
id: TASK-0064
title: Rename the names that collide or mislead
status: Done
assignee: []
created_date: '2026-10-09 03:08'
updated_date: '2026-10-09 23:30'
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
- [x] #1 `chat:session` has a name the glossary uses for nothing else (not `chat:chat`, which doubles as `python:python` did)
- [x] #2 The `harness` row is `shell`, and the `sessions` key is `session`
- [x] #3 The tui's app has one name for its function, component and row
- [x] #4 `layers` is `host`, and `layers.memory` is `auto_memory`; where the person's config directory is stays out of it (`host_paths.config_home`)
- [x] #5 `bh-02 update-layer` and a resumed session translate every old name, saying what changed
- [x] #6 The docs say step where the code means a step, and Python process and extensions process where they mean those; GLOSSARY.md, CONTRACTS.md and the READMEs use the new names
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- `chat:session` is `chat:converse`: the wiring's component is named for what it runs (`chat.converse`, reached through the module, so both keep the name); the package exports the logic, and tests import the component from `chat_cordis_plugin.wiring`.
- The tui's app is `ui` everywhere: function `tui_cordis_plugin.wiring.ui`, component `tui:ui`, row `ui`.
- The shell's pinned rows: `harness` is `shell` (`bh_02.bootstrap:shell`), `layers` is `host` (`bh_02.bootstrap:host`, key `host`, `_Host` with `auto_memory` in place of `memory`), `sessions` is `session` (`bh_02.bootstrap:session`, key `session`). Consumers follow: `runner:confined` (`Host`, was `Layers`), `models:model`/`models:catalog`, `memory:files`/`memory:auto` (`host.auto_memory`), `tui:status` (`session`). `run()` takes `session=` and `auto_memory=`. Where the person's config directory is stays `host_paths.config_home`.
- `update-layer`: row ids `harness`, `layers`, `sessions`; uses `chat:session`, `tui:app` and the three `bh_02.bootstrap:` components. The old status field under the id `session` is still dropped, now only when it is `tui:status` (so the new `session` row is not). Tested in `test_outdated_layers.py`.
- Docs: the names above, "step" where the loop classifies a model step, and "Python process" / "extensions process" for what was "kernel" / "worker" in prose.
<!-- SECTION:NOTES:END -->
