---
id: TASK-0130
title: >-
  Stop a process and everything it started when the jail can't give it
  namespaces: a subreaper per process
status: To Do
assignee: []
created_date: '2026-10-17 02:23'
labels:
  - brig
  - size-3
dependencies: []
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner's call, 2026-10-17: a jail run as uid 0 (containers, CI, cloud sessions) gets no per-process namespaces (decision-194, decision-195) and the supervisor will not hold CAP_SYS_ADMIN to make them (decision-197). In that fallback a process's stop is its process group (decision-191), so a child that left the group (setsid, nohup, a daemonised dev server, subprocess.Popen(start_new_session=True), a double fork) outlives the stop and runs on in the jail until destroy. With one jail per session (TASK-0074), restarting a stuck Python process would leave its servers running.

Proposed, not measured: the supervisor starts each process under a parent of its own marked PR_SET_CHILD_SUBREAPER, so every descendant that loses its parent is re-parented to that subreaper rather than to the jail's PID 1, and a stop kills the subreaper's whole tree (read from /proc/<pid>/task/*/children), repeating until none is left, then the subreaper. No capability is needed. It is not airtight against a tree that forks as fast as the loop kills, so the process scope stays graded below enforced, with the reason named.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 In a jail without per-process namespaces (as root, or with the block planted), stop ends a process's setsid() child, a double-forked daemon and a nohup child; a test plants each, seen surviving before the change
- [ ] #2 A sibling process and its children are untouched by that stop (a control)
- [ ] #3 The process scope's grade and reason say what the fallback holds and what it does not (a tree forking faster than the stop), with a dated SPEC.md ruling
- [ ] #4 brig's tiers pass as root and as tester
<!-- AC:END -->
