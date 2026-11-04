---
id: DRAFT-0028
title: >-
  The real-clock Working-line test fails about one cold run in three: the line
  is drawn before 0.4 s
status: Draft
assignee: []
created_date: '2026-11-04T18:32:00Z'
labels:
  - size-1
  - tui
  - bug
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
test_tui_working.py::test_at_the_real_clock_and_interval_it_appears_after_a_second_and_counts asserts the Working line is still absent 0.4 s after ReplyStarted (line 319). Run alone on a quiet machine (load 1.9) it failed 1 of 3 runs, and it failed once inside scripts/check on 2026-11-04. Either the line appears before the first second on a cold start (a real defect: the widget's first tick is not a second after the reply began) or the test's 0.4 s pause outlasts its budget. Repro: run that test id five times in a row with uv run pytest -q; at least one fails.
<!-- SECTION:DESCRIPTION:END -->
