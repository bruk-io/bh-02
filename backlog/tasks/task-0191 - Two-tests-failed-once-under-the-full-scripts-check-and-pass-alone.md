---
id: TASK-0191
title: Two tests failed once under the full scripts/check and pass alone
status: Done
assignee:
  - '@claude'
created_date: '2026-11-04T13:57:00Z'
updated_date: '2026-11-04T17:04:00Z'
labels:
  - tests
  - size-1
  - size-2
  - finish-moved
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Seen in the reviewer's full scripts/check for TASK-0186 (2026-11-04, on 16fb291): bh-02/app/tests/test_real_launch.py::test_keys_typed_as_the_modal_comes_up_do_not_answer_it, and bh-02/plugins/agent-cordis-plugin/tests/test_agent_records.py::test_a_call_whose_question_the_stop_withdrew_has_the_time_alone (ValueError at line 565: entries(transcript, 'tool') was empty, expected 1). Both pass when run alone. Neither was touched by that commit. They look timing-dependent under -n auto load, and they make the full check red.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each test's failure under load is reproduced or its timing dependence is named
- [x] #2 The agent-records test passes 50 of 50 under the load that failed it, its cause fixed; the real-launch modal test's cause is a product bug, moved to TASK-0193 with its own criteria
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Plugin half fixed. Unfixed, under the load runs of TASK-0192: test_a_call_whose_question_the_stop_withdrew_has_the_time_alone failed at line 565 (ValueError, entries(transcript,'tool') empty) and test_calls_a_stopped_reply_never_reached_have_the_time_alone_and_the_one_it_stopped_is_timed at line 541 (same, found by the same shape). Cause: cancel after asyncio.sleep(0.01) before the tool started / the question was asked. All three sleeps in test_agent_records.py now wait on an event set when the tool starts or approve() is entered. 50 of 50 runs passed under the same load.

No repro: those two failures are a race in the tests themselves, shown by the load runs above.

NOT fixed: test_real_launch.py::test_keys_typed_as_the_modal_comes_up_do_not_answer_it. 30 runs of the file under 8 burners gave 0 failures; under 12 burners (4 workers) it failed 2 of 6, then 1 of 2 again, at: assert "denied" not in app.text()[asked:] (the n pressed as the modal came up answered it). Cause: ApprovalScreen arms on a wall-clock timer (GRACE 0.4 s, set_timer from mount) and the y/n/escape are bindings judged when processed, not when typed. A loaded machine delays either the test or the app past the window; the app can have the timer due and the keys queued, and then the timer wins. A test-side attempt (measure the time from seeing the modal to the keys, retry the launch if it was over GRACE/4) still failed once, so the app-side stall is real and the attempt was reverted. The fix is in the product: judge a key by when it arrived (the key event's time), or make the grace overridable at launch. That is a design choice, not done here. Criterion 2 is not met for this test. Finding: after I killed pytest runs mid-way, real-launch app processes were orphaned (the lead stopped 8); I did not see one left after a run that exited normally.

Lead, 2026-11-04: finish moved by me. The second of this task's two tests (test_keys_typed_as_the_modal_comes_up_do_not_answer_it) fails because of a product bug, not a test race: ApprovalScreen judges keys when processed, not when typed, so queued keys can answer it after a stall. That is TASK-0193 now, with its own repro and fix; criterion 2 is restated so this task closes on the agent-records races it fixed.

Reviewed: closed. Both stop tests now await an event set when the tool runs / approve() is entered (after stepped.advance), so the cancel lands where the asserts expect; asserts unchanged; no sleep(0.01) remains in the file. Full check green (recorded on TASK-0192). The No repro note is fair. Restated criterion 2 is honest: it names the move, and the finish-moved label and the lead's note explain it. TASK-0193 exists on the main branch, not on this one until it merges. Minor, not filed: the task carries two size labels (size-1, size-2), and the board rule wants one.
<!-- SECTION:NOTES:END -->
