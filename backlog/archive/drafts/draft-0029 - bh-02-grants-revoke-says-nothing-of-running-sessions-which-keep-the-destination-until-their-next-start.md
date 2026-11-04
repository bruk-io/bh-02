---
id: DRAFT-0029
title: >-
  bh-02 grants revoke says nothing of running sessions, which keep the
  destination until their next start
status: Draft
assignee: []
created_date: '2026-11-04T21:19:00Z'
labels:
  - runner
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0181.07 (commit 0b0d157). A running jail follows only its own session's Broker.on_change, so a revoke from another process (`bh-02 grants revoke ID`, bh_02/cli.py grants_revoke_command) changes the store but no running jail: its proxy keeps the destination until the program's next start. The runner README (The grants broker) says so, but the person is not told: the CLI prints only 'revoked: ...', and docs/bh-02/using/jail.md says flatly 'a revoke is refused from the next connection on'. A person who revokes from a second terminal, to cut a destination off a running session, believes it is cut when it is not. Either make the words true (the CLI's output and jail.md say a running session keeps it until its next start, `/grants revoke` there or `/clear`), or make it true (the broker notices the store changing and fires on_change).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 bh-02 grants revoke of a net grant says that a session running now keeps the destination until its program's next start, and how to take it off one now
- [ ] #2 docs/bh-02/using/jail.md says which revoke reaches a running program and which waits for its next start
<!-- AC:END -->
