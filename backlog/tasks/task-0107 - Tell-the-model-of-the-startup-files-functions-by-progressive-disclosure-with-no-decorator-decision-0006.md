---
id: TASK-0107
title: >-
  Tell the model of the startup files' functions by progressive disclosure, with
  no decorator (decision-0006)
status: To Do
assignee: []
created_date: '2026-10-16 02:03'
updated_date: '2026-10-16 02:57'
labels:
  - python
  - size-3
  - finish-moved
dependencies:
  - TASK-0106
references:
  - >-
    backlog/decisions/decision-0006 -
    Tell-the-model-of-the-functions-the-startup-files-define-by-progressive-disclosure-with-no-decorator.md
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Build decision-0006 points 1-6 (accepted 2026-10-16). In short: a startup file's public functions (defined in it; exactly __all__'s callables when it has one) are listed by signature in the aside before the first input's output at each REPL start, up to 600 characters across the REPL's startup files in the order they run, the rest by name; help(name) and inspect.getsource are the pulled levels; the python section says the convention, what it costs in context and the docstring convention; @helper, the helper name, __bh_helper__ and the word helper in its startup-function sense go. Supersedes TASK-0100's marking; keeps its data line, cleaning, 160-character cut and identifier rule.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The python section of the system prompt states which functions are told, what they cost (listed every REPL; a leading underscore keeps one untold; a docstring and source cost nothing until asked for) and the docstring convention, and each sentence holds with and without the jail
- [ ] #2 @helper, the helper name, __bh_helper__ and the word helper are gone from the code, the model-facing text, GLOSSARY.md and the docs, and a startup file that still says @helper fails at start with a NameError on the startup line
- [ ] #3 scripts/check passes
- [ ] #4 At each REPL start the aside lists every told function of the REPL's startup files by signature up to 600 characters across them, in the order they run, and the rest by name, and tests cover __all__ (an imported name included), a private name, a name only imported, and files past the budget
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-16: finish moved before any work: the owner set the signature budget to 600 characters (was 1,500, too long) on accepting decision-0006, and the budget spans the REPL's startup files. The word 'helper' goes in its startup-function sense only: brig's jail helpers and credential helpers keep theirs.
<!-- SECTION:NOTES:END -->
