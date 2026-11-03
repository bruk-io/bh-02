---
id: TASK-0179
title: >-
  The runner hands its owners the program's endpoint, instead of each owner
  choosing one
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-02T17:24:00Z'
updated_date: '2026-11-03T03:14:00Z'
labels:
  - runner
  - size-3
dependencies:
  - TASK-0178
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the architecture review of the bh-02/brig seam, 2026-11-02 (TASK-0176). Today the owners choose the program's socket path in their own directories (python_cordis_plugin.client, extensions_cordis_plugin.host) and pass it to runner.start(argv, cwd, endpoint). The new brig reserves the endpoint itself (reserve_channels) before the jail starts, so the runner must hand it to the owner before the owner builds argv. That changes CONTRACTS.md's runner shape, both owners, Unjailed and extensions_cordis_plugin.testing: the swap is not the adapter alone, as decision-0011 says. Landing the contract change first, against the old brig (a callable argv_for(endpoint), or a reserve-then-start pair), keeps the swap's diff to the adapter. Decision-0005 in the new brig makes readiness a property of one connection, so the owners' own re-dial is unverified; ask brig to hand back the verified connection (or a verifying connect) as part of this.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 runner.start's contract gives the owner its endpoint rather than taking one, in CONTRACTS.md and in every implementation and fake
- [ ] #2 scripts/check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-11-03 under the owner's goal (see TASK-0178). Blocked on TASK-0178 (same files).

Shape chosen: one call, start(argv_for, *, cwd) -> started with started.endpoint. Both owners have one pattern (build argv from the socket, start, dial), so a reserve-then-start pair would add a reservation that can leak between its two calls and a second place the owner must clean up; with one call the runner owns the path's whole life (it is made before argv_for runs, removed by started.stop() or by a failed start). The mechanism chooses the path (runner.reserved_endpoint: mkdtemp bh-s- under /tmp, k.sock, same short /tmp directory the owners used, still a write root of the policy); the new brig will choose it inside the adapter with no contract change. Files: runner.py (Mechanism, Runner.start, Started.endpoint, reserved_endpoint/unreserve_endpoint), jail.py (BrigJail/_Jailed), unconfined.py (Unjailed/_Process), python client.py, extensions host.py and testing.py (PlainJail), CONTRACTS.md, runner and python READMEs, root pyproject (two no-impure-functions entries: the mkdtemp/rmtree moved from the owners, whose methods were already budgeted). Owners no longer make or remove a socket directory. The owners' re-dial after start is unchanged (open_unix_connection(started.endpoint)); brig-verified connection (the task description's ask) is TASK-0079.31's, not done here. Old signature removed everywhere (no compat); all test fakes and ~50 test call sites migrated. Proof: new tests test_the_python_process_builds_its_command_from_the_endpoint_the_runner_chose_and_dials_it, test_the_extensions_dial_the_endpoint_the_runner_chose_for_their_worker, test_the_runner_hands_the_command_the_endpoint_it_started_the_program_on, test_an_unconfined_start_chooses_a_short_socket_in_a_directory_of_its_own_and_stop_removes_it (seen failing with the Unjailed stop's cleanup removed, passing restored). scripts/check run per member: runner (full, with gates and docs), python, extensions, app (no gates/docs) all pass; arch-check --no-fix ok. Linux bwrap jail tests ran here and pass. AC2 (scripts/check) left unticked for the reviewer.
<!-- SECTION:NOTES:END -->
