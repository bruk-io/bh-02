---
id: task-0014
title: 'bh-02 v1: a TUI harness on bh-01''s tokens'
status: Done
assignee: []
created_date: '2026-09-23 01:43'
updated_date: '2026-09-23 06:40'
labels:
  - bh-02
  - tui
milestone: M3 bh-02 v1
dependencies:
  - task-0013
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The app the repo is for: bh-02, a Textual TUI plus the harness shell. Its theme is generated from bh-01's token CSS by a tool; components carry bh-01's names. The Textual app is bh-02's `ui` row, so the harness stays testable with a fake UI.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `bh-02` launches a Textual app shell: activity bar, conversation (transcript + composer), status bar
- [x] #2 scripts/sync-tokens generates bh-02's theme from bh-01's token CSS; a test fails if the committed theme drifts from what the tool would write
- [x] #3 The transcript shows text, thinking, code cells, tool results (diffs coloured), notes and usage as they stream
- [x] #4 Approvals are a modal that shows a cell or a component's source; Ctrl-C (a binding) interrupts the turn
- [x] #5 A command palette runs the commands broker's commands; the status bar shows model, session, jail grades and usage
- [x] #6 Sessions: a new run is a session, `bh-02 --resume` continues one, the sidebar lists them
- [x] #7 Verified by booting the real app (not only run_test) and by Pilot tests; a live run with Claude answers, runs a cell, and asks for approval
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Live run with Claude (AC #7), 2026-09-23, verification round 1. `bh-02 --model haiku` in a 120x40 pty, driven by a scratch script in /private/tmp/bhv (live.py, live2.py, live3.py), using Claude Code's login. The jail was brig on darwin; the status bar read `jailed fs_write ✓ network ✓ fs_read ✓ env ✓`.
- Claude answered: 'pong' on turn 1.
- Claude ran a jailed python cell (`result = 6 * 7; print(result)`, result 42) with no question, as a confined kernel should, and said 'The number is 42.'
- A cell calling write_file twice asked for approval in the modal for each call. The prompt was "In ONE python cell, call write_file(path='a.txt', content='one') and then write_file(path='b.txt', content='two'). Do nothing else." With `y` on the first, a.txt was written. Ctrl-C with the second modal up (`Allow write_file(path='b.txt' ...)` on screen) took the modal down and showed `stopped: interrupted`. b.txt was never written: `ls /private/tmp/bhv/live2/work` lists only `a.txt` (re-checked in verification round 3).
- `bh-02 --resume` of that session (20260923-003754-52a9) drew the history. The resumed turns were "Reply with exactly: still here" (answered 'still here') and "What two file names did I ask you to write? Answer in lowercase, joined by a plus sign.", answered 'a.txt+b.txt'. That answer is correct because the question is about what was asked, not what is on disk: it shows the resumed session remembered the earlier request. It says nothing about b.txt; the `ls` above is the evidence that the declined write never happened. (Quotes from the session's events.jsonl.)
- Usage: the per-turn chips read $0.1474 and $0.1616. The SDK's own running total after turn 2 was $0.3090, and the status bar showed `usage: 226k in · 244 out · $0.3090`, so the SDK's cumulative total_cost_usd is now turned into per-turn amounts. A direct SDK probe had shown usage is per turn but total_cost_usd is cumulative (0.1388, 0.2915, 0.2998).

Landed on bh-02 via two workflows: foundation b5653ca; features merged from branches m3-theme, m3-transcript, m3-palette-status, m3-sessions (merges ad70523..3601a61, integration b5987d7), three adversarial verification + fix rounds (e8ffd09, e5e5d0e, 0076178), live-run fix 57d26f0. scripts/check green, sync-tokens --check in sync. Live Claude run (haiku, then /model sonnet): answered, ran a jailed cell, approval modal y/n under --no-jail, Ctrl-C mid-reply, /clear. Cost finding: the SDK session inherited the account's claude.ai MCP connectors (118 tools, ~73k prompt tokens, ~$0.14/turn on haiku); strict_mcp_config=True cut a plain turn to ~1.6k tokens / ~$0.003. Left open (minor or deferred): one malformed meta.json crashes startup (fixed first in M4), a gathered event batch flushes only on the next event, /model and /clear take 12-15 s while the Claude CLI restarts, /clear leaves old turns on screen, permission_for is not deny-by-default for non-bhh MCP names.
<!-- SECTION:NOTES:END -->
