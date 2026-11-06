---
id: TASK-0176
title: Move bh-02 off its in-repo brig onto bruk-io/brig
status: To Do
assignee:
  - '@bruk'
created_date: '2026-10-31T03:54:00Z'
updated_date: '2026-11-06T15:51:00Z'
labels:
  - brig
  - size-8
  - finish-moved
dependencies: []
references:
  - >-
    backlog/decisions/decision-0011 -
    Swap-to-bruk-io-brig-in-one-change-once-it-jails-what-runner-confined-runs-on-both-platforms.md
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem

bh-02 still jails the model's code with its own copy of brig (`libs/brig`, the old brig). brig has been rewritten, in a repository of its own (bruk-io/brig), and the owner wants bh-02 migrated onto that one and the in-repo copy gone ("migrate us off of the in repo brig library to the new brig library we created in bruk-io/brig"). The new brig's own root task says the move is the embedder's to make "once brig can jail what it runs".

## Affected users and systems

- **The person using bh-02**, on darwin and Linux: `runner:confined` is what keeps the model's code from writing outside the project, reading secrets, reaching the network or rewriting bh-02 itself.
- **The runner plugin** (`runner_cordis_plugin.jail`, the only package that imports brig, by `brig-one-adapter`), and the status bar's jail grades (`tui:grades`, four axes from brig's report).
- **The workspace**: `libs/brig` (its source, tests, gate in `scripts/arch-check`, the root pytest `pythonpath`), `docs/brig/`, the CLAUDE.md files, `scripts/linux-jail-check`.
- **bruk-io/brig**: anything bh-02 needs that the new brig lacks is that repository's work, on its own board.

## Open questions

- [x] Can the new brig jail what `runner:confined` runs today? Answered by TASK-0176.01's spike (2026-10-31): on Linux, mostly yes; four gaps on brig's side, one of them a security hole, and no darwin driver at all.
- [ ] Carried forward: answered only at the commit the swap pins (TASK-0176.04 re-checks it). When bruk-io/brig closes those gaps, does its API stay the shape the spike used (ordered `Bind`s, `reserve_channels`, `await_channel_ready`, `destroy_jail`)? The swap's plan is written against that commit and is re-checked against the one it pins.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 bh-02's runner jails through brig from bruk-io/brig, a git dependency pinned to one commit, and nothing in the workspace imports, tests, gates or documents the old brig: libs/brig, docs/brig and every line naming them are gone
- [x] #2 Must not break: interrupting a running input reaches the program in the jail (SIGINT), as today
- [x] #3 Must not break: no jail can reach another jail's channel, another session's included, with a test that plants the attempt
- [x] #4 What bh-02 alone knows (the self-modification list, the credential paths) lives in the runner plugin, not in brig
- [x] #5 scripts/check and scripts/linux-jail-check pass
- [x] #6 Must not break: runner:confined confines on Linux, and on darwin refuses to start and names runner:unconfined until TASK-0176.05 lands Seatbelt; each of the status bar's four axes (fs_write, network, fs_read, env) is graded by brig, with no axis stronger than what a test shows
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-10-31 by Claude under the owner's delegation ("can you handle all the implementation and planning without my input"), as size-8: two repositories, brig-side work with unknowns that need a Mac to settle, and a security property to hold. No spec: the owner is away, so there is no one to approve one. The split below and decision-0011 carry the design, for the owner to confirm or redirect on return.

decision-0011 accepted by @bruk, 2026-10-31; Seatbelt waits for a Mac run (TASK-0176.05). The owner granted this session push access to bruk-io/brig to file .02, .03 and .04 on its board.

Architecture review, 2026-11-02 (three reviewers: brig's internals, the bh-02/brig seam, brig's security). Where it challenges decision-0011: (1) spec_for producing the new brig's ordered Binds bakes bwrap into bh-02's policy and forces a second rewrite when darwin lands; better, spec_for returns bh-02's own intent type and brig compiles an intent policy per jail type (brig DRAFT-0013); (2) the swap is not the adapter alone: the runner's endpoint contract changes (draft above); (3) the new brig lacks more than the four gaps listed: cwd and stdio (brig DRAFT-0016), cleanup of mountpoints for absent paths (DRAFT-0015, measured), a refusal for an unreachable interpreter (DRAFT-0017), and a runtime report (noted on brig TASK-0021). (4) Critical, measured: the jailed command can forge the supervisor's events and ptrace it (brig TASK-0022); the swap waits on it too. decision-0011 stays as accepted until the owner revisits it.

Owner, 2026-11-04 (relayed by the lead): land the swap without darwin confinement; decision-0011 amended the same day. Criterion 'runner:confined confines on darwin and on Linux' replaced: darwin refuses and names runner:unconfined until TASK-0176.05. Seatbelt (TASK-0176.05) stays under this intent and keeps it open.

Owner, 2026-11-04: approval keeps counting fs_write best_effort as confined (runner:approval's _CONFINING). best_effort means the jail itself cannot undo a protected path, but a host process replacing one mid-session (git's config.lock rename over .git/config, say) leaves the jail's read-only mount on the old inode; the tripwire ends the jail when it sees that. The tripwire's gap over brig's rename pins is to be closed next (DRAFT-0022's first item).

2026-11-06: the darwin Seatbelt jail (TASK-0176.05) is moved out of this intent into TASK-0196, standalone and on hold by the owner's decision to hold off on the Mac. Criterion #6 needs only that runner:confined refuse on darwin and name runner:unconfined until Seatbelt lands; where it says TASK-0176.05, read TASK-0196.

Check `scripts/check` exited 0

(13 earlier lines omitted)
```text

........................................................................ [  2%]
........................................................................ [  5%]
.............s.......................................................... [  7%]
..............................x......................................... [ 10%]
........................................................................ [ 12%]
........................................................................ [ 15%]
........................................................................ [ 18%]
..................s..................................................... [ 20%]
........................................................................ [ 23%]
........................................................................ [ 25%]
........................................................................ [ 28%]
........................................................................ [ 30%]
........................................................................ [ 33%]
.....................................ss................................. [ 36%]
........................................................................ [ 38%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 46%]
........................................................................ [ 48%]
........................................................................ [ 51%]
........................................................................ [ 54%]
........................................................................ [ 56%]
........................................................................ [ 59%]
........................................................................ [ 61%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 69%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 87%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 95%]
........................................................................ [ 97%]
...............................................................          [100%]
2794 passed, 6 skipped, 1 xfailed in 125.78s (0:02:05)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/bh-02/site
INFO    -  Documentation built in 2.02 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
