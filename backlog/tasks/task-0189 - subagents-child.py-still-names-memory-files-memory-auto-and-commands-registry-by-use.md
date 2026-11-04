---
id: TASK-0189
title: >-
  subagents child.py still names memory:files, memory:auto and commands:registry
  by use
status: To Do
assignee: []
created_date: '2026-11-04T14:14:00Z'
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
