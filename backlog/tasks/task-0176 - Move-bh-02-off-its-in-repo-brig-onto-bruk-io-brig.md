---
id: TASK-0176
title: Move bh-02 off its in-repo brig onto bruk-io/brig
status: To Do
assignee:
  - '@bruk'
created_date: '2026-10-31T03:54:00Z'
updated_date: '2026-10-31T10:59:00Z'
labels:
  - brig
  - size-8
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
- [ ] #1 bh-02's runner jails through brig from bruk-io/brig, a git dependency pinned to one commit, and nothing in the workspace imports, tests, gates or documents the old brig: libs/brig, docs/brig and every line naming them are gone
- [ ] #2 Must not break: runner:confined confines on darwin and on Linux, and each of the status bar's four axes (fs_write, network, fs_read, env) is graded by brig, with no axis stronger than what a test shows
- [ ] #3 Must not break: interrupting a running input reaches the program in the jail (SIGINT), as today
- [ ] #4 Must not break: no jail can reach another jail's channel, another session's included, with a test that plants the attempt
- [ ] #5 What bh-02 alone knows (the self-modification list, the credential paths) lives in the runner plugin, not in brig
- [ ] #6 scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-10-31 by Claude under the owner's delegation ("can you handle all the implementation and planning without my input"), as size-8: two repositories, brig-side work with unknowns that need a Mac to settle, and a security property to hold. No spec: the owner is away, so there is no one to approve one. The split below and decision-0011 carry the design, for the owner to confirm or redirect on return.

decision-0011 accepted by @bruk, 2026-10-31; Seatbelt waits for a Mac run (TASK-0176.05). The owner granted this session push access to bruk-io/brig to file .02, .03 and .04 on its board.
<!-- SECTION:NOTES:END -->
