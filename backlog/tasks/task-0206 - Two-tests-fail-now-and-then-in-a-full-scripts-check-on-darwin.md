---
id: TASK-0206
title: Two tests fail now and then in a full scripts/check on darwin
status: To Do
assignee: []
created_date: '2026-11-07 04:50'
updated_date: '2026-11-07 19:23'
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

Owner stand-in (Opus), 2026-11-06: TASK-0198 will not fix this test; it is this task's alone. A lead from TASK-0198's worker, not yet confirmed: in libs/brig/src/brig/run/dial.py (around lines 153-178), the darwin branch of _read_peer reads LOCAL_PEERPID and sets left=False unconditionally. The Linux branch checks pidfd liveness before and after it reads the group. That asymmetry is the likely cause of mode (a), 'DID NOT RAISE'. Fixing it changes the peer check, so it needs a SPEC.md decision first. Mode (b) should be pinned by the same fix: the test should state which refusal reason darwin gives.

Folded in from two drafts (archived), 2026-11-07. (1) 'brig's planted-link refusal test fails on darwin under the full parallel check': TASK-0079.34's review ran scripts/check (full tier, xdist) on macOS 27.0.1 on 2026-11-07 and test_a_listener_that_left_after_listening_is_refused FAILED (no traceback kept in the -q summary); the orchestrator's serial run of 2026-11-06 passed it. It is in the verified dial TASK-0079.31 will rely on, so a load-dependent failure may be a real race in the dial's leader/peer check. (2) 'brig's planted-link channel tests fail on darwin: kernel can't report the listener': in TASK-0201's full check (2026-11-07, macOS 27) both test_a_listener_that_left_after_listening_is_refused and test_a_link_planted_with_the_empty_stack_is_refused_by_readiness_and_connect failed with EndpointRefused '... the kernel could not report who listens there ([Errno 57] Socket is not connected)' from brig/run/dial.py:219. That is mode (b) above, and it shows mode (b) also hits the second test, test_a_link_planted_with_the_empty_stack_is_refused_by_readiness_and_connect, which this task did not name before. The fix should leave both tests passing on macOS and Linux, still asserting the refusal each was written to, and still failing if that refusal is removed.
<!-- SECTION:NOTES:END -->
