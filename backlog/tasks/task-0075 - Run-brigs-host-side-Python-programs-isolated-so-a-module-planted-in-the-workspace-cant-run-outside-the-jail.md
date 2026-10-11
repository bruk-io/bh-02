---
id: TASK-0075
title: >-
  Run brig's host-side Python programs isolated, so a module planted in the
  workspace can't run outside the jail
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-10 21:58'
updated_date: '2026-10-11 16:21'
labels:
  - brig
  - runner
  - size-3
dependencies: []
parent_task_id: TASK-0079
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
brig's exit wrapper runs `python -c` with its working directory set to the workload's (libs/brig/src/brig/run/launcher.py:236), and no interpreter brig starts runs with `-I`, so the workload's directory is first on its import path. Reproduced 2026-10-10 with the empty stack: a `subprocess.py` planted in the workspace ran inside the wrapper (argv `-c`), outside any jail. The rlimits trampoline and the egress proxy run `python -m`, which puts the working directory first too (not reproduced). In bh-02 the Python process's working directory is the project root, which jailed code can write, so the next jail start (the Python process started again, the extensions process starting, the first input after /release) would run a planted module unconfined. Not yet reproduced end to end through bh-02. Found by the brig-internals review of decision-0001.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every Python interpreter brig starts on the host runs isolated (`-I`), and a test lists them all
- [x] #2 A test plants `subprocess.py`, `signal.py` and a `brig/` package in the workload's working directory and shows none is imported by the exit wrapper, the trampoline or the egress proxy; the same test fails before the fix
- [x] #3 In bh-02, a test plants a module in the project root, starts the Python process again, and nothing runs outside the jail
- [ ] #4 brig's test tiers, `scripts/linux-jail-check` and `scripts/check` pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Inventory every interpreter brig starts on the host (AST over brig/src plus the wrapper's own source): the exit wrapper (python -c, run/_exit_status.wrapper_argv), the tether watcher the wrapper starts (python -c TETHER), the rlimits trampoline (python -m brig.mech.trampoline, outermost so on the host) and the egress proxy helper (python -m brig.proxy). Probe batteries' python3 -c are jailed workloads, not host programs.
2. SPEC.md first: a dated decision-169 paragraph in section 8 (host-side interpreters run -I), naming TASK-0075.
3. Add -I to the four argv; update the unit/integration tests that pin the exact trampoline prefix.
4. Tests: a unit test that finds every interpreter launch by AST and asserts the list is exactly the four, each -I (AC1); an integration test that plants subprocess.py, signal.py and brig/ in the workload cwd and launches through the wrapper (+tether), the trampoline and the proxy, asserting no plant ran and the workload ran (AC2), seen failing before the fix; a bh-02 test (app/tests/test_python_repl.py) that plants the same in the project root from a jailed input, restarts the Python process, asserts no marker outside the jail, with a host control that shows the plant fires for a non-isolated interpreter (AC3).
5. Risks: -I drops PYTHONPATH and cwd; brig must stay importable through the editable .pth in site-packages (kept by -I). Check nothing relies on PYTHONPATH.
6. Proof: brig unit/integration/e2e vs baseline, scripts/linux-jail-check, scripts/check.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Sized size-3 (2026-10-11): the change is small (-I on three interpreters), but it is a jail escape across two codebases, -I's effect on editable installs and PYTHONPATH is unchecked, and bh-02 needs an end-to-end test.

2026-10-11, implementing worker.
What changed: SPEC.md section 8 gets decision-169 (every interpreter brig starts on the host runs -I; brig must be importable from site-packages; a new one goes on the test's list), naming TASK-0075. -I added to the four host interpreters: the exit wrapper and its tether watcher (run/_exit_status.py), the rlimits trampoline (mech/rlimits.py; outermost, so on the host, in the workload's cwd) and the egress proxy helper (mech/connect_proxy.py). Probe batteries' python3 -c are jailed workloads, left alone. Nothing in brig or bh-02 relies on PYTHONPATH; brig resolves through the editable .pth, which -I still reads; bh-02's workers were already -I. Pins of the exact trampoline/proxy argv updated in test_rlimits_compile, test_connect_proxy_compile, test_stack_compile, test_stack_matrix_ordering.
AC1: tests/unit/test_host_interpreters.py finds every argv display starting sys.executable/python with -c/-m by AST over brig/src plus WRAPPER_SOURCE, asserts the set is exactly the four, each -I, with a control that the visitor tells -I from its absence. Before the fix: 4 failed, 2 passed (the listing passed, the -I checks failed); after: 6 passed.
AC2: tests/integration/test_host_interpreters_isolated.py plants subprocess.py, signal.py and brig/ in the workload cwd (each records its name outside, then hands back the real module), launches one jail through Stack([rlimits, ConnectProxy]) with a tether, waits for the workload, closes the tether and waits for the watcher to end its group. Seen failing before the fix (twice, the second by reverting the three source files from a scratch copy, restored and sha256-verified): 'planted modules imported on the host: [brig, brig, signal, signal, signal, subprocess]'. After: passes. Control in the same test: python -c / -m without -I in that cwd imports all three plants.
AC3: bh-02/app/tests/test_python_repl.py::test_on_linux_a_module_an_input_plants_in_the_project_runs_nowhere_outside_the_jail: a jailed input plants the same three in the project root, the Python process restarts (kernel __aexit__/__aenter__) and runs another input; the record outside the project stays absent. Without -I (scratch revert, sha256-restored) it fails: 'planted modules ran outside the jail: signal subprocess signal brig signal' (reproduced end to end through bh-02). Control: no-I interpreters in the root run every plant.
AC4 not met here, for reasons outside this change: brig integration+e2e: 12 failed + 1 error vs baseline 11 failed; the extra two (test_kill_group cooperative-timing, test_wait_ready teardown sweep of PID-1 zombies) fail identically with -I reverted (TASK-0077's zombie class). Egress tests with env -u NO_PROXY: 17 passed. brig unit: 614 passed. bh-02 jail tests (test_python_repl + runner plugin): 15 failed with the fix, the same 15 plus the new test with -I reverted (root + non-reaping PID 1 in this container). scripts/linux-jail-check: docker image build fails at apt-get (the build container has no route to the egress proxy); running as an unprivileged user natively fails too (the venv's interpreter lives under /root). scripts/check: format, lint, types, gates, docs ok; tests step stops at collection on Linux (warden-systray imports darwin-only rumps; TASK-0081). Full pytest with that member ignored: 27 failed, 2132 passed, all failures in the pre-existing sets above.

Review 1 (2026-10-11, a reviewer who did not do the work): criteria 1-3 met with evidence; code fit to close; criterion 4 not verifiable here yet (scripts/linux-jail-check can't build behind this container's TLS proxy, TASK-0082; scripts/check stops at collection on rumps, TASK-0081). Should-fix taken: four docstrings and comments now show the trampoline and proxy argv with -I. The task stays open until criterion 4 is re-run after TASK-0081 and TASK-0082.
<!-- SECTION:NOTES:END -->
