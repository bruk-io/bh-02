---
id: TASK-0053
title: >-
  Keep a jailed input from editing bh-02's own files when bh-02 works on its own
  checkout
status: Done
assignee: []
created_date: '2026-10-07 14:18'
updated_date: '2026-10-09 03:05'
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
- [x] #1 When bh-02's own shipped context file, or the package directories it can import from, lie under a root the jail lets inputs write, the jail write-denies them as it does layer files
- [ ] #2 Or the context plugin treats the shipped file as the project's when its way passes through the project, without losing the person's own guidance sections
- [x] #3 A test shows a jailed input can't make bh-02 import a module it wrote
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Ported from 51d976f in a4d0ffd. layers.code is the directory of every package bh-02 runs (bh_02, cordis, cordis_helpers, brig, host_paths and each installed plugin's), found by name with find_spec (nothing imported), each as named and as resolved. brig:jail write-denies those under a root an input may write, as it does layer files. AC #2 was the alternative, not taken, and is moot: the context plugin was removed before the port, and memory reads only the project's and the person's files. The test shows a jailed input can't write memory_cordis_plugin's memory.py when the project is bh-02's checkout.
<!-- SECTION:FINAL_SUMMARY:END -->
