---
id: TASK-0191
title: Two tests failed once under the full scripts/check and pass alone
status: To Do
assignee: []
created_date: '2026-11-04T13:57:00Z'
updated_date: '2026-11-04T15:01:00Z'
labels:
  - tests
  - size-1
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Seen in the reviewer's full scripts/check for TASK-0186 (2026-11-04, on 16fb291): bh-02/app/tests/test_real_launch.py::test_keys_typed_as_the_modal_comes_up_do_not_answer_it, and bh-02/plugins/agent-cordis-plugin/tests/test_agent_records.py::test_a_call_whose_question_the_stop_withdrew_has_the_time_alone (ValueError at line 565: entries(transcript, 'tool') was empty, expected 1). Both pass when run alone. Neither was touched by that commit. They look timing-dependent under -n auto load, and they make the full check red.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each test's failure under load is reproduced or its timing dependence is named
- [ ] #2 Both pass in a stated number of full scripts/check runs, or the cause is fixed
<!-- AC:END -->
