---
id: TASK-0052
title: Keep one definition of the config directory and the link walk
status: Done
assignee: []
created_date: '2026-10-07 13:47'
updated_date: '2026-10-09 03:05'
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
Ported from 48c2fdc in dc107a8, and widened: not cordis_helpers but a library of its own, libs/host-paths (package host_paths, standard library only), since cordis_helpers is patterns on cordis and libs are not units of the root gate. It holds walked, MOST_LINKS, roots, passes (the places on a path's way under any root), config_home and state_home. The kernel, models and memory plugins call the walk; the kernel, models, the app (bootstrap and sessions) and brig's records_dir call the XDG lookups. AC #2 is met as one function every row calls, not a value handed to them: a key would add reloads of the kernel and system (48c2fdc's reasoning). Behaviour changes: a relative XDG_CONFIG_HOME or XDG_STATE_HOME counts as unset (the XDG spec); memory walks a file outside the project as named, so a `..` after a link goes where opening it goes. host_paths is one of bh-02's own packages in layers.code.
<!-- SECTION:FINAL_SUMMARY:END -->
