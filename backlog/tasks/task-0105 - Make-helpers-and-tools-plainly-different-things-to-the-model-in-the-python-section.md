---
id: TASK-0105
title: >-
  Make helpers and tools plainly different things to the model in the python
  section
status: To Do
assignee: []
created_date: '2026-10-15 21:00'
labels:
  - python
  - size-1
dependencies: []
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Asked by the owner (2026-10-15): keep tools and helpers separate, but make it obvious to the model that they are different things. Today the python section says "helper" for any function the model defines (one word, two things: decision-0005's rule) and tells of `tools.NAME` in a bullet of its own as "functions here too", never saying where each runs. A helper (a startup file's `@helper` function) is plain Python in the REPL, in the jail, able to do nothing an input can't; a tool is bh-02's, runs outside the jail, and is asked about as the model's own call to it would be.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The python section uses "helper" only for a startup file's @helper function, and says in one place that the model's own functions, helpers and tools are three different things: where each runs (the REPL in the jail, or bh-02 outside it), whether a call is asked about, and how long each lasts
- [ ] #2 GLOSSARY.md's helper and tools (in an input) lines say the same; the python tool's doc page says it where it explains helpers and tools
- [ ] #3 The python plugin's tests pass with the new wording, and scripts/check passes
<!-- AC:END -->
