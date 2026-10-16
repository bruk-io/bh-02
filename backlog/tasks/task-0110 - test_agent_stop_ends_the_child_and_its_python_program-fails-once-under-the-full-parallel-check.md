---
id: TASK-0110
title: >-
  test_agent_stop_ends_the_child_and_its_python_program fails once under the
  full parallel check
status: To Do
assignee: []
created_date: '2026-10-16 03:35'
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
- [ ] #1 The root cause is named in the notes, with a reproduction under load (for example the test repeated under -n auto beside the plugin's other tests)
- [ ] #2 Either agent_wait answers only once the stopped child's model is closed, or the test waits for the close bounded, whichever the root cause says, and the test passes 50 times running under load
- [ ] #3 scripts/check passes
<!-- AC:END -->
