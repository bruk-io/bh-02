---
id: TASK-0157
title: >-
  Sweep out the remaining backwards-compatibility code under the
  no-compatibility rule
status: To Do
assignee: []
created_date: '2026-10-18 14:39'
labels:
  - agent
  - app
  - size-3
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner's rule (root CLAUDE.md, Conventions, 2026-10-18): no backwards compatibility before a supported release. Code from before the rule still reads or translates old forms, for example the claude-code provider's records that replay a session from before the provider (models-cordis-plugin claude_code/records.py, the mcp__bh__ prefix), and the prompt's handling of a transcript from before the loop kept edits (agent plugin, test_agent_prompt.py). List every such path across bh-02/ and libs/ first, then remove them.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The notes list every path found that reads, translates or tests an old stored format or name (grep for from before, old, legacy, earlier, compat, and the bh-02 CLAUDE.md naming rule's cases), each with what it kept working
- [ ] #2 Each listed path and the tests pinning it are removed, or the notes say why one is not compatibility (a guard against a name a layer still names, say)
- [ ] #3 The notes say which old files stop working; scripts/check passes
<!-- AC:END -->
