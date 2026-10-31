---
id: TASK-0177
title: Fix the three tests that fail scripts/check where bubblewrap is installed
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-31T04:13:00Z'
updated_date: '2026-10-31T14:50:00Z'
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
<!-- SECTION:NOTES:END -->
