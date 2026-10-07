---
id: TASK-0044
title: Run a shell command from the composer with a ! prefix
status: Done
assignee: []
created_date: '2026-10-07 03:05'
updated_date: '2026-10-07 13:18'
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
- [x] #1 A line starting with `!` runs as a shell command as the person, not as a message to the model
- [x] #2 Prefixes are claimed through the commands broker (one character each, duplicates refused) and chat routes by asking it, not by its own `is_command`
- [x] #3 The command's output is shown and reaches the model with the person's next message, never during a turn
- [x] #4 The command has a timeout and captured output (the TUI owns the terminal)
- [x] #5 Only a layer row may claim a prefix; an extension cannot
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
commands gains claim(prefix, spec, run) and claims(line); chat routes by asking it. commands:shell_command, a layer row, claims ! and runs the line in the person's shell, unjailed, in the project, output captured, with a 120 s timeout. What it printed is shown and held (take_for_model) for the person's next message, never mid-turn; /model and /compact keep it, /clear drops it. A command is cancelled when the input closes, so quitting ends it. The extensions host never passes claims through.
<!-- SECTION:FINAL_SUMMARY:END -->
