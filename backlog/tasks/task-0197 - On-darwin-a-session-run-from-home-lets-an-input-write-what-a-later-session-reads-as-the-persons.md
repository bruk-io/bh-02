---
id: TASK-0197
title: >-
  On darwin a session run from home lets an input write what a later session
  reads as the person's
status: To Do
assignee: []
created_date: '2026-11-07 04:27'
labels:
  - security
  - runner
  - darwin
  - size-3
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found 2026-11-06 on macOS 27.0.1 (Python 3.15.0rc2), with and without Claude Code's sandbox: bh-02/app/tests/test_python_repl.py::test_a_session_run_from_home_can_t_choose_what_a_later_session_reads_as_the_person_s fails at line 980 - the sixth of the paths it tries is WROTE where the test expects DENIED. TASK-0169.04's worker saw it and reported it identical on the base commit; nobody filed it. Until it is diagnosed this reads as a hole in the darwin jail (a jailed input planting a file a later session trusts), not a test problem; if diagnosis shows the test is wrong on darwin, the notes say why and the test is fixed rather than skipped.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The path that is written is named and the cause found (Seatbelt profile, spec_for's denies, or the test's expectations on darwin), with the evidence in the notes
- [ ] #2 On darwin a jailed input cannot write any path the test lists; the test passes on macOS and still fails if the deny is removed (seen failing)
- [ ] #3 scripts/check passes on Linux (scripts/linux-jail-check too) and the test passes on macOS
<!-- AC:END -->
