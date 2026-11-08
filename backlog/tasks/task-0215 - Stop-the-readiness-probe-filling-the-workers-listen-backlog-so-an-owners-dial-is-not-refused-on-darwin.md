---
id: TASK-0215
title: >-
  Stop the readiness probe filling the worker's listen backlog, so an owner's
  dial is not refused on darwin
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-08 19:35'
updated_date: '2026-11-08 20:19'
labels:
  - runner
  - python
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
scripts/check on main at 61cde05b failed test_a_startup_file_stopped_part_way_is_not_run_again_in_that_repl with 'the REPL could not be started again ([Errno 61] Connection refused)'. Likely cause, not yet shown on the failing test itself: python_cordis_plugin/worker.py main() calls server.listen(1), and the unconfined runner's _until_listening connects and closes as its readiness probe. If the worker has not yet accepted that probe, the owner's next dial in PythonProcess._start finds the backlog full. Measured on this Mac: against a listen(1) Unix socket with no accept, the first connect succeeds and the next three raise Errno 61 at once. Linux was not measured here; the same suites passed in the Linux container. The owner has no retry, so under load a person on darwin would see this error in place of their input running. The probe, the raw dial and listen(1) were all there before bcf17e7c, so TASK-0079.31 did not introduce it. Whether brig's wait_ready followed by Process.connect has the same window on darwin is not checked.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A dial straight after readiness is not refused while the worker has yet to accept the probe, shown by a test that holds the worker's accept back on darwin
- [x] #2 test_a_startup_file_stopped_part_way_is_not_run_again_in_that_repl passes repeatedly under scripts/check's parallel run on darwin
- [x] #3 The jailed path (Process.wait_ready then Process.connect) is checked for the same window, and the result said in the notes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Confirm on the real path: real worker with accept held, via Unjailed.start+connect and BrigJail.start+connect; unheld start loop under load before and after. 2. Fix: worker.py listen() default backlog instead of listen(1); no retry. 3. AC1 test in test_python_tool.py holding the real worker's accept back, seen failing with listen(1). 4. Check nothing relies on backlog 1 (exclusivity prose or tests), the extensions worker's backlog, test programs with listen(1). 5. AC3: jailed path checked, brig not edited (TASK-0210 is there). 6. Repeat scripts/check as the delegation asks, linux-jail-check, member check, arch-check if needed. Risk: Linux blocks rather than refuses at a full backlog, so the dial has a timeout.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Hypothesis held, on the real path (darwin, 28 cores). Unfixed worker, no hold, real Unjailed.start then connect, 1500 starts: with 24 spinners and 16 at once 243 refused (Errno 61, worker alive, socket there), 1257 connected; no spinners and 4 at once 2 refused, 1498 connected. Fixed worker, 24 spinners and 16 at once: 1500 connected, 0 refused. These were scratch scripts, not committed.

Fix: python_cordis_plugin/worker.py main() calls server.listen() (Python's default, min(SOMAXCONN, 128); SOMAXCONN is 128 here) in place of listen(1). No retry; no assertion changed. Nothing in the python plugin, CONTRACTS.md or docs/bh-02 relied on a backlog of one: grep of listen( and one-connection wording found only the worker's own call, and channel_exclusivity is not mentioned in the python plugin or the runner README. The worker takes one hello; the rest is untouched.

AC1: test_a_dial_straight_after_readiness_is_not_refused_while_the_worker_has_yet_to_accept (test_python_tool.py) runs the real worker with socket.accept held until a release file appears. Seen failing with listen(1) planted back: ConnectionRefusedError [Errno 61], 1 failed. Passing with the fix: test_python_tool.py 89 passed with -n auto --dist loadgroup.

AC2: scripts/check on the fix, 5 runs in a row, each exit 0 with 3866 passed, 231 skipped, no failure of any test (102.70s, 72.83s, 76.25s, 76.07s, 75.06s). TASK-0210's known flake did not show in these 5. They ran before a docstring-only edit to the new test; after it scripts/check bh-02/plugins/python-cordis-plugin exit 0.

AC3: the jailed path has the same window. BrigJail.start (Process.wait_ready) then its connect (Process.connect), darwin seatbelt, real worker with accept held: with listen(1) ConnectionRefusedError Errno 61; with the fix connected and the input answered 42. Mechanism: brig's readiness is a real verified dial (is_ready, connect_to, dial), so it takes a backlog slot as the unconfined probe does. The fix is in the worker, so both paths have it. Left in brig, not edited (TASK-0210 is there), reported: any jailed program with listen(1) that has not yet accepted is still refused after wait_ready (a bare one was, Errno 61), though Process.connect's docstring says only wait_ready first. brig/runtime/_oci_agent.py:155 also has listen(1) on a SOCK_SEQPACKET listener; not examined for this window.

Other listeners: extensions_cordis_plugin/worker.py:381 uses asyncio.start_unix_server, whose backlog defaults to 100 (read from the signature of create_unix_server), so it has no such window. Test programs at test_runner_confined.py:1461 and 2120 use listen(1) but make no dial after readiness.

scripts/linux-jail-check: exit 0, 328 passed, 4 skipped; it covers the real worker through test_python_repl.py but not the new test. Not verified: the new test on Linux, and how Linux behaves at a full backlog (not measured).
<!-- SECTION:NOTES:END -->
