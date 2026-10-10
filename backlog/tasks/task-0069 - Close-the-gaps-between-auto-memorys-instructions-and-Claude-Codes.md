---
id: TASK-0069
title: Close the gaps between auto memory's instructions and Claude Code's
status: To Do
assignee: []
created_date: '2026-10-10 03:34'
labels:
  - memory
  - docs
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`auto_section` (memory_cordis_plugin/auto.py) tells the model the four kinds of memory, a topic file per memory with `name`/`description`/`type` frontmatter, and a line for each in MEMORY.md. Claude Code's auto memory prompt (read from the CLI bundled with claude-agent-sdk 0.2.159, 2.1.281; it varies behind feature flags) also tells its model these, which bh-02's leaves out:
- Before saving, check for a memory that already covers it, and update that one rather than add a duplicate.
- For `feedback` and `project`, write the rule or fact, then a **Why:** line and a **How to apply:** line.
- Turn relative dates into absolute ones.
- Write `description` as one specific line: it is what decides, later, whether the memory is relevant.
- Don't save what CLAUDE.md, the code or git history already records, or what only matters to this conversation; asked to remember one of those, ask what was non-obvious about it and save that.
- A memory naming a file, function or flag is a claim that it existed when the memory was written: check it still does before recommending it, and for the repository's current state read the code or git log rather than a memory's snapshot.
- Keep each memory file short (Claude Code's recall shows only its first 200 lines or 4 KB) and organised by topic: split or summarise one that outgrows that.

These are judgement rules, so they are prose. The mechanical ones (a slug name, a known `type`, a one-line `description`, the index matching the files) are code in TASK-0068's memory tool, and this task adds no checks for them. Split from TASK-0068 by the owner (2026-10-10); independent of it, so whichever lands second keeps the other's text in the section. The section is in every request's system prompt, so each rule takes as few words as it needs, in bh-02's voice; a conversation started after the change gets it (the prompt stays fixed for one).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `auto_section` tells the model each rule the description lists: check for an existing memory before saving; the **Why:** / **How to apply:** body for `feedback` and `project`; absolute dates; a specific one-line `description`; what not to save, and what to save instead when asked; checking a memory against the code before recommending from it; keeping each memory file short and organised by topic
- [ ] #2 test_memory_auto.py checks that the section says each rule
- [ ] #3 The memory plugin's README and docs/bh-02/using/memory.md, where they say what the model is told about auto memory, say the same
- [ ] #4 `scripts/check` passes
<!-- AC:END -->
