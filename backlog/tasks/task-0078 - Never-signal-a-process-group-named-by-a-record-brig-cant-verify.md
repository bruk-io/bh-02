---
id: TASK-0078
title: Never signal a process group named by a record brig can't verify
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-10 21:58'
updated_date: '2026-10-11 19:21'
labels:
  - brig
  - runner
  - size-3
dependencies: []
parent_task_id: TASK-0079
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`recycled(pid, stamp)` returns False for an empty stamp (libs/brig/src/brig/run/_identity.py:159), so teardown goes on to signal the group a record names. Exec registrations are files under `<jail_dir>/execs/`, and SPEC.md calls a `jail_dir` writable from inside 'the ordinary arrangement', so a forged registration with an empty stamp could aim the kill ladder at any group. Whether bh-02's jails can write their `jail_dir` (a `/tmp/bh-j-*` directory) is unchecked. Found by the brig-internals review of decision-0001, which treats records as kill authority.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Teardown never signals a group whose record's identity it can't verify, and says so in the kill report
- [x] #2 A test plants a registration with an empty stamp naming a decoy group; the decoy survives the jail's kill; the test fails before the fix
- [x] #3 The task records whether bh-02's jails can write their jail_dir, checked on Linux and macOS
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. AC3 first (it decides how wide the hole is): start a real bh-02 jail (BrigJail on Linux, bwrap) whose program tries to write <jail_dir>/execs/<pid>.json, <jail_dir>/x, and (control) <jail_dir>/tmp/x; read the results on the host. macOS: read the Seatbelt profile BrigJail compiles (spec_for's write_allows -> seatbelt rules) for whether jail_dir itself is writable; say it was not run.
2. SPEC.md first: a dated decision-172 paragraph in section 9 (by decision-155's teardown text): a record with an unknown stamp is not kill authority; the ladder signals nothing for it and the item says why.
3. Test first, seen failing: an integration test plants <jail_dir>/execs/<pid>.json with start_time '' naming a decoy group (a real process in its own session, not the jail's), runs kill_jail, asserts the decoy survives (os.kill/ps, not brig) and the item's detail says unverifiable; control in the same test: the real workload group is ENDED.
4. Fix in teardown._run_ladder: an UNKNOWN stamp signals nothing; outcome ALREADY_GONE if the group scan is empty, else FAILED with a detail naming why (FAILED: something may still run that brig would not touch). Pure decision kept small.
5. Check: uv run pytest libs/brig, scripts/arch-check, scripts/check (known failure classes from TASK-0075's notes), runner plugin tests under tester+tini.
Risks: the workload leader's own UNKNOWN stamp (a fast workload gone before the read) now leaves any children of it unsignalled -- reported FAILED, not hidden; existing tests may assert ENDED there. A forged record with a non-empty stamp whose pid names nothing still reaches a group: out of scope, a follow-up task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Sized size-3 (2026-10-11): the fix is narrow, but whether bh-02's jails can write their jail_dir is unknown on both Linux and macOS.

## What changed
- libs/brig/SPEC.md §9: decision-172 (Ruled 2026-10-11), after decision-155's paragraph, whose residual sentence now points at it: a record with an unknown stamp is not kill authority; never signalled, never reaped; ALREADY_GONE if no live member, else FAILED with a detail saying why. States the residual (a present stamp whose pid names nothing still reaches its pgid).
- libs/brig/src/brig/run/teardown.py `_run_ladder`: step 0 checks `leader_stamp == _identity.UNKNOWN` before `recycled`; no signal, no `_reap_leader` (the pid may be another child of the trusted process). Applies to the workload group, exec siblings and helpers alike. Module and `_identity.py` docstrings say so; `test_pid_identity.py`'s docstring clause about teardown asking `recycled` for UNKNOWN retired (decision-041 rule 4), its assertions unchanged.
- New libs/brig/tests/integration/test_teardown_unverifiable_record.py (2 tests).

## AC2 evidence (seen failing first)
Before the fix (root, uv run pytest on the new file): test_kill_signals_no_group_a_record_with_an_empty_stamp_names FAILED: the decoy group {9972, 9975} was gone after kill(), the forged item read exec_sibling ENDED. After: 2 passed. The second test (ALREADY_GONE for an ended group) passed before and after: it pins the case the fix must not turn into FAILED. Observations via /bin/ps, never brig; the control (workload_group ENDED) is in the same test.

## AC3: can bh-02's jails write their jail_dir?
- Linux, checked in a real jail (BrigJail.start, bwrap 0.9, project in its own temp dir, as root and as tester under tini; same result): no. From inside: mkdir <jail_dir>/execs, write <jail_dir>/x and <jail_dir>/exit -> "Read-only file system"; control <jail_dir>/tmp/x (TMPDIR, scratch) -> wrote, seen on the host. The endpoint lives in a separate /tmp/bh-k-* (python plugin client), not in jail_dir.
- BUT with the project root an ancestor of /tmp/bh-j-* (bh-02 run with cwd /tmp): yes. The same probe with cwd=/tmp wrote execs/1.json, exit and x, all seen on the host, and the malformed execs/1.json made stop() raise JSONDecodeError out of brig's kill (_execs.live). Follow-ups TASK-0079.13 and TASK-0079.14.
- macOS: not run (no darwin here). From the Seatbelt profile rendered from bh-02's own spec_for (render_sbpl, /tmp resolved to /private/tmp): `(deny file-write* (subpath "/"))`, then allows only the project subpath, `/private/tmp/bh-j-*/tmp` and the endpoint literal `/private/tmp/bh-k-*/k.sock`; nothing for jail_dir itself, so no, by the profile's rules; the same cwd-above-jail_dir exception applies (project subpath /private/tmp would cover it).

## Checks
- tini -s -- .venv/bin/python -m pytest libs/brig (root): 2 failed, 787 passed, 24 skipped; the 2 are the known root-only ones (TASK-0079.11, test_bwrap_fs read carve-out, test_probe_runner failed_control). Baseline had 11 failed, 762 passed.
- tester + tini, libs/brig + runner plugin: 846 passed, 25 skipped, exit 0.
- uv run ruff format --check / ruff check --no-fix libs/brig: 0; uv run mypy: no issues in 170 files; scripts/arch-check --no-fix: exit 0.
- tini -s -- scripts/check (root): exit 1, 3 failed / 2165 passed: the two root-only brig tests, and test_auto_memory_dir::test_the_project_is_the_git_repository... caused by an empty /tmp/.git placeholder my cwd=/tmp probe left (removed; the test then passes, 2 passed).
- scripts/linux-jail-check (with proxy env): 145 passed, 2 skipped, exit 0.
<!-- SECTION:NOTES:END -->
