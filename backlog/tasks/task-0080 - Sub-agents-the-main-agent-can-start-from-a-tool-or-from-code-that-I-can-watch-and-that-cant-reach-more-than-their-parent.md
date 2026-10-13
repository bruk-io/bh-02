---
id: TASK-0080
title: >-
  Sub-agents the main agent can start from a tool or from code, that I can
  watch, and that can't reach more than their parent
status: Done
assignee:
  - '@bruk'
created_date: '2026-10-11 15:31'
updated_date: '2026-10-13 02:03'
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
- [x] Where a child's loop runs: in the jail, or on the host. (On the host, in a sealed realm: decision-0002.)
- [x] Limits: depth, how many at once, a budget per agent, what Ctrl-C stops. (decision-0002's Limits; built in TASK-0080.04 and .05.)
- [x] Parallel writers: worktrees, or narrowed jails. (Cooperative for now, enforced isolation later: decision-0002.)
- [x] Teams: later, or never. (Not in this milestone: decision-0002.)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The main agent starts a sub-agent from a tool call and from a python input, and gets its result back
- [x] #2 I can watch each sub-agent while it runs: its event log through bh-02 watch, a status field and /agents, in tmux or not (the tmux pane per sub-agent deferred by the owner's trim, 2026-10-12: TASK-0080.10)
- [x] #3 A sub-agent reaches nothing its parent couldn't, and agents talk to each other only through bh-02
- [x] #4 Must not break: approval stays one rule in one row, and a sub-agent's questions come to me, never to its parent
- [x] #5 Must not break: a conversation's prompt stays fixed, and nothing blocks the TUI's event loop
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner's trim, 2026-10-12: this run delivers .02 to .06 and .09; watching without tmux panes (panes and darwin's check: TASK-0080.10, deferred); project guidance in a child (.07) deferred; TASK-0080.08 parked. From here only blocking review findings are fixed in this run; the rest is filed.

Finish line changed after the work began (2026-10-13), on the owner's trim of 2026-10-12: AC #2's 'a tmux pane when I'm in tmux' became the event log through bh-02 watch, the status field and /agents, in tmux or not; the pane is TASK-0080.10. The deferred children (.07, .08, .10, .11) moved to the new intent TASK-0086, and TASK-0074 to TASK-0084, so this intent closes on its own finish line.

Closed on intent review (Opus, low) at acae028: CLOSE, all five criteria met, nothing blocking. #1 the tools registered harness (agents wiring.py:176-179), the python path tools.agent, the real-launch test. #2 event log 0600 O_EXCL|O_NOFOLLOW, bh-02 watch, the agents_status row; the reworded AC fairly reads the owner's trim. #3 the seal (only runner, approval, host, asker), depth one, a child's python jailed, teardown proven by pid, no agent tools in a child. #4 approval one rule (.02 changed only unasked); a child's questions reach the person labelled. #5 the prompt kept in the transcript, the agents section read on the executor; log and type-file I/O through to_thread. Open questions answered by decision-0002 or carried in TASK-0086 and TASK-0084. Should-fix filed to TASK-0080.11: _claim's two mkdir calls run on the event loop.
<!-- SECTION:NOTES:END -->
