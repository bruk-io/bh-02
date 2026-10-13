---
id: TASK-0086
title: 'Sub-agents, after the first run: what TASK-0080''s run deferred'
status: To Do
assignee: []
created_date: '2026-10-13 00:53'
labels: []
dependencies: []
priority: low
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem
TASK-0080's run (2026-10-12/13) delivered sub-agents from a tool and from code, with types, limits, send and stop, and watching through an event log, bh-02 watch, /agents and a status field. The owner trimmed the run on 2026-10-12 and set review findings to blocking-only, so these wait here: a tmux pane per sub-agent and darwin's tmux-socket check (TASK-0080.10), project guidance in a sub-agent (TASK-0080.07), a tool's show overriding a request's runs or agent (TASK-0080.08), and the close reviews' should-fix items (TASK-0080.11). TASK-0074 (one jail per session, which moves a child's REPL into the session's jail) is in TASK-0084.

## Open questions
- [ ] Which of these, if any, the owner wants next.

Written by the orchestrator from TASK-0080 and the owner's trim; the owner corrects it before anyone accepts it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each deferred task here is done or dropped by the owner
<!-- AC:END -->
