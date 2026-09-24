---
id: task-0010
title: >-
  bhh is always CodeAct, with slash commands, resumable sessions and
  model-written components
status: Done
assignee: []
created_date: '2026-09-23 00:51'
updated_date: '2026-09-23 01:21'
labels:
  - bhh
  - codeact
  - cordis
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The user's direction after task-0009: CodeAct is not a flag, it is how bhh works. Then the two pieces of a real coding harness still missing: slash commands (acting on the running composition) and sessions that can be resumed. Then what only cordis can do: a cell mounts a component the model wrote, as a live row, contract-checked and undone with its parent.

Stays true to the design: the layer files remain the only way to change the running program (a session is a layer file of its own that commands edit), commands are a broker like tools, and cordis gains only operator API on the loader.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every subtask is Done
- [x] #2 pytest, ruff, mypy and scripts/arch-check pass
- [x] #3 CONTRACTS.md, the READMEs and CLAUDE.md describe what exists
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
All five subtasks Done. 1416 tests pass (8 skipped, brig's platform-gated); ruff, mypy strict (120 files) and both gates clean. Live with Claude: /model mid-session kept the conversation, /clear dropped it, /rows showed the composition, a session resumed after exit remembered its conversation and model, and a model-written component was mounted (source shown, approved) and its tool called from the next cell. cordis gained operator API only: Loader.restart / explain / a change lock, loader key declared, format_layer. Nothing committed; warden changes still share files.
<!-- SECTION:NOTES:END -->
