---
id: TASK-0187
title: >-
  subagents hard-codes the shipped layer's rows and reads other plugins' configs
  by string
status: To Do
assignee: []
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-04T12:39:00Z'
labels:
  - subagents
  - size-3
  - finish-moved
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03: subagents_cordis_plugin/agents.py defaults to 11 row ids from 4 other plugins; child.py hard-codes memory:files, memory:auto, commands:registry and reads or rewrites the transcript row's path and the model row's state and default. A new loop dependency or tool row makes children wait out the 30 s start or go without it; renaming ModelConfig.default silently drops a type's model. Proposed: derive the rows from what loop depends on (cordis already reads provides), or move them into bh-02.toml beside the rows they name; list the cross-plugin config fields in CONTRACTS.md; a boot test that a child of the shipped layer comes up.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A boot test brings up a child of the shipped layer with every row the parent's loop depends on (but agents and auto memory)
- [ ] #2 No hand-kept row list in the subagents plugin: derived from what loop depends on, or kept in bh-02.toml beside the rows it names
- [ ] #3 CONTRACTS.md lists the fields subagents reads or rewrites of other rows (the transcript's path, the model's state and default), and a test fails when one is renamed
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).
<!-- SECTION:NOTES:END -->
