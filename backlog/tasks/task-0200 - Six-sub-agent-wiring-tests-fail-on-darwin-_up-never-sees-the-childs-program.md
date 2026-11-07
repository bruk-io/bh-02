---
id: TASK-0200
title: 'Six sub-agent wiring tests fail on darwin: _up never sees the child''s program'
status: To Do
assignee: []
created_date: '2026-11-07 04:27'
labels:
  - subagents
  - darwin
  - tests
  - size-2
dependencies: []
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
On macOS 27.0.1 (2026-11-06, with and without Claude Code's sandbox, run alone): test_agents_wiring.py's test_agent_stop_ends_the_child_and_its_python_program, test_ctrl_c_stops_the_child_a_python_input_waits_on, test_ctrl_c_stops_the_parent_s_reply_and_the_child_it_waits_on_from_the_tool, test_release_stops_the_children_s_programs_and_their_conversations_go_on, test_retiring_a_child_while_it_replies_ends_the_call_with_no_report and test_unloading_the_agents_row_retires_every_child_it_holds fail at line 310 (_up: all(...) is False). TASK-0169.04's notes called them environment; they are not. Whether the product or the test's liveness check is wrong on darwin is the question.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The cause is named in the notes (the product's handling of a child's program on darwin, or the test's liveness check)
- [ ] #2 The six tests pass on macOS and Linux; if the product was wrong, a test shows the fix
- [ ] #3 The subagents plugin's tests pass on macOS and Linux
<!-- AC:END -->
