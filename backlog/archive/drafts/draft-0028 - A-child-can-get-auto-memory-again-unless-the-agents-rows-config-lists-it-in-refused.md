---
id: DRAFT-0028
title: >-
  A child can get auto memory again unless the agents row's config lists it in
  refused
status: Draft
assignee: []
created_date: '2026-11-04T14:41:00Z'
labels:
  - subagents
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0189 (63d6f38) moved the refusal of memory:auto from child.py into AgentsConfig.refused, which defaults to (). decision-0002's rule (a child never has auto memory: children writing one directory race the parent) now holds only because bh-02.toml writes refused = ["memory:auto"]. A layer's or patch's config replaces the row's config whole (the reason for TASK-0190), and TASK-0190's error tells the person to copy bh-02.toml's rows list: a config with rows and no refused, naming memory-auto among the rows, boots and mounts auto memory in a child with no error. The plugin tests had to add refused to keep the decision-0002 tests passing, so nothing pins the rule without the explicit key. Fix: the safe default must not depend on a layer repeating it, e.g. refused defaults to ("memory:auto",) in AgentsConfig (agents.py, not child.py, so TASK-0189's criterion still holds), or the auto memory component declares itself not for children in cordis metadata and wiring.py reads it as it reads inject.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An agents row whose config gives rows naming the auto memory row and no refused fails at boot with the decision-0002 message
- [ ] #2 A test pins that with no refused key in the row's config
<!-- AC:END -->
