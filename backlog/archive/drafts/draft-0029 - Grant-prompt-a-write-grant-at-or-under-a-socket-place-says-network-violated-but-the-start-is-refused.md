---
id: DRAFT-0029
title: >-
  Grant prompt: a write grant at or under a socket place says network violated,
  but the start is refused
status: Draft
assignee: []
created_date: '2026-11-04T20:05:00Z'
labels:
  - runner
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
prompting._warnings (bh-02/plugins/runner-cordis-plugin/src/runner_cordis_plugin/prompting.py) gives every read or write path that is, lies under or holds a socket place the same warning: the jail's network would be violated and approval would stop counting it as confined. For a write grant that is or lies under /tmp, /run, /var/tmp, /dev/shm or $XDG_RUNTIME_DIR that is untrue: policy.writable carries it into BrigJail._roots, and socket_refusal raises at start (decision-0012 item 9: such roots are refused), so the program does not start at all. A person who answers always gets a project grant that stops every later start until it is revoked. The Grades line also says 'no grade changes' beside a warning saying the grade becomes violated. Found reviewing TASK-0181.06.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A write grant at or under a socket place warns that the jail will not start while it is granted, and says what to do (revoke it with /grants revoke)
- [ ] #2 A read grant, or a write grant that holds a socket place, keeps the network-violated warning, and the Grades line does not say no grade changes when a warning applies
- [ ] #3 test_runner_prompting covers each case
<!-- AC:END -->
