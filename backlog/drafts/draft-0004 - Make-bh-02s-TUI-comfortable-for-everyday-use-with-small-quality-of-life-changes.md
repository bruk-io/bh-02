---
id: DRAFT-0004
title: >-
  Make bh-02's TUI comfortable for everyday use with small quality-of-life
  changes
status: Draft
assignee:
  - '@bruk'
created_date: '2026-10-14 00:01'
updated_date: '2026-10-14 00:01'
labels:
  - tui
dependencies: []
priority: medium
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem
bh-02 works, but its TUI lacks the small conveniences I lean on in Claude Code, and each gap is friction every day. The first one: typing / in the composer shows nothing, so I have to remember a command's name or open the palette (Ctrl-P) to find it. There are more like it; each is small, and together they decide whether I reach for bh-02 or for something else.

## Outcome
The everyday things I do in the TUI take no more thought than in Claude Code, starting with finding and running a command by typing /. Each change is small, lives where it belongs (how things look and the keys that reach them in the tui plugin; what a command does in the plugin that registers it), and leaves the composition as it is.

## Must not break
- tui:ui depends on nothing but its config, so no reload restarts the app or loses the transcript.
- Nothing blocks the event loop the TUI shares.
- commands stays a neutral broker the TUI reads, not the TUI's (decision-0003); the ui runs no command itself.
- The Ctrl-P palette, the question screen and Ctrl-C keep working as they do.

## Open questions
- [x] Should commands be owned by the TUI? No: they stay a neutral broker (decision-0003).
- [ ] Which other quality-of-life changes belong here: I have more in mind and will list them; each becomes a task under this intent.
- [ ] Their order after slash completion.

Drafted by the orchestrator from the owner's words (2026-10-13/14); the owner corrects it before anyone accepts it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Typing / in the composer shows the commands that match, and choosing one runs it or finishes its arguments, as decision-0003 sets out
- [ ] #2 Each further quality-of-life change the owner names is a task under this intent, done or dropped by the owner
- [ ] #3 Must not break: tui:ui depends on nothing; nothing blocks the event loop; commands stays a neutral broker and the ui runs no command itself; the palette, the question screen and Ctrl-C work as before
<!-- AC:END -->
