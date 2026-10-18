---
id: TASK-0151
title: >-
  Give every brig integration and e2e test a jail directory no earlier process
  used
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 12:55'
updated_date: '2026-10-18 23:19'
labels:
  - brig
  - size-4
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while fixing TASK-0140. About 43 files under libs/brig/tests/integration and libs/brig/tests/e2e mint jail directories as /tmp/bg{os.getpid()}<infix><counter> and never remove them. This machine's /tmp holds thousands of them. The pid space is 32768 and wraps within a day of test runs, so a later process with a reused pid is handed an earlier run's directory: makedirs(exist_ok=True) accepts it and the jail starts over its files (a proxy.port, a procs/ record). Measured on test_connect_proxy_launch.py before TASK-0140 fixed it there: 3 of 160 runs under 8-way load failed, every one on a reused directory, two with JailDirInUse from Jail.create and one with ConnectionRefusedError. The other files are exposed the same way wherever stale state matters. Proposed shape (as TASK-0140 did in test_connect_proxy_launch.py and test_channel_reservation_starts.py already has): one shared jail_dir fixture in libs/brig/tests/conftest.py that makes tempfile.mkdtemp(prefix=..., dir=/tmp), resolves it, and removes it after the test; migrate the files in batches (split the task if it is too large); then tests/unit/test_jail_dir_infixes_are_unique.py, which pins the old naming, is replaced by a check that no test mints a pid-named directory. Keep the path short (the proxy port file, AF_UNIX channel sockets and the leak sweep's truncated argv all want it).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 No test under libs/brig/tests names a jail directory from os.getpid(); each takes one from a shared fixture that makes a new directory and removes it after
- [x] #2 A unit test fails when a test file mints /tmp/bg{os.getpid()} names again, and is seen failing on a planted one
- [x] #3 scripts/check libs/brig passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1) conftest.py: one jail_dir fixture and a new_jail_dir factory (tempfile.mkdtemp under /tmp, resolved, removed after the test, retried against a late-exiting supervisor); 2) migrate every integration and e2e file that minted /tmp/bg{os.getpid()}.. (43 at HEAD) plus the local jail_dir fixtures (connect_proxy_launch, channel_reservation_starts, host_records, jail_host, bwrap_channel_dir, bwrap_records_refused), in batches with a scratch AST tool; 3) replace tests/unit/test_jail_dir_infixes_are_unique.py with an AST check that no test names a path from os.getpid(), seen failing on a planted file; 4) tests of the fixture itself; 5) run integration+e2e (baseline 329 passed / 108 skipped here) and scripts/check libs/brig. Risks: darwin-only (seatbelt) and docker-only files cannot run here; tests that asserted the jail dir did not exist yet (test_jail_launch refused-create) now see an empty directory.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
What changed (tests only, no SPEC change: no brig behaviour moved). libs/brig/tests/conftest.py: a shared 'new_jail_dir' fixture (a factory over tempfile.mkdtemp(prefix='bg-', dir='/tmp'): path resolved, 16 characters, removed after the test) and a 'jail_dir' fixture on top of it for the one-directory test. Removal retries for about a second: a jail the test did not destroy has a supervisor that writes supervisor/exit as the tree goes, which left a bg-<8>/supervisor/exit behind after test_bwrap_network (2 times in 17 full runs before the retry, 0 in the 6 full runs and 2 scripts/check runs after). The 43 files that minted /tmp/bg{os.getpid()}.. (48 sites) now take them: a scratch AST tool threaded the fixture through (a helper that mints one directory takes jail_dir=; a test that mints several takes new_jail_dir) and every diff was read by hand. Also dropped the local jail_dir fixtures of test_connect_proxy_launch, test_channel_reservation_starts, test_host_records, test_jail_host, test_bwrap_channel_dir, test_bwrap_records_refused and test_channel_planted_link. Dead os.makedirs / rmtree of fixture-made directories removed. test_jail_launch's refused-create test asserted the directory was never created; it now asserts that the empty directory it was offered is still empty. test_seatbelt_smoke's realpath test now hands build_compile_ctx the fixture's /tmp name (the fixture's own path is already resolved, which would make the test vacuous).

AC1 evidence: tests/unit/test_no_test_names_a_directory_from_its_pid.py scans every .py under libs/brig/tests with ast. Run over the HEAD versions of the same files it flags exactly the 43 files (48 sites) and no other; over the working tree it finds nothing (uv run pytest libs/brig/tests/unit/test_no_test_names_a_directory_from_its_pid.py: 18 passed). AC2 evidence: that file replaces test_jail_dir_infixes_are_unique.py. Seen failing: a planted libs/brig/tests/integration/test_zz_plant.py with f"/tmp/bg{os.getpid()}zz{next(_n)}" made test_no_test_names_a_directory_from_the_process_id fail, naming 'integration/test_zz_plant.py: line 12'; removed, 18 passed. The detector is itself under test: 10 planted shapes (f-string, bare getpid, %, +, str.format, join, pathlib /, makedirs, mkdtemp) must be found and 7 uses of a pid that is not a path (message, comparison, bytes, a /dev name, docstring, template) must not be. Blind spot, said in its docstring: a pid reaching a path through a name (harness_pid, in the name of conftest's /tmp/bg{harness_pid}-spawnreg FILE, which is appended to and removed at the end of the session) is not followed. The retry was planted too: _REMOVE_TRIES = 1 made test_a_directory_written_into_while_it_is_removed_is_removed_in_the_end fail; conftest.py restored (sha256 278875f3...), 3 passed. AC3 evidence: scripts/check libs/brig exit 0 (run twice, the second on the final tree): format, lint, types (63 files), tests 1380 passed 111 skipped, gates (root, brig, cordis, cordis-helpers, host-paths), docs.

Ran here: uv run pytest libs/brig -m 'integration or e2e' -n auto --dist loadgroup: 329 passed 108 skipped before, 332 passed 108 skipped after (the 3 new fixture tests), no bg-<8> left in /tmp. Skipped here, so migrated by reading the diff only: test_seatbelt_channel, test_seatbelt_fs, test_seatbelt_smoke (darwin); the three darwin tests of e2e/test_probe_forgery.py, the three of e2e/test_scratch_darwin_batteries.py and the two of e2e/test_network_battery_against_a_real_mechanism.py; test_wait_ready's tmp_path-overflow test (darwin). The Docker tests (no daemon) were not touched: none names a pid. test_process_namespaces and test_control_battery skip here (no namespaces in this container) and were not touched. Filed, not started: retire the scratch sweep (_scratch_sweep, decision-121: nothing makes a /tmp/bg<pid> root now), and remove the directories other tests leave in /tmp (tests/supervised_jail.py::new_jail_dir leaves 2 bg-sv-<8> per run).
<!-- SECTION:NOTES:END -->
