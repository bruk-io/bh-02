---
id: DRAFT-0005
title: Decide whether the memory tool refuses a memory over Claude Code's recall cap
status: Draft
assignee: []
created_date: '2026-10-14 14:46'
labels:
  - memory
  - size-1
dependencies: []
priority: low
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raised by TASK-0069's worker (2026-10-14); captured by the owner as a spike, not to be taken on soon (left a draft on purpose). Claude Code's recall shows only the first 200 lines or 4 KB of a memory file. TASK-0069 tells the model to keep each memory short and organised by topic, but that is prose only. TASK-0068's memory tool checks the mechanical rules (a slug name, a known type, a one-line description, the index matching the files) and not size. Question: should the tool refuse (or warn on) a memory over the cap, and if so, which cap (lines, bytes, both), where it is checked (the tool, a test of the files, nowhere), and what the refusal says. Depends on how TASK-0068's tool lands; answer it once that tool exists.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The answer is written down: refuse, warn or leave it to the prompt, with the cap and the reason, in this task's notes or a decision
- [ ] #2 If the answer is to check it, a follow-up task with its finish line is filed against TASK-0068's tool
<!-- AC:END -->
