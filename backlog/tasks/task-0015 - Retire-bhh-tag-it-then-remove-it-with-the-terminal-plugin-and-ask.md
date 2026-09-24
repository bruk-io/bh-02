---
id: task-0015
title: 'Retire bhh: tag it, then remove it with the terminal plugin and ask'
status: Done
assignee: []
created_date: '2026-09-23 01:43'
updated_date: '2026-09-23 08:43'
labels:
  - repo
  - bhh
milestone: M4 Retire bhh
dependencies:
  - task-0014
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
bh-02 replaces bhh. A frozen app on live plugins isn't frozen, so bhh is tagged and removed rather than kept.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A git tag bhh-final marks the last commit with bhh
- [x] #2 bhh, terminal-cordis-plugin and the `ask` mode are removed; nothing references them
- [x] #3 Gate rules and docs that existed only for them are gone or rewritten
- [x] #4 The suite, types and gates pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
bhh-final (annotated, local, not pushed) -> 4b7852c: its tree has bhh/ and terminal-cordis-plugin; HEAD's has neither. Removal c997c5d; product renames 211919c (console script bh-02-claude-detached, MCP server 'bh' so the model sees mcp__bh__python, temp prefixes bh-*); three verification+fix rounds c7f128b, 529f50f, 3dec8e1; last doc corrections 7a552d5. ask/one_shot/AskConfig removed from chat; tests needing a one-shot mode use a test-local fragile:one_reply. git grep -i bhh outside backlog/: nothing. scripts/check: format, lint, types, 1578 passed / 8 skipped, gates, tokens ok. Live Claude smoke run after the rename: the model called mcp__bh__python in the jail and answered. Not exercised: resuming a Claude Code session started before the rename (its history names mcp__bhh__python). Old session state under $XDG_STATE_HOME/bhh/sessions is orphaned.
<!-- SECTION:NOTES:END -->
