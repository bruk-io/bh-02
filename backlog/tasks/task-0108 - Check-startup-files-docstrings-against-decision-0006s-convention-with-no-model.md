---
id: TASK-0108
title: >-
  Check startup files' docstrings against decision-0006's convention, with no
  model
status: To Do
assignee: []
created_date: '2026-10-16 02:03'
updated_date: '2026-10-16 02:04'
labels:
  - python
  - size-3
dependencies:
  - TASK-0106
  - TASK-0107
references:
  - >-
    backlog/decisions/decision-0006 -
    Tell-the-model-of-the-functions-the-startup-files-define-by-progressive-disclosure-with-no-decorator.md
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Build decision-0006 point 7: the docstring convention checked by code, never left to the model. Waits for TASK-0106 (acceptance) and TASK-0107 (it rewrites the aside and the set of told functions this reports on). Open for the plan: the command's name and home, since plugin-layering keeps the app's CLI from importing the python plugin.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A pure, standard-library-only function over a startup file's text reports, for each told function the file defines: no docstring, no summary line, no example (a doctest block or a :: literal block), and a doctest block that does not parse or has no blank line before it; it runs none of the file's code, and tests cover each finding and a file with none
- [ ] #2 At each REPL start the aside names each function that misses and what it misses, in bh-02's words, with or without the jail, and a finding never stops a file running or hides a function
- [ ] #3 A command checks a startup file with no session and no model, exits 1 on a finding and 0 on none, and its use from a pre-commit hook and CI is documented
- [ ] #4 scripts/check passes
<!-- AC:END -->
