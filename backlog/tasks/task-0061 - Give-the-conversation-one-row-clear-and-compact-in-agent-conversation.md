---
id: TASK-0061
title: 'Give the conversation one row: /clear and /compact in agent:conversation'
status: Done
assignee: []
created_date: '2026-10-09 03:08'
updated_date: '2026-10-09 19:06'
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
- [x] #1 An `agent:conversation` row owns `/clear` and `/compact` (`agent:compact` folds into it); it finds the transcript row's file from the row as the loader mounted it, as `/compact` does today
- [x] #2 `/clear` is `/compact`'s rewrite with an empty conversation: written over the transcript row's file in one step, the old kept as `.bak` (`.bak.2`, ...), then the loop and transcript restart; what `commands` holds for the model is dropped as today
- [x] #3 The operator's `forget` config goes; `bh-02 update-layer` and a resumed session rewrite a layer that sets it or names `agent:compact`, saying what changed
- [x] #4 A restart either command queued that fails is told through `output.notice`, as both do since df21009
- [x] #5 CONTRACTS.md, GLOSSARY.md, bh-02/CLAUDE.md, the agent and commands READMEs and the docs site describe the row
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
agent:compact became agent:conversation (compact.py is conversation.py; CompactConfig is ConversationConfig, which gains `clear`, the rows /clear restarts: loop, transcript, kernel). /clear finds the file as /compact does (kept_in) and writes [] over it with transcript.rewrite, so the old conversation is the .bak beside it. A transcript with nothing in it yet, one in memory, or one another component fills is not written: its restart is the new conversation. Both commands share the row's one restart queue and one unrestarted() notice, which now names /rows and /restart TRANSCRIPT. The operator lost /clear and its config entirely (the component takes none). update-layer and a resume: the compact row (or any using agent:compact) is renamed to conversation keeping its config; an operator's `clear` moves to a conversation row (added after the operator unless the layer has one, then set by hand), its `forget` is dropped, and a layer that fills the operator itself and has no conversation row gets one. The session layer writes no operator row any more. The ui's `carried` handling stays, for files an older bh-02 emptied.
<!-- SECTION:NOTES:END -->
