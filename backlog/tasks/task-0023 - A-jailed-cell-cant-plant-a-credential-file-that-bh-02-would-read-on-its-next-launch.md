---
id: task-0023
title: >-
  A jailed cell can't plant a credential file that bh-02 would read on its next
  launch
status: To Do
assignee: []
created_date: '2026-09-30 01:36'
updated_date: '2026-09-30 01:40'
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
- [ ] #1 Every path the model row searches for its credential is among the jail's secrets, on every platform; a test computes both from the real anchors and fails when they differ
- [ ] #2 A jailed cell can't create or replace a local.env at any searched path under a writable root, on darwin (real seatbelt test) and Linux (real bwrap test in scripts/linux-jail-check); nothing is left on the host afterwards
- [ ] #3 The credential lookup accepts only a regular file, so a jail's placeholder at a nearer searched path never shadows the real credential, including when the model row rereads it after /model or /clear; a test covers it
- [ ] #4 On Linux, a credential file the person creates or replaces on the host while a session runs (including by atomic rename, as editors save) is not readable from the jail; where bwrap can't guarantee that, the fs_read grade and the plugin README say so and the person is told at session start which paths the jail holds

- [ ] #5 scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->
