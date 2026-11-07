---
id: TASK-0210
title: >-
  brig: on darwin a workload that answers and closes at once can fail wait_ready
  (decision-209)
status: To Do
assignee: []
created_date: '2026-11-07 21:52'
labels:
  - brig
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-209 (TASK-0206) measured darwin's LOCAL_PEERPID: once the serving end has closed a connection the read fails with ENOTCONN, and the dial refuses (decision-186), so Process.wait_ready on darwin can raise EndpointRefused for a genuine workload that writes a greeting and closes before the host reads its peer. Linux keeps SO_PEERCRED after the close. Decide whether the readiness dial should treat that case otherwise (a SPEC ruling, owner's call), or document it for embedders. Also: libs/brig/tests/integration/test_channel_reservation_starts.py's _SERVE closes each connection at once, the same latent race TASK-0206 removed from test_channel_planted_link.py.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The darwin behaviour for a server that closes first is ruled in SPEC.md and implemented or documented
- [ ] #2 test_channel_reservation_starts.py's serving workload no longer races the host's peer read on darwin
<!-- AC:END -->
