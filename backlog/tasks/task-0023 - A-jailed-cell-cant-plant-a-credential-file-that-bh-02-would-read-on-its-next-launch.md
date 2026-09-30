---
id: task-0023
title: >-
  A jailed cell can't plant a credential file that bh-02 would read on its next
  launch
status: Done
assignee: []
created_date: '2026-09-30 01:36'
updated_date: '2026-09-30 03:35'
labels: []
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0019/0022, widened on 2026-09-29. The model row reads the first local.env that is a file above its own package or bh-02's environment (models_cordis_plugin/local_env.py: candidates/token_file). The jail's secrets come from a different anchor set (bh_02/cli.py: cwd, bh_02's package, sys.prefix via credential_files). In this workspace four directories the model row searches before the root's local.env are missing from secrets: bh-02/plugins/local.env, bh-02/plugins/models-cordis-plugin/local.env, and the two below it. The first two are writable by a jailed cell on darwin and Linux alike. So a cell can plant a local.env there, and the next launch hands its token to Claude Code, which sends the person's conversations to someone else's account. On Linux, a secret path that doesn't exist yet is not masked either, so a cell can create one anywhere under the project, and a credential file created after the kernel started stays readable until the kernel restarts.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every path the model row searches for its credential is among the jail's secrets, on every platform; a test computes both from the real anchors and fails when they differ
- [x] #2 A jailed cell can't create or replace a local.env at any searched path under a writable root, on darwin (real seatbelt test) and Linux (real bwrap test in scripts/linux-jail-check); nothing is left on the host afterwards
- [x] #3 The credential lookup accepts only a regular file, so a jail's placeholder at a nearer searched path never shadows the real credential, including when the model row rereads it after /model or /clear; a test covers it
- [x] #4 On Linux, a credential file the person creates or replaces on the host while a session runs (including by atomic rename, as editors save) is not readable from the jail; where bwrap can't guarantee that, the fs_read grade and the plugin README say so and the person is told at session start which paths the jail holds

- [x] #5 scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Commit 881494b (+ f5b2eb4). One credential search: bh_02.cli.credential_search() (above bh_02's install and sys.prefix, nearest first) is the new layers.credentials. models:model and models:catalog depend on layers and search only that list (claude-code start, the openai per-request key read, /model's key check), so the models plugin no longer anchors on its own package and the four plugins/... paths aren't searched at all. unreadable(credentials, beside, states) builds secrets containing every credential path by construction. test_credential_search computes both from the real anchors (red first: it found the four paths). Linux: an absent searched path under a writable root keeps its write deny, so it's held by a read-only placeholder and a cell can't create it. A deny nested in another is left to the outer one, because bwrap can't mount on it. test_a_jailed_cell_cannot_plant_a_credential_where_the_model_row_looks (real jail; red on Linux). The lookup accepts regular files only; tests cover a placeholder at a nearer path for the claude-code reread and the openai key read (not red first: is_file already held; shown to catch a regression by switching to exists). Measured and not closable: a host rename over a masked file, or removing a placeholder, detaches the mount inside the jail. So on Linux fs_read is graded best_effort whenever a secret under a writable root is held, the jail's notice() names those paths, tui:status shows it when a kernel comes up, and the README and CONTRACTS say so. test_a_linux_jail_s_hold_on_a_secret_ends_when_the_host_replaces_or_removes_it pins the gap. On Linux the person can't create the root local.env mid-session (the notice says to stop bh-02 first). Verified after merging into leftovers: scripts/check 1809 passed / 19 skipped, all green; scripts/linux-jail-check 83 passed; pytest -m e2e 16 passed (both live Claude Code tests incl.); a real bh-02 launch in a pty with the default jail answered after a cold start, /model sonnet, /model haiku and /clear (2.0-2.8 s).
<!-- SECTION:NOTES:END -->
