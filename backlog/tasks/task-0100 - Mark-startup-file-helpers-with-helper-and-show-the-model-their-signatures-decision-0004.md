---
id: TASK-0100
title: >-
  Mark startup-file helpers with @helper, and show the model their signatures
  (decision-0004)
status: To Do
assignee: []
created_date: '2026-10-14 15:57'
labels:
  - python
  - size-2
dependencies:
  - TASK-0099
references:
  - >-
    backlog/decisions/decision-0004 -
    Show-the-startup-files-helpers-to-the-model-by-signature-marked-with-helper.md
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Build decision-0004 (proposed: the owner accepts it before this starts). The owner's ordering (2026-10-14): only after the naming work, TASK-0099, which may rename the startup files and the python row's class; build against the names it leaves. In short: the Python process binds helper in the namespace; @helper marks a callable and returns it unchanged; after each startup file the startup line lists its helpers as name(signature), control characters stripped and each cut at 160 characters, then counts the other public names as hidden; help(name) gives the docstring; the python section says the convention once; told at startup only; unconfined, the model is told to run the same input. Kept out: slash commands, a directory of startup files, the REPL's environment (its own design), helpers defined after startup.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A startup file's @helper functions are listed in the first input's output as name(signature), and its other public names only counted as hidden; a test of each, seen failing before the change
- [ ] #2 A signature with control characters or over 160 characters is cleaned and cut, and one inspect.signature can't read is name(...); a test of each
- [ ] #3 help(name) shows a helper's docstring; @helper returns the function unchanged; an input that binds helper itself keeps it; a test of each
- [ ] #4 The python section, the plugin README, docs/bh-02/how-it-works/python-tool.md and GLOSSARY.md (helper) say the convention; the worker stays standard library only; scripts/check passes
<!-- AC:END -->
