---
id: TASK-0080
title: >-
  Sub-agents the main agent can start from a tool or from code, that I can
  watch, and that can't reach more than their parent
status: To Do
assignee:
  - '@bruk'
created_date: '2026-10-11 15:31'
updated_date: '2026-10-12 22:22'
labels: []
milestone: m-5
dependencies: []
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem
The main agent can't hand work to another agent. I want it to start sub-agents from a tool call or from code in a python input, to watch each one, and to know none can reach anything its parent couldn't. The design so far is in the M6 milestone and decision-0001; it rests on the brig intent (a jail that holds many processes).

## Open questions
- [ ] Where a child's loop runs: in the jail, or on the host.
- [ ] Limits: depth, how many at once, a budget per agent, what Ctrl-C stops.
- [ ] Parallel writers: worktrees, or narrowed jails.
- [ ] Teams: later, or never.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The main agent starts a sub-agent from a tool call and from a python input, and gets its result back
- [ ] #2 I can watch each sub-agent while it runs: a tmux pane when I'm in tmux, a status field and /agents when I'm not
- [ ] #3 A sub-agent reaches nothing its parent couldn't, and agents talk to each other only through bh-02
- [ ] #4 Must not break: approval stays one rule in one row, and a sub-agent's questions come to me, never to its parent
- [ ] #5 Must not break: a conversation's prompt stays fixed, and nothing blocks the TUI's event loop
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner's trim, 2026-10-12: this run delivers .02 to .06 and .09; watching without tmux panes (panes and darwin's check: TASK-0080.10, deferred); project guidance in a child (.07) deferred; TASK-0080.08 parked. From here only blocking review findings are fixed in this run; the rest is filed.
<!-- SECTION:NOTES:END -->
