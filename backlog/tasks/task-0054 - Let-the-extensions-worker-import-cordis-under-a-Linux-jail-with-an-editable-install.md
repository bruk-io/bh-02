---
id: TASK-0054
title: >-
  Let the extensions worker import cordis under a Linux jail with an editable
  install
status: To Do
assignee: []
created_date: '2026-10-07 14:43'
labels:
  - extensions
  - brig
dependencies: []
references:
  - 'https://github.com/bruk-io/bh-02/pull/8'
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Under a Linux brig:jail (reads by allowlist: the system, the interpreter, the project), the extensions worker can't import cordis when bh-02 is an editable install (uv tool install --editable ./bh-02/app, or uv run in the checkout): the venv's .pth files point at the workspace's src directories, which the jail can't read, so the worker never listens and no extension loads. The kernel's worker is stdlib-only and run by path, so it is unaffected. Found while fixing PR #8's code review.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Under a Linux jail with an editable install, an extension loads (the jail's read allowlist names the source directories the worker imports from, or the worker is given what it needs another way)
- [ ] #2 Those directories are readable only, never writable, by an input
- [ ] #3 A test boots the real extensions worker under bubblewrap with an editable install and loads an extension
<!-- AC:END -->
