---
id: DRAFT-0019
title: Fix the three tests that fail scripts/check where bubblewrap is installed
status: Draft
assignee: []
created_date: '2026-10-31T04:13:00Z'
labels: []
dependencies: []
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
