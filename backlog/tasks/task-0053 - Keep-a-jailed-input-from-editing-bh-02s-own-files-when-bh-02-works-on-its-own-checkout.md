---
id: TASK-0053
title: >-
  Keep a jailed input from editing bh-02's own files when bh-02 works on its own
  checkout
status: To Do
assignee: []
created_date: '2026-10-07 14:18'
labels:
  - context
  - brig
  - security
dependencies: []
references:
  - 'https://github.com/bruk-io/bh-02/pull/8'
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
When bh-02 runs in its own source checkout (an editable install, working on bh-02 itself), the shipped context file (context_cordis_plugin/context.toml) is inside the project, so a jailed input can write it. It is trusted whole and re-read before every message: an input could name a module it wrote on the editable install's path, and that module would be imported and run in bh-02's own process at the next prompt reading, outside the jail. Edits to bh-02's other source files already become code the person runs at the next launch; this one takes effect at once. Found while fixing PR #8's code review.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 When bh-02's own shipped context file, or the package directories it can import from, lie under a root the jail lets inputs write, the jail write-denies them as it does layer files
- [ ] #2 Or the context plugin treats the shipped file as the project's when its way passes through the project, without losing the person's own guidance sections
- [ ] #3 A test shows a jailed input can't make bh-02 import a module it wrote
<!-- AC:END -->
