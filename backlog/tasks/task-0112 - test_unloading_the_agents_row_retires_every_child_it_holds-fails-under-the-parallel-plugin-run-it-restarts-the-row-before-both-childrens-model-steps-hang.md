---
id: TASK-0112
title: >-
  test_unloading_the_agents_row_retires_every_child_it_holds fails under the
  parallel plugin run: it restarts the row before both children's model steps
  hang
status: To Do
assignee: []
created_date: '2026-10-16 05:42'
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
- [ ] #1 After _up, the test waits until both children's model steps hang (await _until(lambda: model.hung == 2), the bounded wait its siblings use) before restarting the row; its assertions stay as they are
- [ ] #2 The test passes 50 times running with the whole plugin on every core (-n auto --dist loadgroup), and the file's other tests pass
<!-- AC:END -->
