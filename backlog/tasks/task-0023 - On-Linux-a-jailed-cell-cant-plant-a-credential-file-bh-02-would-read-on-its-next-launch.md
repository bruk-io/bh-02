---
id: task-0023
title: >-
  On Linux a jailed cell can't plant a credential file bh-02 would read on its
  next launch
status: To Do
assignee: []
created_date: '2026-09-30 01:36'
labels: []
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0019/0022. The model row reads the first local.env above bh-02's installed package or its environment (credential_files in bh_02/bootstrap.py), so when bh-02 is installed inside the project (bh-02's own repo, or a project's own venv), <project>/local.env is a credential location. On Linux the jail masks that file only if it exists when the kernel starts. If it doesn't, a cell can create it, and the next bh-02 launch would hand its token to Claude Code, sending the person's conversations to someone else's account. The same gap lets a credential file created after the kernel started be read until the kernel restarts. darwin already refuses both (seatbelt denies an absent path).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 On Linux a jailed cell cannot create a secret path that lies under a writable root and doesn't exist yet (e.g. <project>/local.env); a real-bwrap test in scripts/linux-jail-check shows the attempt denied and nothing left on the host afterwards
- [ ] #2 A credential file the person creates on the host while a session runs is not readable from the jail, or the person is told plainly why their file can't be created until the session ends
- [ ] #3 The fs_read grade and brig-cordis-plugin's README describe what the Linux jail now guarantees for absent secrets
- [ ] #4 darwin behaviour is unchanged; scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->
