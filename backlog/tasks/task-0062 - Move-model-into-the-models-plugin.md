---
id: TASK-0062
title: Move /model into the models plugin
status: Done
assignee: []
created_date: '2026-10-09 03:08'
updated_date: '2026-10-09 18:53'
labels:
  - models
  - commands
dependencies: []
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`/model` is registered by `commands:operator`, so the operator depends on `models` (the catalog): a composition without `models:catalog` loses `/rows`, `/explain` and `/restart` with it, and the commands plugin knows how a model is chosen. The command belongs beside the catalog it reads. Pairs with the conversation row task (both take a command out of the operator). Found by the review against cordis of 2026-10-09 (the separation, duplicates and docs review).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A `models:switch` row registers `/model` with `commands`: it lists the models, the current one marked, and switches by editing the session layer's model row, as today; it depends on `models`, the loader and `commands`
- [x] #2 `commands:operator` no longer depends on `models`, and a composition without `models:catalog` keeps `/rows`, `/explain` and `/restart` (a test)
- [x] #3 The shipped layer has the row; `bh-02 update-layer` adds it to a layer that has the operator and not it, saying so
- [x] #4 A restart `/model NAME` queued that fails is still told through `output.notice`
- [x] #5 CONTRACTS.md, bh-02/CLAUDE.md, the models and commands READMEs and the docs site say where `/model` is
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The row id is `switch` (/rows shows it beside `models:switch`). `switch.py` holds the command (`Switch`, `SwitchConfig`, `model_list`, `unfinished`) with no cordis import; `wiring.py` the row, `set_model` and `shadowing` (cordis's read_layer/format_layer), moved from the commands plugin. The row keeps its own reload queue (cordis-helpers' `perform`) until TASK-0063's jobs row. The session layer writes `layer` and `model_row` on the switch row now; update-layer (and a resume, silently) moves them off an operator row that sets them, adds the switch row to a layer that fills the operator itself and has none, and says to set them by hand when the layer already has one. The operator no longer depends on `models` (nor `reload`): a test mounts it with no models row and runs /rows.
<!-- SECTION:NOTES:END -->
