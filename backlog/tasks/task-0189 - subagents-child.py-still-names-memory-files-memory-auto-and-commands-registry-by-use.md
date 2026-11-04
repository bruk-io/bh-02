---
id: TASK-0189
title: >-
  subagents child.py still names memory:files, memory:auto and commands:registry
  by use
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-04T14:14:00Z'
updated_date: '2026-11-04T14:36:00Z'
labels:
  - subagents
  - size-2
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0187 moved the row list to bh-02.toml and listed the cross-plugin config fields, but child.py still hard-codes three component names: _MEMORY_USE and _COMMANDS_USE (a child with a memory row gets a commands registry of its own) and _AUTO_USE (the refusal of auto memory). Derive the first from the component injecting commands (wiring.py walk, cordis metadata) and name the registry and the refused uses in the agents row's config.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 child.py names no other plugin's component
- [ ] #2 a child whose row injects commands gets a registry of its own, derived in wiring.py
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
child.py names no other plugin's component: AgentsConfig gains commands_row and refused (bh-02.toml names them); wiring.py derives which rows inject commands from cordis's resolve(use).inject and passes the predicate to Agents; child_rows copies the parent's commands row's component for a child with such a row. Proof: plugin and app tests, scripts/check on both members.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
child.py no longer has _MEMORY_USE, _AUTO_USE or _COMMANDS_USE (grep for 'memory:' and 'commands:' in child.py finds none). AgentsConfig gained commands_row (default commands) and refused (default none; bh-02.toml names memory:auto); wiring._injects_commands reads cordis.loader.resolve(use).inject and is handed to Agents, which hands it to child_rows. A child's row that injects commands (any, not only memory:files) now gets a registry copying the parent's commands row's component. The auto-memory error now reads 'a child must not have memory:auto (decision-0002...)'. Tests: full bh-02 pytest run 2004 passed before the last app-test fix; test_child_boot and the plugin tests updated, wiring test for the probe row now asserts it is given its own registry. scripts/check bh-02/plugins/subagents-cordis-plugin exit 0 (gates and docs included); scripts/check bh-02/app --no-gates --no-docs exit 0. Criteria left unticked.
<!-- SECTION:NOTES:END -->
