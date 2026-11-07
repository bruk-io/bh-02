---
id: TASK-0206
title: Two tests fail now and then in a full scripts/check on darwin
status: To Do
assignee: []
created_date: '2026-11-07 04:50'
labels:
  - tests
  - darwin
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Seen in TASK-0202's three scripts/check runs on a 28-core Mac at -n 8 (2026-11-06), each in one run of three: bh-02/plugins/tui-cordis-plugin/tests/test_tui_working.py::test_at_the_real_clock_and_interval_it_appears_after_a_second_and_counts ('Working · 2s' not seen within 3.0 s, line 320; also failed in an earlier -n 8 run) and libs/brig/tests/integration/test_channel_planted_link.py::test_a_listener_that_left_after_listening_is_refused (DID NOT RAISE EndpointRefused). Both look timing- or load-dependent; neither is retried away.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each failure is explained (load, a race in the code, or a test premise) and fixed, seen failing before the fix where the cause can be planted
- [ ] #2 Each passes in three scripts/check runs in a row
<!-- AC:END -->
