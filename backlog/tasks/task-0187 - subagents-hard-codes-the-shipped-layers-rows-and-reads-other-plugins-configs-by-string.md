---
id: TASK-0187
title: >-
  subagents hard-codes the shipped layer's rows and reads other plugins' configs
  by string
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-04T14:15:00Z'
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Keep the row list in bh-02.toml (agents rows, required); app test walks loop inject/provides+requires and boots a child; CONTRACTS section plus field test.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).

Row list: kept in bh-02.toml beside the rows (agents row config `rows`, now required; AgentsConfig has no default). Why not derived: loop's injections give only model, tools, transcript, system, asides, executor; `python` is the loop's `requires`, and memory, on-touch, access contribute to its brokers (system, asides) without loop depending on them, and which contributors a child gets (not agents, not memory-auto) is the layer author's call. So derivation cannot name them and would leave a hand list anyway. The drift (new loop dependency) is caught instead by app/tests/test_child_boot.py: it walks loop's inject/provides (cordis resolve) plus loop requires over the shipped layers and asserts every row is in the agents row's rows. Planted: removed executor from rows in bh-02.toml: the walk test failed (assert {'executor'} == set()) and the boot test failed (child never came up); restored. Also planted a rename of `default` in CONTRACTS.md: the contracts test failed; restored.
Boot test (test_a_child_of_the_shipped_layer_comes_up_with_every_row_the_loop_depends_on): real shipped layers, fake model only; the parent calls agent, the child's real loop/tools/transcript/system/asides/executor/python/memory/on-touch come up within start=10 and report the tool it was offered (python only).
CONTRACTS.md: new section 'Fields one plugin reads or rewrites in another's row' (transcript path; model default and state). Tests: those components have the fields and the section lists them; child_rows with the shipped rows rewrites exactly them.
Subagents tests updated for required rows. Ran: scripts/check bh-02/plugins/subagents-cordis-plugin exit 0 (gates, docs on); scripts/check --no-gates --no-docs bh-02/app exit 0. Not run: full scripts/check and scripts/arch-check (nothing outside members changed). Left over: child.py still names memory:files, memory:auto, commands:registry; filed as a task.
<!-- SECTION:NOTES:END -->
