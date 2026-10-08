---
id: TASK-0052
title: Keep one definition of the config directory and the link walk
status: Done
assignee: []
created_date: '2026-10-07 13:47'
updated_date: '2026-10-08 01:16'
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
- [x] #1 One walk, in a library every plugin may import or carried on a value (layers already computes config_directories), used by the kernel, models and context plugins
- [x] #2 The config directory is worked out in one place and handed to the rows that read it
- [x] #3 The plugins' tests still pass unchanged in what they assert
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
cordis_helpers.paths holds config_home (XDG_CONFIG_HOME, else ~/.config) and walked (every directory and link on a path, links followed, at most MOST_LINKS), replacing the copies in the kernel, models and context plugins and the app's config_directories. Each caller passes the environment and home it used before, so behaviour is unchanged. Not a key on layers: system and the kernel would then reload on /restart layers, which they don't today.
<!-- SECTION:FINAL_SUMMARY:END -->
