---
id: TASK-0144
title: >-
  Show a row's first load apart from its reloads on the trajectory, and fold the
  boot
status: To Do
assignee: []
created_date: '2026-10-18 12:15'
labels:
  - app
  - size-3
dependencies: []
references:
  - >-
    backlog/decisions/decision-0009 -
    Record-a-sessions-trajectory-as-timing-on-the-transcripts-entries-and-read-it-with-bh-02-trajectory.md
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-0136.11 and its real run (2026-10-18). cordis has no first-load or restart event, so rows.jsonl records a row's first load as a reload: bh-02 trajectory opens with about 34 boot lines, and each sub-agent's start adds about 15, which bury the reloads that matter (a /model switch, a /clear). The reader can tell them apart: a row id not seen before in the session is its first load.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 bh-02 trajectory labels a row's first load in the session apart from a reload of a row seen before (a restart, a dependency replaced, a layer edit), from rows.jsonl as it is written today
- [ ] #2 The first loads at the session's start are one line (how many rows, the time from the first to the last), and a sub-agent's first loads are one line under it; reloads and failures still print one line each in time order (tests)
- [ ] #3 GLOSSARY.md and the docs page for bh-02 trajectory say what each line means; scripts/check passes
<!-- AC:END -->
