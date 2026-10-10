---
id: TASK-0073
title: 'Let a brig jail hold more than one process: start it once, run many in it'
status: To Do
assignee: []
created_date: '2026-10-10 18:41'
labels:
  - brig
milestone: m-5
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A brig jail is one launch of one command (`Spec -> Stack -> Step -> launch -> Handle`, SPEC.md section 2) with one declared LISTEN channel, and a second launch into one jail directory is a second jail (decision-162). Docker/OCI is in brig's stated purpose (SPEC.md section 1), and a container is something you start once and exec into, so one launch per jail fits it badly. bh-02 needs a jail to hold several programs too (M6: one jail per session; a jail per program is too expensive to be the default).

The jail gets a lifetime of its own and a way to start another process in it: the running jail starts a process (argv, working directory), and each process has its own interrupt, stop and exit record, while the jail's Spec, grades and teardown stay one. A backend with no exec of its own (bubblewrap, Seatbelt) launches a supervisor of brig's, standard library only, as the jail's command and starts processes through it; a container backend would use its own exec.

Decided with the owner (2026-10-10): a jail can hold more than one process.

## Open questions
- [ ] The API: a process handle from something like `Handle.start(argv, cwd)`, or a second kind of launch into an existing Handle.
- [ ] Law 7, "control must not require cooperation": stopping one process through the supervisor needs the supervisor's cooperation, while killing the whole jail does not. Is a per-process stop allowed to be cooperative while the jail-wide kill stays not?
- [ ] Channels: one LISTEN channel carrying every process's messages, or one per process (on Linux the channel's directory is bind-mounted writable, so more sockets fit beside it; Seatbelt's rule needs checking).
- [ ] An exit record per process, given decision-162.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A jail launched once runs several processes started into it, each with its own argv, working directory, interrupt, stop and exit status
- [ ] #2 Every process in a jail is under the jail's one Spec: a probe from a second process reports the same grades as from the first
- [ ] #3 Killing the jail ends every process in it without any process's cooperation
- [ ] #4 Works on bubblewrap and Seatbelt: brig's unit tier everywhere, its integration and e2e tiers on each platform
- [ ] #5 SPEC.md describes a jail's lifetime and its processes, including how a container backend's own exec fits
- [ ] #6 `uv run pytest libs/brig -q` and `scripts/arch-check` pass
<!-- AC:END -->
