---
id: TASK-0062
title: Move /model into the models plugin
status: To Do
assignee: []
created_date: '2026-10-09 03:08'
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
- [ ] #1 A `models:switch` row registers `/model` with `commands`: it lists the models, the current one marked, and switches by editing the session layer's model row, as today; it depends on `models`, the loader and `commands`
- [ ] #2 `commands:operator` no longer depends on `models`, and a composition without `models:catalog` keeps `/rows`, `/explain` and `/restart` (a test)
- [ ] #3 The shipped layer has the row; `bh-02 update-layer` adds it to a layer that has the operator and not it, saying so
- [ ] #4 A restart `/model NAME` queued that fails is still told through `output.notice`
- [ ] #5 CONTRACTS.md, bh-02/CLAUDE.md, the models and commands READMEs and the docs site say where `/model` is
<!-- AC:END -->
