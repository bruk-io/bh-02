---
id: TASK-0110
title: >-
  test_agent_stop_ends_the_child_and_its_python_program fails once under the
  full parallel check
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-16 03:35'
updated_date: '2026-10-16 05:54'
labels:
  - subagents
  - size-2
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
During TASK-0107's close review (2026-10-16), the first full scripts/check (pytest -n auto --dist loadgroup) failed at bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py:1199: model.closed == 0 right after agent_wait reported general-1 stopped. The second full run passed (3076 passed), and the test passes alone 3 of 3. TASK-0107's commit does not touch the subagents plugin. Either agent_wait answers before the stopped child's teardown has closed its model (a product race: a caller told 'stopped' may still see the child's model open), or the test asserts too soon. Root-cause it; a flake is not a root cause, and the test must not be weakened.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The root cause is named in the notes, with a reproduction under load (for example the test repeated under -n auto beside the plugin's other tests)
- [x] #2 Either agent_wait answers only once the stopped child's model is closed, or the test waits for the close bounded, whichever the root cause says, and the test passes 50 times running under load
- [x] #3 scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Reproduced first (done): the target test repeated beside the plugin's other tests on 4 cores (-n auto --dist loadgroup, as tester under tini): 3 failures in 180 runs, 'assert (0 == 1)' on model.closed at test_agents_wiring.py:1199, the reported failure. A diagnostic copy of the file (outside the repo) recording model.hung and len(model.requests) when agent_stop runs showed (hung, requests) = (0, 1) at the stop and (0, 0, 1) after agent_wait: the stop landed before the child's second model request, the _HANG step, had begun.
2. Root cause (test, not product): the test waits with _up() for the pid file, which proves the child's python input ran, not that the loop has sent the result back and asked the model for the next step. Stopped in that window, the child has no hanging model stream, so nothing is closed and model.closed is 0. agent_wait answers only after the run task ends, which awaits the cancelled reply (_driven gathers it) and retires the child, so a step in flight is always closed by then; the siblings that wait for model.hanging/model.hung first never fail on it.
3. Fix: in the test, after _up, wait for the hang to begin (await _until(lambda: model.hung == 1), bounded 30 s, as the sibling tests do) before agent_stop. The assertions stay as they are.
4. The same flaw is in test_unloading_the_agents_row_retires_every_child_it_holds (confirmed: closed == 1 with hung == 1 at restart): out of this task's scope, filed as its own task.
5. Proof: the reproduction loop (the same 180-run loop that failed) passes with the fix; the target repeated 50+ times running under load; the file's other tests pass; scripts/check bh-02/plugins/subagents-cordis-plugin once at the end. Risk: none to product code; the test only gains a bounded wait.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root cause (test, not product): the test waited with _up() for the child's python program to have run its input (the pid file), then called agent_stop. That says nothing of the model: the loop still has to get the program's result back and ask the model for the next step, the _HANG step, whose stream is what model.closed counts. Stopped in that window the child has no hanging stream, so nothing is closed and model.closed is 0 although agent_wait honestly reports it stopped. agent_wait answers only when the run task ends, and the run awaits the cancelled reply (_driven gathers it) and retires the child, so a model step that is in flight at the stop is always closed by then: no product race. The siblings that wait for model.hanging or model.hung before stopping (lines 429, 493, 517, 544, 912 ...) never failed on it.

Reproduction under load (as tester under tini, 4 cores, -n auto --dist loadgroup, the target repeated by a scratch pytest plugin beside the plugin's other tests): 3 failed in 180 runs, assert (0 == 1) on model.closed at test_agents_wiring.py:1199, the reported failure. A diagnostic copy of the test file (outside the repo) recording model.hung and len(model.requests) showed (hung, requests) = (0, 1) at the stop and (0, 0, 1) after agent_wait, in every failure: the second model request had not been made. Same loop without the fix, 5 rounds of 40 runs: 2 rounds failed with the same assertion.

Fix: test_agents_wiring.py, after _up, await _until(lambda: model.hung == 1) (bounded 30 s, as the sibling tests do) before agent_stop. Assertions unchanged. Seen failing before, passing after.

Evidence after: 3 rounds x 60 and 20 rounds x 40 target runs beside the plugin's other tests on every core, all passed (980 runs, 0 failures); the whole plugin (-n auto --dist loadgroup) 50 consecutive rounds, the target passing every time; scripts/check bh-02/plugins/subagents-cordis-plugin exit 0 (119 passed; format, lint, types, tests, gates, docs ok; tokens skipped: no bh-01/dist), run as root under tini.

Not green, and not this task: test_unloading_the_agents_row_retires_every_child_it_holds has the same flaw (restarts the row after _up(.., 2) without waiting for both steps to hang; closed == 1 with hung == 1 at the restart) and failed 4 of the first 25 whole-plugin rounds (assert 1 == 2). Filed as TASK-0112 and not touched; the other 25 of the 50 rounds deselected it. Criterion 3 (scripts/check passes, the full one) left for the reviewer; until TASK-0112 lands the plugin run can still fail on that test.

Review (closing reviewer): full scripts/check from the repo root, run once: format, lint, types ok; tests 3171 passed, 31 skipped in 202.41s; gates ok; docs ok; tokens skipped (no bh-01/dist); exit 0. No files reformatted. TASK-0112's test passed in this run.
<!-- SECTION:NOTES:END -->
