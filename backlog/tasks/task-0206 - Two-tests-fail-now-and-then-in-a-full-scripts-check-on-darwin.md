---
id: TASK-0206
title: Two tests fail now and then in a full scripts/check on darwin
status: To Do
assignee: []
created_date: '2026-11-07 04:50'
updated_date: '2026-11-07 06:46'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner stand-in (Opus), 2026-11-07: TASK-0198's review hit the brig half of this again (2 of 3 standalone runs of test_channel_planted_link.py on darwin), and TASK-0198 was let close with this bug carrying it. Two failure modes are now on record. (a) 'DID NOT RAISE EndpointRefused': wait_ready accepted a listener that had left. That is the unsafe direction for the dial's peer check (brig/run/dial.py, darwin LOCAL_PEERPID), so treat it as a possible jail-guarantee bug, not as load noise, until it is explained. (b) A refusal with the wrong reason: '[Errno 57] Socket is not connected' from LOCAL_PEERPID instead of 'has left'. That is safe, but the test does not pin it. TASK-0079.31 relies on this dial. DRAFT-0021 reports the same failure and should be folded into this task, not promoted on its own.
<!-- SECTION:NOTES:END -->
