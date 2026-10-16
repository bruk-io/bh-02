---
id: TASK-0123
title: >-
  Tell a bh-02 user what to do when the jail mounts no Python for brig's
  supervisor
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-16 13:48'
updated_date: '2026-10-16 22:01'
labels:
  - runner
  - size-1
dependencies: []
priority: low
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0084.02's close review. When no interpreter the jail mounts is found, brig's InterpreterNotMounted reaches the runner row's boot diagnosis unchanged, and its advice ('build the mechanism with strict_linux(python=...)') is for code that embeds brig, not for a bh-02 user, whose steps are to install python3 or run with --no-jail, as the runner's missing-bwrap error already says. cordis prints the exception's repr, so a note added with add_note would not show: the runner has to raise its own error naming those steps, with brig's as its cause.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A host whose jail mounts no usable interpreter fails the runner row with a message that tells the person to install python3 or run with --no-jail, and names brig's reason, shown by the app-level test TASK-0084.02 added
- [x] #2 brig is unchanged
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. jail.py: a pure function naming the no-interpreter refusal in bh-02's terms (install python3, or use runner:unconfined / bh-02 --no-jail, knowing it confines nothing; the missing-bwrap error's style), naming the candidates looked for and brig's reason (InterpreterNotMounted, the interpreter the jail does not mount). BrigJail.compile catches brig's InterpreterNotMounted around stack_for(...).compile and raises that RuntimeError from brig's error, so the cause is kept and the message is in the exception itself (cordis prints repr). Covers the constructor's probe compile and each launch. brig untouched.
2. Tests: test_runner_confined.py's no-interpreter test now expects the runner's RuntimeError, its __cause__ an InterpreterNotMounted, and the steps in the text; bh-02/app/tests/test_python_repl.py's test asserts the new wording the person reads in the row diagnosis.
3. README (runner plugin, supervisor's interpreter paragraph) and the module/supervisor_interpreter docstrings say what the person now reads.
Risks: the translation must not catch anything but brig's refusal; the darwin path never raises it. The app test is load-sensitive? no, it is a compile refusal. Proof: planted check: with the catch removed (or the message replaced by brig's) the no-interpreter tests fail; restored and green. Then runner tests and test_python_repl.py as tester under tini; scripts/check at the end of the batch.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
What changed (bh-02/plugins/runner-cordis-plugin): BrigJail.compile catches brig's InterpreterNotMounted around stack_for(...).compile and raises the runner's own RuntimeError from it (__cause__ stays brig's). Its text, from the private _no_python_message: the jail runs brig's supervisor as PID 1 under a Python it mounts; none of the Pythons looked for ((candidates)) is one; brig refused the jail (InterpreterNotMounted): <python> is under no path the jail mounts; install python3, or use runner:unconfined for the runner row (or bh-02 --no-jail), knowing it confines nothing. brig's advice (strict_linux(python=...)) stays in the cause. The probe compile in the constructor and every launch go through compile, so both raise it. Docstrings (supervisor_interpreter, compile's Raises) and the runner README's supervisor paragraph say it. Tests: test_a_host_whose_jail_mounts_no_interpreter_is_refused_with_what_a_person_does (RuntimeError, cause InterpreterNotMounted, candidates, reason, steps, no strict_linux text); bh-02/app/tests/test_python_repl.py test_on_linux_a_host_with_no_interpreter_... asserts the new wording in the row diagnosis. brig: unchanged (git diff d552a08 -- libs/brig is empty).
Evidence AC1: test_python_repl.py::test_on_linux_a_host_with_no_interpreter_the_jail_mounts_does_not_start_and_says_brig_s_reason passes as tester under tini (1 passed). Planted: with the catch's raise replaced by a bare raise (brig's error crosses unchanged), test_a_host_whose_jail_mounts_no_interpreter_is_refused_with_what_a_person_does FAILED (1 failed); restored, then green.
Evidence AC2: git diff d552a08 -- libs/brig is empty.
Checks: runner tests + bh-02/app/tests/test_python_repl.py as tester under tini (-n 2 --dist loadgroup): 117 passed, 2 skipped, 95 s; machine shared with two other workers, no timing claimed. ruff format --check and ruff check on the changed files: clean. scripts/check is run once at the end of the batch (TASK-0124's commit), not here.
<!-- SECTION:NOTES:END -->
