---
id: TASK-0052
title: Keep one definition of the config directory and the link walk
status: To Do
assignee: []
created_date: '2026-10-07 13:47'
labels:
  - kernel
  - models
  - context
dependencies: []
references:
  - 'https://github.com/bruk-io/bh-02/pull/8'
priority: low
type: enhancement
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The kernel (client.py _walked, _MOST_LINKS) and the models plugin (named.py) carry word-for-word copies of the walk that checks every link on a path, and the person's config directory ($XDG_CONFIG_HOME else ~/.config) is worked out separately in the kernel, context, models and bootstrap code; the kernel's _located uses Path.home() while the context plugin uses its row's configured home. Plugins can't import each other, so the copies can drift. Found in the code review of PR #8.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One walk, in a library every plugin may import or carried on a value (layers already computes config_directories), used by the kernel, models and context plugins
- [ ] #2 The config directory is worked out in one place and handed to the rows that read it
- [ ] #3 The plugins' tests still pass unchanged in what they assert
<!-- AC:END -->
