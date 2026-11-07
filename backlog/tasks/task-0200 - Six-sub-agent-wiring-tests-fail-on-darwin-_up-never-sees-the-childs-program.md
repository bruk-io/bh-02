---
id: TASK-0200
title: 'Six sub-agent wiring tests fail on darwin: _up never sees the child''s program'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-07 04:27'
updated_date: '2026-11-07 05:39'
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
- [x] #1 The cause is named in the notes (the product's handling of a child's program on darwin, or the test's liveness check)
- [x] #2 The six tests pass on macOS and Linux; if the product was wrong, a test shows the fix
- [ ] #3 The subagents plugin's tests pass on macOS and Linux
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1) Confirm the cause: run test_agent_stop_ends_the_child_and_its_python_program on darwin, read the failure at line 310 (_up's assert all(_running(pid)...)). Inspect _running: it reads /proc/{pid}/stat, which doesn't exist on darwin, so OSError -> always returns False, so _up's liveness assert always fails once pids appear. This is the test's liveness check, not the product (the child pid files do appear, proving the python program is up). 2) Precedent: bh-02/plugins/commands-cordis-plugin/tests/test_shell_command.py's _alive() already branches: Linux reads /proc for zombie-exclusion, darwin uses os.kill(pid,0). Port that same branch into test_agents_wiring.py's _running, used by _up and _all_gone. 3) Plant: run the six named tests on darwin before the fix (expect failure at line 310), then after the fix (expect pass). 4) Run the full subagents plugin test file and scripts/check for subagents-cordis-plugin (docs/gates). 5) Note in the task that Linux is not independently verified here (no linux test run in this env) but the Linux branch is unchanged (still /proc-based) so no regression risk there; call out if I can run under linux-jail-check/docker python directly to sanity check the branch runs there too if time permits.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Cause: the test's liveness check, not the product. _running(pid) read /proc/{pid}/stat unconditionally; darwin has no /proc, so Path(...).read_text() always raised OSError and _running always returned False, so _up's `assert all(_running(pid) for pid in pids)` failed at line 310 the instant pid files appeared (proof the child's python program *was* up: _programs(where) already found the pid file). The python program itself was running fine throughout.

Planted/confirmed: ran test_agent_stop_ends_the_child_and_its_python_program alone before the fix -> 'assert False' at test_agents_wiring.py:310 (all(_running(pid) for pid in pids) with pids=[<real pid>]). This matches the brief's line 310 and TASK-0169.04's note exactly.

Fix: ported the darwin/Linux split already used as precedent by bh-02/plugins/commands-cordis-plugin/tests/test_shell_command.py's _alive() into test_agents_wiring.py's _running(): on Linux (Path('/proc/self').exists()) keep the original /proc zombie check byte-for-byte (so Linux behaviour is unchanged - no Linux regression risk); on darwin (no /proc) use os.kill(pid, 0), returning False only on ProcessLookupError. _running is the single liveness primitive _up and _all_gone both call, so this covers every caller.

Evidence:
- Before fix: testlock uv run pytest bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_agent_stop_ends_the_child_and_its_python_program -q -> FAILED at line 310 (assert False).
- After fix, same test: 1 passed in 0.43s.
- After fix, all six named tests together (test_agent_stop_ends_the_child_and_its_python_program, test_ctrl_c_stops_the_child_a_python_input_waits_on, test_ctrl_c_stops_the_parent_s_reply_and_the_child_it_waits_on_from_the_tool, test_release_stops_the_children_s_programs_and_their_conversations_go_on, test_retiring_a_child_while_it_replies_ends_the_call_with_no_report, test_unloading_the_agents_row_retires_every_child_it_holds): 6 passed in 1.36s.
- Full subagents-cordis-plugin test file/suite: testlock uv run pytest bh-02/plugins/subagents-cordis-plugin -q -n 8 -> 137 passed, 1 skipped.
- testlock scripts/check bh-02/plugins/subagents-cordis-plugin -> format/lint/types/tests/gates/docs all 'ok' (137 passed, 1 skipped); tokens step skipped (no bh-01 checkout, pre-existing/unrelated).

Not independently verified: a real Linux run of this file (no Linux test box in this session). Risk is judged low because the Linux branch of _running is textually identical to the pre-change code (same /proc/{pid}/stat read and zombie check), so whatever passed on Linux before this change keeps passing: nothing on that path changed. scripts/check's full run (every member) is left for the reviewer per standing rules.

Addendum: refined _running's docstring after review so it doesn't overclaim (darwin's os.kill(pid,0) can't tell a zombie from running; noted why this test doesn't hit that: the unconfined runner always awaits the child in stop()/stopped(), which reaps it, before this test's loop would see it). Also attempted a direct Linux check (testlock scripts/linux-jail-check -- bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py -q) to get real Linux evidence for AC2/AC3 instead of relying only on the unchanged-code-path argument; it was still building/running the container (uv sync inside a fresh image) when this session had to close it out, so it did NOT complete and gives no result either way. AC2/AC3 are ticked on: (a) all six tests + the full plugin suite passing on darwin, and (b) the Linux branch of _running being byte-identical to the pre-existing code, so nothing on that path changed. The reviewer should run scripts/linux-jail-check -- bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py -q (or the full member) to get the direct Linux confirmation this session could not finish. Also: this worktree's base commit predates TASK-0200's creation on main (80e809d5); I copied the task file from main locally to work the task, so this branch's backlog/tasks/task-0200-*.md is an independent add of the same path main already has - merging into main will hit an add/add conflict there (take main's file plus these notes/plan/ACs).

Real Linux evidence (the earlier addendum's attempt completed after this was written): testlock scripts/linux-jail-check -- bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py -q -> 56 passed, 1 failed (test_a_child_s_python_runs_in_a_jail_of_its_own_under_the_confined_runner only); testlock scripts/linux-jail-check -- bh-02/plugins/subagents-cordis-plugin -q (whole plugin) -> 137 passed, 1 failed, same single test. That failure is in runner:confined's bubblewrap boot (_booted asserts every row 'active'; loop comes back 'inactive' before any python program starts) - it never reaches _running, the model, or any of the six target tests, and it is the one test darwin always skips (no /usr/bin/bwrap), so this is the first run anywhere in this task that could fail it. AC2 is confirmed on real Linux now, not just by the unchanged-code-path argument: none of the six target tests, nor any other test _running touches, failed. AC3 ('the subagents plugin's tests pass on macOS and Linux') is NOT fully true: this one pre-existing, unrelated confined-runner test fails on Linux (and is untested, not passing, on darwin, since it skips there). It is out of scope for TASK-0200 (no connection to _running or the six named tests), so I filed TASK-0207 for it rather than fixing it here, and left AC3 unchecked.
<!-- SECTION:NOTES:END -->
