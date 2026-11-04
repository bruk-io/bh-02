---
id: TASK-0188
title: >-
  Find out how Claude Code's extract-memories pass saves memories without the
  main agent
status: To Do
assignee: []
created_date: 2026-10-10 12:15
updated_date: '2026-11-04T12:39:00Z'
labels:
  - memory
  - size-1
  - finish-moved
dependencies: []
priority: low
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The CLI bundled with claude-agent-sdk 0.2.159 (2.1.281) has a background pass that saves memories from a conversation (`querySource` `extract_memories`, event `tengu_extract_memories_extraction`), besides the main agent saving its own. Found while comparing bh-02's auto memory with Claude Code's (2026-10-10), not yet read. bh-02's model saves a memory only when it decides to; if a main agent under-saves, a pass like this is Claude Code's answer. A draft until it is accepted.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The task's notes say when the pass runs, which model, what it reads, what its prompt asks for, what it may write and its limits, each with where in the CLI's code it was read
- [ ] #2 The notes say whether bh-02 should do the same, and a follow-up task is logged if so
- [ ] #3 The notes say how Claude Code's extract-memories pass saves memories without the main agent, naming the bundled CLI version read (SDK 0.2.158)
- [ ] #4 The notes say what of it DRAFT-0002 would reuse
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Lead, 2026-11-04: promoted from a draft review; criteria written right after promotion (finish-moved for that reason only).
<!-- SECTION:NOTES:END -->
