---
id: TASK-0046
title: Let the person keep REPL helpers in a startup file of their own
status: Done
assignee: []
created_date: '2026-10-07 03:05'
updated_date: '2026-10-07 13:18'
labels:
  - kernel
dependencies: []
priority: low
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The kernel runs one startup file, the project's `.bh-02/kernel.py`. A person who wants the same helpers (show, search, refs) in every project has to copy them into each repo.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The kernel runs a list of startup files: the person's own (outside the project) and then the project's
- [x] #2 `~` is expanded on the host side, and each file is readable inside the jail
- [x] #3 The model is told that only the project's file is its to edit
- [x] #4 Tests cover both files, a missing one, and a failing one
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The kernel runs the person's startup file ($XDG_CONFIG_HOME/bh-02/kernel.py, else ~/.config/bh-02/kernel.py), then the project's .bh-02/kernel.py. A Linux jail can't read the home directory, so the host reads the person's file and sends its source (inspect.getsource works; __file__ is not set), unless its path or a link on the way lies in a root inputs may write (jail.writes()); then the jail reads it. The jail write-denies bh-02's config directory when it lies under a writable root (layers.trusted), so no session can plant what a later one reads. A startup file that ends the worker is skipped until /restart kernel. The model is told only the project's file is its to edit. Not closed: bh-02 run inside its own config directory, and on Linux a ~/.config/bh-02 that is itself a link.
<!-- SECTION:FINAL_SUMMARY:END -->
