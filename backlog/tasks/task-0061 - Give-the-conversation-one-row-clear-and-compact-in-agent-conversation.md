---
id: TASK-0061
title: 'Give the conversation one row: /clear and /compact in agent:conversation'
status: To Do
assignee: []
created_date: '2026-10-09 03:08'
labels:
  - agent
  - commands
dependencies: []
priority: medium
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Starting a new conversation lives in two plugins and works two ways. `/clear` is `commands:operator`'s: it empties the files its `forget` config names (the transcript's, with no backup), answers `cleared`, then restarts the loop and transcript rows. `/compact` is `agent:compact`'s: it writes the new conversation over the transcript row's file in one step, keeping the old as `.bak` (`.bak.2`, ...), then restarts the same rows. The operator's `forget` has to be kept in step with the transcript row's file by hand, and a `/clear` loses the conversation for good. Found by the review against cordis of 2026-10-09 (the separation, duplicates and docs review).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An `agent:conversation` row owns `/clear` and `/compact` (`agent:compact` folds into it); it finds the transcript row's file from the row as the loader mounted it, as `/compact` does today
- [ ] #2 `/clear` is `/compact`'s rewrite with an empty conversation: written over the transcript row's file in one step, the old kept as `.bak` (`.bak.2`, ...), then the loop and transcript restart; what `commands` holds for the model is dropped as today
- [ ] #3 The operator's `forget` config goes; `bh-02 update-layer` and a resumed session rewrite a layer that sets it or names `agent:compact`, saying what changed
- [ ] #4 A restart either command queued that fails is told through `output.notice`, as both do since df21009
- [ ] #5 CONTRACTS.md, GLOSSARY.md, bh-02/CLAUDE.md, the agent and commands READMEs and the docs site describe the row
<!-- AC:END -->
