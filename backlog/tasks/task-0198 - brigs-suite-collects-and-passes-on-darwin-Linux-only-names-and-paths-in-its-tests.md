---
id: TASK-0198
title: >-
  brig's suite collects and passes on darwin: Linux-only names and paths in its
  tests
status: To Do
assignee: []
created_date: '2026-11-07 04:27'
labels:
  - brig
  - darwin
  - tests
  - size-2
dependencies: []
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0079.34's re-run on macOS 27.0.1 (2026-11-06). uv run pytest libs/brig stops at collection: tests/unit/test_process_namespaces_pure.py:156 uses signal.SIGRTMIN (Linux only). With it ignored: tests/integration/test_supervisor_link.py errors at setup on every test (OSError Errno 43 Protocol not supported: a Linux-only socket type, no darwin skip); test_exit_status_is_recorded_not_invented runs /bin/true (macOS has /usr/bin/true); test_teardown_zombies::test_teardown_fails_an_item_whose_table_it_cannot_read gets ALREADY_GONE where it expects FAILED; and brig's leak poller reports '/bin/ps sampling failed' at teardown (test_channel_dial[peer5], test_wrap_prefix::test_zero_length_wrap_prefix_is_distinguishable_from_refusal).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 uv run pytest libs/brig -q on macOS collects every file and passes; a Linux-only test skips off Linux saying why, never by silencing a whole module
- [ ] #2 test_teardown_zombies' darwin result is explained: either teardown is wrong on darwin and fixed, or the test's premise is Linux-only and it says so
- [ ] #3 The leak poller's /bin/ps failures are traced: a real ps failure is reported, a transient one does not fail an unrelated test
- [ ] #4 brig's tiers pass on Linux (as root and as tester) and scripts/linux-jail-check passes
<!-- AC:END -->
