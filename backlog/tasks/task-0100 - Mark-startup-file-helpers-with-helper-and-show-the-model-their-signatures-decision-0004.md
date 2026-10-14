---
id: TASK-0100
title: >-
  Mark startup-file helpers with @helper, and show the model their signatures
  (decision-0004)
status: To Do
assignee: []
created_date: '2026-10-14 15:57'
updated_date: '2026-10-14 16:29'
labels:
  - python
  - size-2
dependencies:
  - TASK-0099.02
references:
  - >-
    backlog/decisions/decision-0004 -
    Show-the-startup-files-helpers-to-the-model-by-signature-marked-with-helper.md
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Build decision-0004 (accepted 2026-10-14 by Fable for the owner, with two changes). It waits for TASK-0099.02 only, which renames the startup files (startup.py) and the python row's class (PythonProcess) that this task edits; TASK-0099.03 does not touch these files. In short: the Python process binds helper in the namespace; @helper marks a callable and returns it unchanged; after each startup file the startup line lists its helpers as name(signature), control characters stripped and each cut at 160 characters, then counts the other public names as hidden; help(name) gives the docstring; the python section says the convention once; told at startup only. Unconfined (--no-jail) stays as today: nothing listed. After /compact the signatures live only in the model's summary: an accepted limit. Kept out: slash commands, a directory of startup files, the REPL's environment, helpers defined after startup.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A startup file's @helper functions are listed in the first input's output as name(signature), and its other public names only counted as hidden; a test of each, seen failing before the change
- [ ] #2 A signature with control characters or over 160 characters is cleaned and cut, and one inspect.signature can't read is name(...); a test of each
- [ ] #3 help(name) shows a helper's docstring, and @helper returns the function unchanged; a test of each
- [ ] #4 The python section, the plugin README, docs/bh-02/how-it-works/python-tool.md and GLOSSARY.md (helper) say the convention; the worker stays standard library only; scripts/check passes
<!-- AC:END -->
