---
id: TASK-0085
title: >-
  The /release tests fail while any other jail of the same user runs: the jail
  lock is one fixed path in /tmp
status: To Do
assignee: []
created_date: '2026-10-12 21:29'
labels:
  - runner
  - tests
  - size-1
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in TASK-0080.09's close review (2026-10-12). bh-02/app/tests/test_python_repl.py::test_on_linux_release_frees_where_the_model_row_looks_until_the_next_input and ::test_on_linux_release_frees_the_credential_path_while_the_extensions_worker_runs expect /release to free its placeholders, but release frees them only when it takes /tmp/bh-02-jails-{uid}.lock exclusively (runner_cordis_plugin/jail.py: _LOCK, _swept, _sweep). That lock is one per user at a fixed path; a test's XDG_STATE_HOME moves only the records directory. So any other jail of the same uid fails both tests (IsADirectoryError on the placeholder local.env, or 'stays held: another bh-02 session of yours is running a jail'): an overlapping pytest run, a jail a killed run left behind, or a real bh-02 session of the person's. Seen once in a clean scripts/check run after a killed batch. Fix: let the lock path be injected (from the state directory, or a parameter the tests set to tmp_path), or have these tests skip, saying why, when the lock is already held. Changing where the real lock lives is a behaviour change: every bh-02 of the user must still share one.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Both /release tests pass while another jail of the same user holds the real lock, or skip saying so; a test or a recorded run shows it
- [ ] #2 Every bh-02 session of one user still shares one lock; scripts/check passes
<!-- AC:END -->
