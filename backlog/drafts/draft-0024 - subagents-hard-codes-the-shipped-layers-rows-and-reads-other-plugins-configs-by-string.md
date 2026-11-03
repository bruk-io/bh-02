---
id: DRAFT-0024
title: >-
  subagents hard-codes the shipped layer's rows and reads other plugins' configs
  by string
status: Draft
assignee: []
created_date: '2026-11-03T17:47:00Z'
labels:
  - subagents
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03: subagents_cordis_plugin/agents.py defaults to 11 row ids from 4 other plugins; child.py hard-codes memory:files, memory:auto, commands:registry and reads or rewrites the transcript row's path and the model row's state and default. A new loop dependency or tool row makes children wait out the 30 s start or go without it; renaming ModelConfig.default silently drops a type's model. Proposed: derive the rows from what loop depends on (cordis already reads provides), or move them into bh-02.toml beside the rows they name; list the cross-plugin config fields in CONTRACTS.md; a boot test that a child of the shipped layer comes up.
<!-- SECTION:DESCRIPTION:END -->
