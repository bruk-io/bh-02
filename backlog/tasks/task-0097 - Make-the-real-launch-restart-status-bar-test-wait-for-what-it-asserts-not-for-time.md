---
id: TASK-0097
title: >-
  Make the real-launch restart status-bar test wait for what it asserts, not for
  time
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-14 13:40'
updated_date: '2026-10-17 04:18'
labels:
  - app
  - tests
  - size-2
dependencies: []
modified_files:
  - bh-02/app/tests/test_real_launch.py
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
bh-02/app/tests/test_real_launch.py::test_while_the_model_restarts_the_status_bar_says_so_and_a_message_waits_visibly failed once in TASK-0093's close review (221 passed, 1 failed) and passed alone and on rerun; TASK-0087's worker saw a timing flake in a test_real_launch status-bar test the same way. TASK-0093 added a second pty launch to the file. A real-launch test that reads a pty must wait for the text it asserts (as TASK-0083 did for the /model refusal), never for a fixed time; find what this one races on and make it wait for it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The test waits for the screen text it asserts, with a bound, never for a fixed delay; the race it had is named in the notes
- [x] #2 test_real_launch.py passes 20 runs in a row under load (for example beside another pytest process), recorded in the notes
- [x] #3 scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. Find the race: replay the test's steps with a diagnostic script (outside the repo) and read the one recorded failure (TASK-0093 close review).
2. Prove it by planting the stall a loaded test process has between its two typed lines, and watch the old assertion fail on a correct app.
3. Fix, test-only, in bh-02/app/tests/test_real_launch.py: the model field's 'active again' check waits for the bar's own text (bounded) instead of reading the last 'model: s/slow-2' out of what has arrived; the /clear step stops demanding a waiting line that exists only inside the restart window (the burst test beside it pins that line), and waits for the reply.
4. Run the file 20 times in a row beside other pytest processes and record each; scripts/check bh-02/app --no-gates --no-docs once.

### Risks
The file takes about 2.5 minutes a run, so 20 runs is most of an hour on a shared machine. App code is not touched unless the race turns out to be in the app.

### Proof
The planted stall fails the old test and passes the new one; a planted bar stuck on starting fails the new wait; 20 of 20 file runs beside other pytest processes; scripts/check bh-02/app --no-gates --no-docs exit 0.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Deferred by the owner (2026-10-15): this run fixes only critical bugs; this one is not critical (no data loss, no security exposure, a workaround exists). Not to be started without the owner's word.

Orchestrator, 2026-10-17: the owner's word to start it, which the earlier deferral asked for: "ok wrap up all tasks that you are able to" (in conversation, this date).

Worker (TASK-0097). Started on the Orchestrator note above (the owner's word to start, quoted by the orchestrator; I could not check it myself). Test-only change in bh-02/app/tests/test_real_launch.py; no app code touched.

THE RACE. The assertion that failed in TASK-0093's close review (the only recorded failure: scratchpad app.log, "1 failed, 221 passed", line 773 of that day's file) is the last one of the test: after `/clear` and `again`, `said = app.text()[replied:again]` must hold "⧗ waiting for agents, loop, python, transcript to start" or "waiting for `python`". Both lines are transient. The first is shown only if `again` is submitted while the restart /clear queued is still running (`BhApp.send`, with `Bridge.waiting_on`: the line is kept and a row is coming up); the second only if the line is read after the restart but the python tool is not yet registered (agent loop `reply`: `_WAITING`). A line read when every row and the python tool are already up gets neither, and that is correct: the line is answered at once. Which of the three happens is when this process presses Enter for `again` (Launched.type presses the text, reads for a fixed 0.2 s, then Enter; it never looks at the screen between `/clear` and `again`) against how long the restart takes. A test process stalled for a moment on a loaded machine lands in the third case and the assertion, which wants the first or second, fails on a correct app. The test's own comment said "Which is timing; the new loop answers either way", and the assertion contradicted it.
Evidence, planted: with `app.settle(3.0)` between `app.type("/clear")` and `app.type("again")` (a stalled test process), the unfixed test fails at that assertion every time (AssertionError on `said`, test_real_launch.py:804, the same failure as the recorded one: the screen after /clear shows the lines "› again" and "↻ python reloaded" and neither waiting line). The fixed test with the same plant passes. I did not see it fail unplanted: the 20 file runs below, 20 runs of the two restart tests unfixed (4 in parallel, 5 each, on a machine at load 5 to 8), and 14 replays of the /clear step alone (6 idle, 8 with the test process at nice 19 beside 4 busy loops) all gave the first or second case; the second (the loop's note) every time when idle.

THE STATUS-BAR READ (not shown to fail). `status = app.text()[app.text().rfind("model: s/slow-2"):]` after `replied` reads the last model field out of whatever the pty read has returned so far; a read that ends between the bar's repaint and the reply's text would see the "starting…" form. In 36 replays the bar's "up" repaint was always in the stream before the reply (3773 bytes before it, in every run) and the test's read saw it, so I have no run showing it fail; the code allows it, since the bar and the transcript are painted by separate messages and the read has no boundary. It is now `app.wait_for("model: s/slow-2 ", 20, after=starting)`: the bar's own text, bounded. Planted: with frame.phase_after not leaving `starting` at `active` (reverted), the fixed test fails at that wait ("'model: s/slow-2 ' never appeared", 26 s); restored, passes.

THE FIX. The model-field check is the wait above. The /clear step types `/clear` and `again` as before, waits for "echo: AGAIN (message 1)" (20 s) and asserts "stopped: interrupted" is not in what was drawn meanwhile; it no longer demands a waiting line that exists only inside the restart's window. The waiting line for /clear stays pinned deterministically by test_a_message_typed_the_moment_after_model_waits_for_the_new_model, which types both lines in one burst and waits for it. Residual, not changed: this test types `hello` after seeing "starting…" and needs it submitted within the model's 3 s fake start (`_SLOW_START_S`); the margin is about 2.5 s against about 0.25 s of typing.

SAME PATTERN ELSEWHERE IN THE FILE (not changed; the fix is not a shared helper). test_a_message_typed_the_moment_after_model_waits_for_the_new_model reads the bar the same way (`shown = app.text()` after `replied`, `shown[shown.rfind("model: s/slow-2"):].startswith(...)`, and `0 <= starting < replied`). test_clear_clears_the_screen_and_model_does_not reads every bar drawn since (`re.findall(r"session: [^\n]*", ...)`) after one wait, so a read ending inside a bar's line would drop its jail field. test_a_bang_line_runs_in_the_shell_... waits for "YOU", then `settle(0.5)` (a fixed delay), then asserts "(message 1)" is in the reply; waiting for "(message 1)" would remove it. `settle(1.0)` after "↻ chat reloaded" (several tests) stands in for "the restart is done" before typing the next line; those lines are answered either way, so they do not fail.

AC2. Machine shared at the start with three other workers, then mostly mine (load average at the end of each run in brackets). `tini -s -- .venv/bin/python -m pytest bh-02/app/tests/test_real_launch.py -q`, 20 runs in a row, beside `uv run pytest bh-02/plugins/models-cordis-plugin -q` looped (124 passes, 0 failures) and, from run 6 on, also `pytest bh-02/plugins/tui-cordis-plugin bh-02/plugins/agent-cordis-plugin -n 2` looped (28 passes, 0 failures): runs 1-20 all exit 0, "34 passed" each, 126 to 145 s each (load 4.23, 3.48, 2.49, 1.06, 2.01, 1.81, 3.17, 4.62, 2.99, 4.93, 3.56, 7.64, 2.68, 3.00, 1.41, 1.47, 1.88, 1.45, 5.25, 6.37). The unfixed file also passed 20 of 20 of the two restart tests in parallel runs, so these runs show no regression; the planted stall above is what shows the fix.
AC3. Left for the reviewer. `scripts/check bh-02/app --no-gates --no-docs`: exit 0 (format ok, lint ok, types ok, 242 passed 1 skipped in 73 s; tokens skipped, no bh-01 dist).

Reviewer: AC1 and AC2 verified (no settle/sleep in the changed test, every wait_for bounded; changed test 3/3 passes, file 34 passed in 131 s). AC3 left for the orchestrator's full check: the worker's member check ran with --no-gates --no-docs, so the gates never saw the edited test file. READY. Should-fix: test_real_launch.py:826 (burst test) still reads the bar with rfind after the reply, the same pattern this task replaced at :794. Nit: :823-825 same read; the bang-line test's settle(0.5).

Full scripts/check on 5cf6e37 (this task's commits with the rest of the batch): exit 0, format, lint, types, tests 3454 passed 50 skipped, five gates, docs (orchestrator, 2026-10-17; log at the session scratchpad, check-batch4b.txt).

No repro: the race only shows when the test process stalls between /clear and again; the worker reproduced it with a planted 3 s settle (the old test failed at its last assertion, the shape of TASK-0093's recorded failure) and the fixed test passes with the same plant.
<!-- SECTION:NOTES:END -->
