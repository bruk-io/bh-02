---
id: TASK-0190
title: >-
  A layer or patch that sets the agents row's config without rows fails at boot
  with a bare dataclass error
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-04T14:18:00Z'
updated_date: '2026-11-04T14:23:00Z'
labels:
  - subagents
  - size-1
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0187 made AgentsConfig.rows required. A patch's config replaces the layer's whole, so a user patch such as config = { start = 60 } on the agents row now fails at boot with cordis's generic 'agents: invalid config for AgentsConfig: __init__() missing 1 required keyword-only argument: rows' (component.py:140). That names the field but not what to write or where the shipped list is, against CLAUDE.md's rule that an error says what to do.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A layer naming subagents:parent without rows fails with a message that says to list the child's rows in the agents row's config and points to bh-02.toml's list
- [ ] #2 A test pins that message
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
finish-moved: the lead asked for the acceptance criteria after promotion (the task had none when the worker began).

Correction: the task already carried criteria #1 and #2 when the worker began (the lead's brief said none); the worker added two duplicates, then removed them. The finish-moved label stays only because the lead asked for it.
<!-- SECTION:NOTES:END -->
