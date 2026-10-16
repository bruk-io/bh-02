---
id: TASK-0112
title: >-
  test_unloading_the_agents_row_retires_every_child_it_holds fails under the
  parallel plugin run: it restarts the row before both children's model steps
  hang
status: Done
assignee:
  - '@claude'
created_date: '2026-10-16 05:42'
updated_date: '2026-10-16 06:18'
labels:
  - subagents
  - size-1
dependencies: []
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in TASK-0110 while root-causing test_agent_stop_ends_the_child_and_its_python_program. Same flaw, other test: bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_unloading_the_agents_row_retires_every_child_it_holds waits with _up(tmp_path, 2) (both children's python programs have run their input), then restarts the agents row and asserts model.closed == 2. _up says nothing of the model: a child restarted before the loop has sent its program result back and asked for its next step (the _HANG step) has no hanging stream to close, so model.closed is 1.

Seen: the whole plugin on every core (su tester -c 'tini -s -- .venv/bin/python -m pytest -q -p no:cacheprovider -n auto --dist loadgroup bh-02/plugins/subagents-cordis-plugin') failed this test in 4 of 25 consecutive runs with assert (1 == 2) on model.closed; a diagnostic copy recording model.hung and len(model.requests) at the restart showed (hung, requests) = (1, 3), or (0, 2): one or both second steps had not begun. Not a product race: the unloading row retires every child and the runs end with the report, so any step in flight is closed by then (the tests that wait for model.hanging or model.hung first do not fail).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 After _up, the test waits until both children's model steps hang (await _until(lambda: model.hung == 2), the bounded wait its siblings use) before restarting the row; its assertions stay as they are
- [x] #2 The test passes 50 times running with the whole plugin on every core (-n auto --dist loadgroup), and the file's other tests pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Edit one test: in test_unloading_the_agents_row_retires_every_child_it_holds (bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py), add a comment and 'await _until(lambda: model.hung == 2)' directly after 'programs = await _up(tmp_path, 2)', before the row restarts. Same shape as TASK-0110's change in the stop test (model.hung == 1). Assertions unchanged; nothing else touched.
2. Run the file's tests as tester under tini (the target and the file's other tests, -n auto --dist loadgroup) to see it green.
3. Criterion 2: the 50-round whole-plugin loop as the delegation gives it, in two halves of 25 if one call would run past the timeout; count passing rounds; failing rounds are printed.
4. Once, at the end: scripts/check bh-02/plugins/subagents-cordis-plugin (exit code read directly, not through a pipe). Criterion 1 and 2 ticked only with the evidence. Risk: none to product code; the test only gains a bounded wait (30 s via _until, which fails loudly if the steps never hang).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fix: test_agents_wiring.py, test_unloading_the_agents_row_retires_every_child_it_holds: await _until(lambda: model.hung == 2) right after _up(tmp_path, 2), before the row restarts, the same change TASK-0110 made to the stop test. Assertions unchanged; the diff is that wait and its 2-line comment.
- Before the fix (from the description, not re-run here): the whole plugin failed this test 4 of 25 rounds, assert (1 == 2) on model.closed.
- The file alone, as tester under tini (tini -s -- .venv/bin/python -m pytest -q -p no:cacheprovider -n auto --dist loadgroup .../test_agents_wiring.py): 48 passed, exit 0.
- Criterion 2: the whole plugin (-n auto --dist loadgroup) 50 rounds running as tester under tini, the brief loop in two halves of 25 (about 14 s a round): 50 of 50 passed, no round printed a failure. The file's other tests ran in every round.\n- scripts/check bh-02/plugins/subagents-cordis-plugin, run as root under tini, exit 0: format, lint, types (6 files), tests (119 passed), gates, docs ok; tokens skipped (no /home/user/bh-01/dist).\n- Not verified: the other _up callers (lines 430, 521, 548, 1402) were only read, not changed; none asserts a model.closed count across a restart in the lines I read.

No repro: the failure (4 of 25 whole-plugin rounds, assert 1 == 2 on model.closed) was recorded in the description before the fix; a passing test can't be recorded as a repro, as TASK-0110's close did.

Review (closing reviewer): CLOSE. AC1 met: commit 51dff1d adds only a bounded 'await _until(lambda: model.hung == 2)' plus comment after _up(tmp_path, 2), before loader.restart('agents'); assertions unchanged. AC2 met: worker's 50/50 rounds; reviewer re-ran the whole plugin -n auto --dist loadgroup as tester under tini 5 times, 119 passed and exit 0 each. Findings: none blocking or should-fix; nit: the other _up callers were read, not audited, no failure seen there; no draft filed.
<!-- SECTION:NOTES:END -->
