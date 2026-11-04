---
id: TASK-0192
title: >-
  test_agent_records' stopped-step test races a 10 ms sleep and fails under the
  full suite's load
status: To Do
assignee: []
created_date: '2026-11-04T14:55:00Z'
labels:
  - agent
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
In the full check on claude/subagents-followups (HEAD 2a306af, recorded on TASK-0189), bh-02/plugins/agent-cordis-plugin/tests/test_agent_records.py::test_a_step_that_failed_or_was_stopped_has_a_record_of_what_came_before_it failed with KeyError: 'step' at line 281. 8 further runs of the plugin with -n auto, and 5 runs of the file, all passed, and the branch does not touch the agent plugin. The test cancels the reply after asyncio.sleep(0.01) and assumes the step's start was recorded by then; under load the cancel lands first, so the answer has no step. scripts/check goes red at random.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The test waits on an event the model fake sets when complete() is entered, not a fixed sleep
- [ ] #2 The test passes 50 runs under scripts/check's -n auto load
<!-- AC:END -->
