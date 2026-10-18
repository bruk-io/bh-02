---
id: TASK-0140
title: >-
  Make test_the_workload_is_refused_a_host_outside_the_allow_list stop failing
  once under -n auto
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 05:33'
updated_date: '2026-10-18 13:01'
labels:
  - brig
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
In one full scripts/check run (3638 passed, 1 failed, 118 skipped, under -n auto --dist loadgroup) libs/brig/tests/integration/test_connect_proxy_launch.py::test_the_workload_is_refused_a_host_outside_the_allow_list failed: the workload's urlopen of http://127.0.0.1:<port>/x raised ConnectionRefusedError (the test expects the proxy's own 403, line 256). The next full run passed (3639 passed), and the file passes alone 5 of 5 runs, so it is flaky and not tied to any change. It does not touch host_paths. Found while fixing TASK-0136.06; not part of it. First look: whether the workload reached 127.0.0.1 directly (so the origin was already closed or its port reused) instead of through the proxy, and whether the proxy's port file was read before the proxy listened.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The cause of the one-off ConnectionRefusedError is found and named in the notes
- [x] #2 The test, or the code it exercises, is changed so the run cannot fail this way, and the test is seen failing (planted) before the fix and passing after
- [x] #3 scripts/check libs/brig passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Reproduce under load: 8 parallel loops x20 runs of the file (done: 3 of 160 failed, every one on a pid-named /tmp/bp<pid>-<n> dir left by an earlier process that had the same pid). 2. Name the cause: the test's jail dir is /tmp/bp<pid>-<n>, never removed, reused with exist_ok; a stale proxy.port (or procs record) from an earlier run is read by the wrap shell before the new proxy replaces it. Plant it: a dead port in proxy.port at the dir the test will use -> the 403 test fails at line 256 with ConnectionRefusedError, 6 of 6. 3. Fix the test: a jail_dir fixture that makes a fresh mkdtemp dir under /tmp (short, realpath'd) and removes it after, used by all five tests. 4. Prove: same plant against the fixed file (stale dirs planted at every old name for the pytest pid) passes; load loop again, no failures. 5. File follow-ups, not done here: the same pid-named dirs in ~19 other brig integration tests; the library hazard that a reused jail dir's stale port file points a new jail at a dead or foreign port (needs a SPEC decision). 6. scripts/check libs/brig once.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
CAUSE (AC1). The test's jail directory was /tmp/bp<pid>-<n>, made with makedirs(exist_ok=True) and never removed. connect_proxy's wrap shell starts the workload as soon as the jail starts and reads <jail_dir>/proxy.port with [ ! -s file ]; the proxy publishes that file (os.replace, after bind+listen, so never before it listens) only when its own Python process has started, tens of ms later. When the directory is one an earlier process with the same pid left (pid_max here is 32768; /tmp held 1685 such dirs from 479 pids), the old proxy.port is already there, the wrap reads it, and the workload's urlopen goes through HTTP_PROXY to a dead port: ConnectionRefusedError in got.err and no '403', which is exactly line 256 (assert "403" in err, err). Not what the task guessed: the workload did not reach 127.0.0.1 directly (the proxy variables were set; NO_PROXY is empty), and the port file was not read before the proxy listened (it is published after listen, atomically). It was read before the NEW proxy had replaced an OLD file.

REPRODUCED UNDER LOAD. 8 parallel loops x 20 runs of the file alone (160 runs): 3 failed. All three were on a reused pid-named dir: two died in Jail.create with JailDirInUse (clear_earlier_records found a procs/ record left by the earlier process), one was the control test failing with 'Connection refused' in got.err (got is truncated by the workload's open(out,'w') before urlopen raises, so _wait_file returned None). The rate matches the share of the pid space already used (479/32768).

PLANTED, BEFORE THE FIX. A scratch copy of the original file whose _new_jail_dir also wrote proxy.port naming a closed port: the 403 test failed 6 of 6, then 11 of 12 on a later batch (the proxy sometimes wins the race), always with ConnectionRefusedError at line 256.

FIX (AC2). libs/brig/tests/integration/test_connect_proxy_launch.py: _new_jail_dir and the itertools counter are replaced by a jail_dir fixture (tempfile.mkdtemp(prefix='bp', dir='/tmp'), realpath'd, rmtree after), the convention test_channel_reservation_starts.py already uses; the five tests take it. A fresh directory cannot hold an earlier jail's files, so the race is not run. origin is now typed (Iterator[_Origin]) because ruff's reformat of the longer signatures moved the old type-ignore comments off their def lines. No library code changed.

PROOF, AFTER THE FIX. A scratch copy of the fixed file that plants a stale proxy.port with a closed port at /tmp/bp<pid>-0..9 (every old name): whole file passed 12 of 12 (the same plant on the unfixed 403 test: 1 of 12 passed). The 160-run 8-way load loop on the fixed file: 160 of 160 passed, and no bp dir was left behind. Scratch files deleted. scripts/check libs/brig: exit 0 (1354 passed, 111 skipped, gates ok, docs ok).

NOT DONE HERE, FILED. TASK-0150: the library hazard itself (a reused jail_dir's stale proxy.port makes the wrap hand a new jail's workload an old port, dead or foreign; needs a SPEC decision). TASK-0151: about 43 other brig integration/e2e files mint /tmp/bg<pid>... dirs the same way. Left in /tmp: the bp* dirs my load and plant runs made before the fix (a sweep of them was refused by the permission check); they only matter to the old naming, which no test uses now.

Check `scripts/check` exited 0

(30 earlier lines omitted)
```text
........................................................................ [ 31%]
........................................................................ [ 33%]
........................................................................ [ 35%]
........................................................................ [ 37%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 46%]
.........................................ss...sss.ss...ss..s.s..ss..s.ss [ 48%]
..ss..s.s...s.ssss.s.......s............................................ [ 50%]
......................................................................s. [ 51%]
........................................................................ [ 53%]
ssssssssssss.sssssssssssssssssssssssssssssssssssssssssssssssssssssss.... [ 55%]
...........................ssssssss.ss.....s.............s.............. [ 57%]
........................................................................ [ 59%]
........................................................................ [ 61%]
..............................................sss....................... [ 63%]
........s............................................................... [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 76%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
........................................................................ [ 83%]
........................................................................ [ 85%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 98%]
..................................................................       [100%]
3766 passed, 118 skipped in 202.52s (0:03:22)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/brig
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
INFO    -  Building documentation to directory: /home/user/bh-02/site
INFO    -  Documentation built in 3.61 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review (independent): every criterion met on the evidence; full scripts/check exit 0 (3766 passed, 118 skipped), the run changed no files. Not closed: close-task refuses a bug without a recorded repro. The planted reproduction was a scratch copy since deleted, so the worker should add either record-check TASK-0140 --repro -- <planted test> or a note starting 'No repro:' explaining why (the race needs a stale proxy.port planted in a pid-named dir, which the fixed test no longer uses). Then it can close. Note: decision-0009 (session trajectories) does not bear on this task.
<!-- SECTION:NOTES:END -->
