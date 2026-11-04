---
id: TASK-0192
title: >-
  test_agent_records' stopped-step test races a 10 ms sleep and fails under the
  full suite's load
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-04T14:55:00Z'
updated_date: '2026-11-04T17:04:00Z'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reproduced on the unfixed test with 8 CPU burners, the plugin's tests with -n 4: 27 of 30 runs failed, at line 281 KeyError: 'step' (this test), and at the other two sleeps (see TASK-0191). Cause: the cancel after asyncio.sleep(0.01) lands before the model's complete() is entered, so no step is recorded. Fix: Silent.complete sets an asyncio.Event on entry and the test awaits it. After the fix: 50 of 50 runs passed (0 failures) under the same load.

No repro: the failure is a race in the test itself, shown by the load runs above; the product records the step as soon as the model is entered. scripts/check bh-02/plugins/agent-cordis-plugin exits 0. The full scripts/check was started twice on a machine shared with other workers and did not finish in 30 min, so it is left for the reviewer; criteria unticked.

Check `scripts/check` exited 0

(11 earlier lines omitted)
```text
bringing up nodes...
bringing up nodes...

........................................................................ [  2%]
........................................................................ [  5%]
........s............................................................... [  8%]
...............x........................................................ [ 11%]
........................................................................ [ 13%]
........................................................................ [ 16%]
........................................................................ [ 19%]
............s........................................................... [ 22%]
........................................................................ [ 24%]
........................................................................ [ 27%]
........................................................................ [ 30%]
........................................................................ [ 33%]
........................................................................ [ 35%]
.....................s.s................................................ [ 38%]
........................................................................ [ 41%]
........................................................................ [ 44%]
........................................................................ [ 46%]
........................................................................ [ 49%]
........................................................................ [ 52%]
........................................................................ [ 55%]
........................................................................ [ 57%]
........................................................................ [ 60%]
........................................................................ [ 63%]
........................................................................ [ 66%]
........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 74%]
........................................................................ [ 77%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 85%]
........................................................................ [ 88%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 96%]
........................................................................ [ 99%]
................                                                         [100%]
2603 passed, 6 skipped, 1 xfailed in 235.78s (0:03:55)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/bh-02-flaky/site
INFO    -  Documentation built in 4.21 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
