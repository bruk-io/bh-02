---
id: TASK-0155
title: >-
  Fold a resumed run's boot on the trajectory: mark each run's start in
  rows.jsonl
status: To Do
assignee: []
created_date: '2026-10-18 14:31'
labels:
  - app
  - size-2
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-0144. bh-02 trajectory tells a row's first load by its row id not being in rows.jsonl before. A session resumed with --resume goes on in the same rows.jsonl (the appender appends), so the resumed run's whole boot (about 34 rows, and a sub-agent's again) reads as reloads of rows seen before and prints a line each, burying what matters, as the boot did before TASK-0144. cordis has no event for a run's start, and the file cannot tell a mass dependency replacement (a /model switch) from a boot, so the shell would have to write a marker line when it opens the log (for example kind run at the time), which the trajectory reads: the rows after it that are already seen are that run's loads, folded the same way. Changes what rows.jsonl is written as, so a decision-0009 amendment, the GLOSSARY entries and the command-line docs follow.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A resumed session's boot is one line on bh-02 trajectory, apart from a reload of a running session's row (a restart, a dependency replaced)
- [ ] #2 A rows.jsonl written before the marker (no marker) reads as it does now (tests)
- [ ] #3 GLOSSARY.md and the docs page for bh-02 trajectory say what the marker and the line mean; scripts/check passes
<!-- AC:END -->
