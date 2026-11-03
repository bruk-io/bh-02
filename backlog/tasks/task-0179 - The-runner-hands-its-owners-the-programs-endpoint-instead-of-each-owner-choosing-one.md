---
id: TASK-0179
title: >-
  The runner hands its owners the program's endpoint, instead of each owner
  choosing one
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-02T17:24:00Z'
updated_date: '2026-11-03T03:39:00Z'
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

Check `scripts/check` exited 1

(72 earlier lines omitted)
```text
________ test_a_keyed_model_s_key_never_reaches_an_input_s_environment _________
[gw3] linux -- Python 3.15.0 /home/user/bh-02/.venv/bin/python3

tmp_path = PosixPath('/tmp/pytest-of-root/pytest-130/popen-gw3/test_a_keyed_model_s_key_never0')

    def test_a_keyed_model_s_key_never_reaches_an_input_s_environment(tmp_path: Path) -> None:
        """A key a command prints (`key = { cmd = ... }`) goes only into its requests' Authorization
        header: bh-02 holds it and sets it in no environment, so an unjailed input (whose environment
        is scrubbed of Claude's names alone) does not find it. A key read from bh-02's environment
        (`{ env = ... }`) would be there under `--no-jail`, by design (the jail docs say so)."""
        work, state, config = tmp_path / "work", tmp_path / "state", tmp_path / "config"
        work.mkdir()
        pin = tmp_path / "keyed.toml"
        pin.write_text('[[plugin]]\nid = "model"\nconfig = { default = "k/keyed" }\n')
        with StubServer(key="fake-verify-key") as stub:
            keyed = f'[k]\nprovider = "openai"\nbase_url = "{stub.base_url}"\n'
            keyed += 'key = { cmd = "printf fake-verify-key" }\n'
            keyed += '[k.models.keyed]\nid = "stub-1"\n'
            _models_file(config, keyed)
            app = Launched(["--no-jail", "--patch", str(pin)], work, state, config=config)
            try:
                ready = app.wait_for(_READY, 60)
                app.wait_for("model: k/keyed", after=0)
                app.type(
                    'call import os; print("VERIFY_STUB_KEY" in os.environ, "fake-verify-key" in str(os.environ))'
                )
                app.wait_for("Run this python code", 10, after=ready)
                app.answer(b"y")
                app.wait_for("the input said: False False", 20, after=ready)
                app.press(b"\x11")
>               assert app.exit_code() == 0
E               assert 1 == 0
E                +  where 1 = exit_code()
E                +    where exit_code = <bh-02.app.tests.test_real_launch.Launched object at 0x7fb8a42024e0>.exit_code

bh-02/app/tests/test_real_launch.py:980: AssertionError
=========================== short test summary info ============================
FAILED bh-02/app/tests/test_real_launch.py::test_a_keyed_model_s_key_never_reaches_an_input_s_environment
1 failed, 3964 passed, 118 skipped in 262.43s (0:04:22)
   FAILED: tests
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
INFO    -  Documentation built in 5.22 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review (reviewer, 2026-11-03): NOT CLOSED. AC #2 unmet: full scripts/check exited 1 (recorded above): bh-02/app/tests/test_real_launch.py::test_a_keyed_model_s_key_never_reaches_an_input_s_environment, a --no-jail real launch whose quit exited 1 instead of 0; 3964 passed; gates and docs ok; no files reformatted. The test passes 3/3 alone, so it fails under parallel load; whether it is a pre-existing flake or the Unjailed stop/unreserve change (that path is exactly what this commit changed) is unshown, and either way check is not green. Needed: a green full check, and the failure explained (reproduce under -n auto on 1e0b11b^ vs 1e0b11b, or read the app's stderr on that exit). AC #1 met on reading: no start(argv, cwd, endpoint) form, adapter or fallback remains (remaining endpoint= are spec_for/compile policy calls); runner owns the socket dir (reserved after the refusals stack_for/bwrap/lock, before argv_for; removed on stop and in the failed-start except in BrigJail and Unjailed); /tmp/bh-s-XXXXXXXX/k.sock ~26 bytes; spec_for still allows only dirname(endpoint). Brig-verified connection left out and said so honestly (TASK-0079.31). Minor, no task: PlainJail (extensions testing fake) leaves its bh-t- dir when its readiness wait times out or the worker exits (no stop on that raise); BrigJail reserves the endpoint before os.pipe outside the try, so a pipe failure leaks it (same as jail_dir before).

Check `scripts/check` exited 0

(63 earlier lines omitted)
```text
........................................................................ [ 88%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 98%]
.................................................                        [100%]
3965 passed, 118 skipped in 248.98s (0:04:08)
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
INFO    -  Documentation built in 5.73 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
