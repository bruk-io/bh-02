---
id: decision-0011
title: >-
  Swap to bruk-io/brig in one change, once it jails what runner:confined runs on
  both platforms
date: '2026-10-31T03:55:00Z'
status: accepted
---
## Context

TASK-0176: move bh-02 off `libs/brig` (the old brig) onto bruk-io/brig (the new one). Both are
the distribution `brig`, import name `brig`, so one workspace cannot hold both: the swap is all
at once, not platform by platform.

TASK-0176.01's spike (2026-10-31, new brig at a7e7f45, bubblewrap 0.9.0, Python 3.15.0b4) jailed
a stand-in for bh-02's Python worker under bh-02's own Linux policy, written as the new brig's
ordered `Bind`s. What held:

- The policy shape: the system tree and the interpreter read-only, the project and a scratch
  directory writable, a write deny inside the project (a read-only bind over itself, after the
  root), a secret file masked by binding `/dev/null` over it (reads fail with `PermissionError`,
  not an empty file as today), a secret directory masked by an empty one.
- No network (`--unshare-all`); the environment scrubbed to an allowlist with `TMPDIR` passed.
- The program's channel: `reserve_channels`, the endpoint in argv, `await_channel_ready`'s
  verified connect (the worker must survive a dial-and-leave, as it does for bh-02's own
  `_until_listening` today).
- Teardown: `destroy_jail` ended a program left running; a SIGKILLed embedder's jail died with
  it (`--die-with-parent`, today's tether).
- uv's `cpython-3.15-<platform>` link must be mounted for the supervisor to start, since brig
  runs its supervisor under the embedder's `sys.executable`. That is bh-02's to mount
  (`_links_on_the_way` already finds it).

What did not, all on brig's side:

1. **Cross-jail reach (security).** A jail with no grant under `~/.brig` dialled another jail's
   channel and got its answer: brig binds its whole state directory into every jail, every other
   jail's channel directory with it. For bh-02, a session's jail could drive another session's
   Python worker, with that project's write access.
2. **No interrupt.** Nothing public signals the jailed command; the supervisor forwards SIGTERM
   only. SIGINT to the supervisor's group did not reach the program.
3. **No grades bh-02 shows.** brig grades `channel_exclusivity` only; the status bar's four axes
   (`fs_write`, `network`, `fs_read`, `env`) have nothing to read.
4. **No darwin.** bwrap is the only driver; Seatbelt is planned, and the new brig's own open
   question (build it before a Mac run proves it, or wait) is the owner's.

## Decision

- **The swap waits for all four.** Moving now would leave darwin unconfined, an input
  uninterruptible, the status bar blank and jails reachable from each other. The new brig's root
  task says the same: an embedder moves "once brig can jail what it runs". Each gap is a task
  under TASK-0176 that names what bh-02 needs and is closed from bruk-io/brig's commit that
  delivers it; the gaps are built on that repository's board, not here.
- **One change swaps it**, TASK-0176.07: `runner_cordis_plugin.jail` moves to the new API and
  the root `pyproject.toml` depends on `brig @ git+https://github.com/bruk-io/brig@<commit>`,
  pinned to one commit, bumped deliberately (as pypeeker is). A second change removes the old
  brig (TASK-0176.08), so the swap's diff is the adapter alone.
- **bh-02 owns its policy.** `spec_for` stays bh-02's one pure function; it produces the new
  brig's ordered `Bind`s and `EnvPolicy`. What only bh-02 knows (the self-modification list, the
  credential paths) moves into the runner plugin first (TASK-0176.06), since the new brig has no
  such lists and should not.
- **What can land before the swap lands now**, against the old brig, when it is needed either
  way and changes no behaviour (TASK-0176.06). Nothing is written against the new API before it
  can be run end to end.

## Consequences

- bh-02 keeps the old brig until bruk-io/brig closes the four gaps; how long is that board's.
- The swap's plan is re-checked against the pinned commit: the API the spike used may change.
- A masked secret reads as a permission error, not an empty file. Nothing of bh-02's reads one.
- `supervisor_interpreter`'s choice of `/usr/bin/python3` goes: the new supervisor runs under
  bh-02's own interpreter and refuses one older than 3.15 (decision-0007 already asks for 3.15).
