---
id: TASK-0109
title: Type-check startup files with mypy --strict at each REPL start (decision-0006)
status: To Do
assignee: []
created_date: '2026-10-16 02:51'
labels:
  - python
  - size-3
dependencies:
  - TASK-0106
  - TASK-0108
references:
  - >-
    backlog/decisions/decision-0006 -
    Tell-the-model-of-the-functions-the-startup-files-define-by-progressive-disclosure-with-no-decorator.md
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Build decision-0006 point 7's typing half: mypy --strict, bh-02's flags and no project config, run in the jail over each startup file at REPL start; mypy becomes a dependency of the python plugin. Waits for TASK-0106 (acceptance) and TASK-0108 (it builds the REPL-start checks and their aside, which this adds a second tool to). Measured 2026-10-16: an untyped parameter and a wrong operand are caught; 5.3 s cold, 0.2 s warm on the uncompiled mypy pin; a bare annotation (tools: Any) satisfies mypy and keeps the REPL's binding; a __builtins__.pyi stub on MYPYPATH does not work. Open for the plan: where the cache lives among the jail's writable roots, and which paths mypy searches so it finds what the REPL can import.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Confined, at each REPL start, mypy --strict with no project config checks each startup file in the jail, and the aside names each told function with an error and its error codes, never mypy's messages; tests cover an untyped function, a type error, an unfound import and a clean file
- [ ] #2 A startup file that declares a name the REPL provides with a bare annotation (tools: Any) passes mypy and keeps the REPL's binding, and the python section tells the model to declare such names so
- [ ] #3 The mypy line for CI and a pre-commit hook is documented, and mypy's cold and warm cost at REPL start on the shipped mypy is measured and recorded on this task
- [ ] #4 scripts/check passes
<!-- AC:END -->
