---
id: TASK-0093
title: >-
  Say a bad models-file default where the person looks, and keep one rule for
  which models file is trusted
status: To Do
assignee: []
created_date: '2026-10-14 08:10'
updated_date: '2026-10-14 12:02'
labels:
  - models
  - size-3
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Filed from TASK-0087's close review (should-fix and nit, not blocking). Three gaps, one cause: the 'is the models file trusted, and what is its default' rule exists twice. (1) bh_02.sessions.create reads the file's top-level default itself (_declared_default, tomllib, host_paths.passes/roots) to record a new session's model; models_cordis_plugin reads it again in providers.known/named.parsed. Two copies of a trust rule can drift into a hole (bh-02/CLAUDE.md: what every package must compute alike is a library function, not a key). plugin-layering forbids bh_02 and models_cordis_plugin importing each other, so where the one rule lives is the open question: host_paths (stdlib, but knows nothing of models), a small shared library, or the shell asks nothing and the row records the resolved model itself. (2) _declared_default swallows a default that is not TOML or not a name and starts the session on sonnet, so AC#2's 'what to write' error from TASK-0087 never shows for a new session: the person never learns their default is ignored. (3) Round-1 should-fix 3: with a bad file default the status bar's provider is blank and /model's list has no line saying the default was refused. Open question carried: where the shared rule lives (decide before building; a design gate).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One function decides whether the models file is trusted and what its default is; sessions.create and the model row both use it, and a test fails if either stops using it
- [ ] #2 A new session started under a models file whose default is not TOML, not a name, or names no model says so with what to write, and still starts on sonnet; a test of each
- [ ] #3 With a bad file default, the status bar names the model or says it is unusable (never blank) and /model's list says the file's default was refused and why
- [ ] #4 scripts/check passes
- [ ] #5 /model NAME of a valid model still switches while an endpoint table or the file's default is broken; a test (from TASK-0095's close review)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From TASK-0095's close review (nits, carry only where this task already touches the line): docs/bh-02/using/models.md:147 and the models plugin README ~230 have lines longer than their neighbours' wrap; the unsendable-key message (openai/client.py ~107) ends 'then try again.' where the missing-key one ends 'then send the message again.'; the status bar's blank provider for a broken table is checked through current() only, not the rendered TUI (this task's AC #3 covers the status bar).
<!-- SECTION:NOTES:END -->
