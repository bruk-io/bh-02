---
id: TASK-0044
title: Run a shell command from the composer with a ! prefix
status: To Do
assignee: []
created_date: '2026-10-07 03:05'
updated_date: '2026-10-07 03:06'
labels:
  - commands
  - chat
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Claude Code runs a line starting with `!` as a shell command and gives its output to the model. In bh-02 chat decides what is a command with its own `is_command`, separate from the commands registry, and commands cannot be interrupted with Ctrl-C, so a prefix needs more than a new registration. A review of the design against cordis is in the session that produced PR #8.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A line starting with `!` runs as a shell command as the person, not as a message to the model
- [ ] #2 Prefixes are claimed through the commands broker (one character each, duplicates refused) and chat routes by asking it, not by its own `is_command`
- [ ] #3 The command's output is shown and reaches the model with the person's next message, never during a turn
- [ ] #4 The command has a timeout and captured output (the TUI owns the terminal)
- [ ] #5 Only a layer row may claim a prefix; an extension cannot
<!-- AC:END -->
