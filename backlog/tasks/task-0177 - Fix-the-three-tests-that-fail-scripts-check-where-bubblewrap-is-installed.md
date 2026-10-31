---
id: TASK-0177
title: Fix the three tests that fail scripts/check where bubblewrap is installed
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-31T04:13:00Z'
updated_date: '2026-10-31T14:55:00Z'
labels: []
dependencies: []
modified_files:
  - bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py
  - bh-02/app/tests/test_real_launch.py
  - conftest.py
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
With bubblewrap installed, scripts/check fails on three tests (seen in the TASK-0176.06 review at 8d5b98f; none of them, nor what they read, is in that commit's diff from c0a7d48): test_real_launch.py::test_a_keyed_model_s_key_never_reaches_an_input_s_environment and test_agents_wiring.py::test_a_child_s_python_runs_in_a_jail_of_its_own_under_the_confined_runner (the model row stays inactive; test_real_launch.py:963 still writes env_file, which TASK-0169.04 retired), and test_xdist_groups.py::test_every_test_file_that_starts_a_jail_is_in_a_group (test_host_values.py starts a jail in no xdist group, per the TASK-0176.06 worker). They block every task whose criteria say scripts/check passes, TASK-0176.06 first.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 scripts/check passes on a machine with bubblewrap installed
- [ ] #2 No test config passes env_file
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. test_agents_wiring.py's fake `host` (`_Host`) gains `key_envs` and `models_file`, as the runner's own test fakes have them: the runner row's contract asks for both since TASK-0169.05, and without them it fails with `ContractViolation('runner: host is bound to a _Host, which is missing key_envs, models_file')`, which leaves loop, approval and python inactive.
2. test_real_launch.py's keyed-model test: the key moves from the retired `env_file` to `key = { cmd = "printf fake-verify-key" }` on the models file's endpoint. `cmd` is the source whose key bh-02 holds itself and puts in no environment, which is what the test is about. `{ env = ... }` would not do: under `--no-jail` a key in bh-02's environment reaches an input by design (TASK-0169 #7).
3. conftest.py's `jail-lock` group names bh-02/app/tests/test_host_values.py, with the reason in `why`: it boots `runner:confined` and expects a refusal before any jail starts, and if that refusal regressed its jail would take the lock.
4. The three tests, then the whole scripts/check, on this host with bubblewrap installed.

### Risks
The real-launch test's stub must still see `Bearer fake-verify-key`: the command's output is the key, with no trailing newline (`printf`).

### Proof
The three node ids pass; scripts/check passes; `git grep env_file -- '*.py'` finds nothing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-10-31 by Claude on the owner's instruction ("Both": fix these alongside brig's TASK-0019), as size-2.

Check `scripts/check` exited 0

(53 earlier lines omitted)
```text
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
........................................................................ [ 83%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 98%]
..........................................                               [100%]
3958 passed, 118 skipped in 196.20s (0:03:16)
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
INFO    -  Documentation built in 4.60 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Repro at 907f9398c5b2, test files: bh-02/app/tests/test_real_launch.py, bh-02/app/tests/test_xdist_groups.py, bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py; command: `uv run pytest -q -p no:randomly -p no:cacheprovider bh-02/app/tests/test_real_launch.py::test_a_keyed_model_s_key_never_reaches_an_input_s_environment bh-02/app/tests/test_xdist_groups.py::test_every_test_file_that_starts_a_jail_is_in_a_group bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_a_child_s_python_runs_in_a_jail_of_its_own_under_the_confined_runner` exited 1

(161 earlier lines omitted)
```text
E        +  where False = all(<generator object _booted.<locals>.<genexpr> at 0x7f81ca2b35a0>)

bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py:317: AssertionError
=========================== short test summary info ============================
FAILED bh-02/app/tests/test_real_launch.py::test_a_keyed_model_s_key_never_reaches_an_input_s_environment
FAILED bh-02/app/tests/test_xdist_groups.py::test_every_test_file_that_starts_a_jail_is_in_a_group
FAILED bh-02/plugins/subagents-cordis-plugin/tests/test_agents_wiring.py::test_a_child_s_python_runs_in_a_jail_of_its_own_under_the_confined_runner
3 failed in 3.59s
```

Worker's report (Claude, 2026-10-31).

Root causes (the failing repro above is the three node ids with these fixes stashed):
- test_agents_wiring.py: the runner row failed its contract, `ContractViolation('runner: host is bound to a _Host, which is missing key_envs, models_file')`, which left loop, approval and python inactive. The fake `host` predates TASK-0169.05; it gains `key_envs` (empty) and `models_file` (""), as the runner's own test fakes have them.
- test_real_launch.py: the keyed-model test still passed the retired `env_file`. The key now comes from `key = { cmd = "printf fake-verify-key" }`, the source bh-02 holds itself and sets in no environment, so the property tested is the same; the docstring says why `{ env = ... }` would not be (under `--no-jail` it reaches an input by design). The stub still sees exactly `Bearer fake-verify-key`.
- test_xdist_groups.py: test_host_values.py boots `runner:confined` (expecting a refusal before any jail starts) and was in no group. It joins `jail-lock`, with that reason in the group's `why`.

After: the three pass, and `scripts/check` passes on this host with bubblewrap installed (3958 passed, 118 skipped, recorded above). `git grep env_file -- '*.py'` finds only the old brig's Docker `--env-file` code (libs/brig, removed in TASK-0176.08), no model config.
<!-- SECTION:NOTES:END -->
