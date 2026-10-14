---
id: TASK-0085
title: >-
  The /release tests fail while any other jail of the same user runs: the jail
  lock is one fixed path in /tmp
status: Done
assignee:
  - '@claude'
created_date: '2026-10-12 21:29'
updated_date: '2026-10-14 02:08'
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
- [x] #1 Both /release tests pass while another jail of the same user holds the real lock, or skip saying so; a test or a recorded run shows it
- [x] #2 Every bh-02 session of one user still shares one lock; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. jail.py: BrigJail.__init__ gets keyword-only lock (default _LOCK for uid); _hold and _swept use self._lock; docstring says what lock is for.
2. test_python_repl.py: the two /release tests pass lock=tmp_path/jails.lock. test_runner_confined.py: the release tests that assert freed paths (test_release_frees_what..., test_release_waits_for_a_start...) get the same; list the rest in notes.
3. Prove AC1: hold real lock /tmp/bh-02-jails-0.lock SH from a helper; run the two tests with change (pass) and stashed (fail, recorded); pop; kill holder.
4. README sentence on lock if it describes the shared lock (it does, in the Placeholders section; add one sentence).
5. Run runner tests, test_python_repl, arch-check, mypy, scripts/check as root; read exit codes directly.
Risk: _swept/_hold are BrigJail methods (lines 1043-1085), not _Jailed. Commit: squash to one commit on top of 659accd.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Change: BrigJail.__init__ takes keyword-only lock (default _LOCK.format(uid=os.getuid()), so production and every bh-02 session still share one lock; wiring.py passes none). _hold and _swept open self._lock. Tests: test_python_repl.py's two /release tests and test_runner_confined.py's test_release_frees_what_the_programs_held_once_each_owner_stopped_its_own and test_release_waits_for_a_start_under_way_and_says_it_still_runs pass lock=tmp_path/jails.lock. Other release() tests there (test_release_never_stops_a_program_its_owner_did_not_and_says_it_still_holds) assert no freed path, so they keep the real lock. README: one sentence on lock.
AC1 evidence (root, uv run pytest bh-02/app/tests/test_python_repl.py -k on_linux_release): a python3 holder took LOCK_SH on /tmp/bh-02-jails-0.lock. Unchanged code: 2 failed (the 'stays held: another bh-02 session ... is running a jail' assertion). With the change: 2 passed. Stashed again with the holder alive: 2 failed. Restored: 2 passed. uv run pytest bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py -k release with holder alive: 4 passed. Holder killed (pid 1810, now a zombie, which holds no fds); a LOCK_EX|LOCK_NB probe on /tmp/bh-02-jails-0.lock then succeeded.
Checks (root): runner plugin tests 65 passed 1 skipped (exit 0); test_python_repl.py 36 passed 1 skipped (exit 0); scripts/arch-check exit 0; uv run mypy exit 0 (184 files); ruff format --check . exit 0; scripts/check exit 0 (2527 passed, 31 skipped, 362s). The first scripts/check had failed on format and lint for my two long BrigJail lines; ruff format fixed them, and the rerun passed.
Not run: scripts/linux-jail-check (not in scope). The tester-user run was not used; these were root runs.

Closed on review (Opus, low) of 62ab0cb: CLOSE, both criteria met, nothing blocking. Reviewer held the real lock shared from another process: test_python_repl.py -k release 2 passed, test_runner_confined.py -k release 4 passed; holder killed and reaped after. The one production builder (runner wiring.py:37, Runner(BrigJail(config, host))) passes no lock, and nothing a layer or config sets reaches it. scripts/check exit 0 (2527 passed, 31 skipped); runner 65 passed; mypy and arch-check exit 0. Should-fix and nits folded into TASK-0091 before it starts: a test that a second holder of the same (tmp) lock keeps placeholders held; test_release_never_stops_a_program_its_owner_did_not_and_says_it_still_holds onto a tmp lock; the README lines at 198-199 rewrapped; the BrigJail docstring names the path, not _LOCK.
<!-- SECTION:NOTES:END -->
