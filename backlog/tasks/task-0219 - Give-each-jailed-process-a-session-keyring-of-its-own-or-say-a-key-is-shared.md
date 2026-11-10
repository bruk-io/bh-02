---
id: TASK-0219
title: >-
  Close the jail's hole to the kernel's session keyring: a jailed program reads
  a host secret
status: To Do
assignee: []
created_date: '2026-11-09 01:17'
updated_date: '2026-11-10 18:26'
labels:
  - brig
  - size-1
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A confinement hole, not only a channel between programs. A jailed program can use the kernel's session keyring of the process that started the jail, since brig's bwrap has no seccomp filter (grep of libs/brig/src/brig/mech finds none) and nothing else stands in the way.

Measured by a pre-merge review of TASK-0074 in the Linux container scripts/linux-jail-check gives: the process starting the jail joined a session keyring as a login does and added a key, and a program in a namespaced jail found it and read its payload. So a secret in that keyring is readable from the jail, and no grade says so. Measured for TASK-0074: a key one jailed program adds is found by a sibling, with the same key id in one shared jail and across two jails started by one process, so it is also a way between jails. The user keyring is kept apart by the nested user namespace.

A bare Linux host should be exposed the same way, though that has only been measured in this container. Docker's default seccomp profile does not change this: that profile stops bwrap's own namespaces, which is why scripts/linux-jail-check turns it off, so a jail never runs under it.

Named as open in brig's decision-211, brig's README, the runner plugin's README and the docs' jail-and-approval page; tests/e2e/test_process_namespaces.py::test_an_open_hole_a_sibling_finds_a_key_in_the_session_keyring pins it. Likely fixes, neither tried: a fresh session keyring for the jail with keyctl(KEYCTL_JOIN_SESSION_KEYRING, NULL) in the supervisor before anything starts (and per process, for siblings), or a seccomp filter on add_key, keyctl and request_key.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A key the process that starts a jail holds in its session keyring cannot be found or read by a program in the jail, in a test with a control
- [ ] #2 A key one jailed program adds is not found by a sibling or by a program in another jail, in a test with a control
- [ ] #3 decision-211, brig's README, the runner's README and the jail-and-approval page no longer name it as open, and the test pinning the hole is gone
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-10: Now tracked as bruk-io/brig TASK-0062.
<!-- SECTION:NOTES:END -->
