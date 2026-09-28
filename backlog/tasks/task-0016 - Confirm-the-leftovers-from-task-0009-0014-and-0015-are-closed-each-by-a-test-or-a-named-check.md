---
id: task-0016
title: >-
  Confirm the leftovers from task-0009, 0014 and 0015 are closed, each by a test
  or a named check
status: In Progress
assignee: []
created_date: '2026-09-28 12:26'
updated_date: '2026-09-28 12:40'
labels: []
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The Done notes of task-0009, task-0014 and task-0015 named items left open. Reading the current code suggests several were closed later, but nothing ties each closure to a test. This task proves each one closed, with a test that exercises the behaviour (added if missing) or, for an operational item, a named check that can be repeated.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A meta.json that is not JSON, lacks a key, or has a wrongly typed value neither crashes startup nor listing; a named test covers it
- [ ] #2 permission_for denies an MCP tool name from any server other than bh (e.g. mcp__other__python) and a bare built-in name; a named test covers it
- [ ] #3 Events gathered while the app draws a batch are drawn once it finishes, even when no further event arrives (a reply pausing mid-stream); a named test covers it
- [ ] #4 /clear removes the earlier conversation from the screen, not only from the model; a named test covers it
- [ ] #5 The REPL's lifecycle line printing onto a live prompt is moot: the REPL no longer exists (bh-02 is a Textual TUI)
- [ ] #6 The bhh-final tag is on the remote (bruk-io/bhh), pointing at 4b7852c
- [ ] #7 No saved bh-02 session names the pre-rename tool (mcp__bhh__), and no bhh session state is left under XDG_STATE_HOME; checked on this machine
<!-- AC:END -->
