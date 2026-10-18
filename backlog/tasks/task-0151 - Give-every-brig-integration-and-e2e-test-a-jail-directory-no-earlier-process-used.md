---
id: TASK-0151
title: >-
  Give every brig integration and e2e test a jail directory no earlier process
  used
status: To Do
assignee: []
created_date: '2026-10-18 12:55'
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
- [ ] #1 No test under libs/brig/tests names a jail directory from os.getpid(); each takes one from a shared fixture that makes a new directory and removes it after
- [ ] #2 A unit test fails when a test file mints /tmp/bg{os.getpid()} names again, and is seen failing on a planted one
- [ ] #3 scripts/check libs/brig passes
<!-- AC:END -->
