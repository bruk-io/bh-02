---
id: TASK-0150
title: >-
  A reused jail_dir's stale proxy.port points a new jail's workload at a dead or
  foreign port
status: Done
assignee:
  - '@claude'
created_date: '2026-10-18 12:55'
updated_date: '2026-10-18 22:42'
labels:
  - brig
  - size-3
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while fixing TASK-0140. connect_proxy's wrap (libs/brig/src/brig/mech/connect_proxy.py, _render_wait_script) waits with [ ! -s <jail_dir>/proxy.port ], reads the port and exports HTTP_PROXY/HTTPS_PROXY. The proxy publishes that file (os.replace after listen) only when its Python process has started, tens of milliseconds after the workload's shell may already be running. A jail_dir that still holds the proxy.port of an earlier jail (a supported flow: decision-181, make_channel_dir keeps an earlier jail's directory, clear_earlier_records clears only procs/) makes the wrap return at once with the OLD port. The workload is then pointed at a port nobody listens on (ConnectionRefusedError, measured: a planted stale file failed the 403 integration test 11 of 12 runs) or, worse, at whatever listens there now, which would receive its proxied requests. The cooperative grade does not excuse sending a jail's traffic to a foreign listener. TASK-0140 fixed the one test by giving it a fresh directory; the library is unchanged. A fix changes behaviour, so it starts as a SPEC.md decision (libs/brig/WORKFLOW.md). Options to rule on: the runtime removes a helper's declared ready file before it spawns the helper (Helper gains the path it publishes); or the runtime starts the proxy with its existing --ready-fd and waits for it, then passes the port on; or the wrap checks the file it reads came from this launch.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A SPEC.md decision paragraph rules how a new jail never reads an earlier jail's proxy.port, naming this task and ending (Ruled YYYY-MM-DD, decision-N.)
- [x] #2 A test plants a proxy.port naming a closed port in the jail_dir before Jail.create and shows the workload still gets the proxy's own 403 for a host outside the allow list; it is seen failing before the change and passing after
- [x] #3 scripts/check libs/brig passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Plant first: add an integration test to libs/brig/tests/integration/test_connect_proxy_launch.py that writes a proxy.port naming a closed port into the jail_dir BEFORE Jail.create, then runs the existing fetch-from-a-denied-host workload and requires the proxy's own 403 (DENIAL_PREFIX in the body, not ConnectionRefusedError). Run it on the unchanged code, repeated, and see it fail (the task measured 11 of 12). 2. SPEC.md decision-204 (next free in libs/brig; decision-0008 reserves 204 onward for new rulings): rule option 1, the runtime removes a helper's declared ready file before it spawns the helper; Helper gains ready_path; why it beats --ready-fd (the port is wanted by a compile-time-pure wrap, a handshake would need a new run-time env channel) and a provenance check (a check can be wrong, a file that does not exist cannot be read). Names TASK-0150, ends (Ruled 2026-10-18, decision-204.). 3. Code: Helper.ready_path: str | None = None in mech/contract.py; connect_proxy declares ready_path=port_path; run/host.py _start_helpers removes it (FileNotFoundError ignored, any other OSError propagates with a note) before the spawn. 4. Tests: the planted-stale-port integration test above (seen failing, then passing); a unit test that connect_proxy's helper declares the port file as ready_path; an integration test in test_helpers.py that a generic helper's stale ready file is gone after create. 5. Prove: pytest the touched files, repeated runs of the planted test, scripts/check libs/brig, scripts/arch-check --no-fix. Risks: Helper is a frozen slots dataclass built positionally in oci tests (Helper('h', ('true',), JAIL_LIFETIME)), so the new field goes last with a default; docs quoting SPEC sentences moved by the edit (grep before commit).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Ruling: libs/brig/SPEC.md section 6, decision-204 (2026-10-18), option 1: Helper gains ready_path; HostRuntime.create removes every helper's declared ready file before it starts any helper (_remove_ready_files in run/host.py; FileNotFoundError ignored, a link removed not followed, any other OSError propagates with a note before anything is started). connect_proxy declares its port file. Chosen over the --ready-fd handshake (the port is wanted by a wrap rendered once by a pure compile(), so it would need a new run-time env channel, and create would block on every helper) and over a provenance check (mtime, pid or token comparisons are new ways to be wrong in the wrap that runs before every workload and fail open to the stale port; a file that does not exist cannot be read). decision-204 is the next free number in libs/brig (highest was 203; decision-0008 reserves 204 onward for new rulings). Code: mech/contract.py (Helper.ready_path, absolute-path guard), mech/connect_proxy.py, run/host.py. Tests: integration/test_connect_proxy_launch.py::test_a_port_file_an_earlier_jail_left_is_not_the_port_the_workload_is_pointed_at (plants proxy.port naming a closed port before Jail.create, with controls: port refused, file present at create, file replaced by the proxy's after); integration/test_helpers.py (stale ready file gone at the helper's own start for JAIL_LIFETIME and LAUNCH_SCOPED, neighbour kept, helper's own publish survives; an unremovable ready path refuses create with no helper started, with a same-test control); unit tests for the field and for connect_proxy declaring the port file. Evidence, AC2 seen failing: on the unchanged code the planted test failed 6 of 6 runs with the workload seeing URLError(ConnectionRefusedError(111)) instead of the proxy's 403; with the fix it passed 8 of 8 reruns of test_connect_proxy_launch.py. Mutation checks (scratch copy plus sha256, restored, hashes match): removing the _remove_ready_files call fails the planted test and 3 test_helpers cases; removing ready_path=port_path from connect_proxy fails the planted test and the unit test. The integration tests run in this container (bwrap present, uid 0; these tests use HostRuntime and no bwrap). AC3: scripts/check libs/brig exit 0 (format, lint, mypy strict, 1360 passed 111 skipped, gates all ok, docs ok; tokens skipped, no bh-01). Not covered, filed: TASK-0164 (proxy-decisions.jsonl is appended across a reused jail_dir and the egress reader folds an earlier jail's lines in). The full scripts/check was not run.

Check `scripts/check` exited 0

(32 earlier lines omitted)
```text
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 37%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 46%]
......................................................s..ss.....ss.s.s.s [ 48%]
.s..ss...sss.s.s...sssss.s.s.ssss...........s........................... [ 50%]
........................................................................ [ 52%]
........................................................................ [ 54%]
...................sssssssssssssssssssssssssssssssssssssssssssssssssssss [ 55%]
ssssssssssssss...............................ssssssssss...........s..... [ 57%]
.....s...................................................s.............. [ 59%]
........................................................................ [ 61%]
...................................................................ss.s. [ 63%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 99%]
......................................                                   [100%]
3882 passed, 118 skipped in 209.56s (0:03:29)
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
INFO    -  Documentation built in 4.20 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review (not closed): every AC is met and the full scripts/check exits 0, but close-task refuses a bug with no repro recorded. The repro (test_a_port_file_an_earlier_jail_left_is_not_the_port_the_workload_is_pointed_at) passes on HEAD, so record-check --repro cannot record it now; the worker's 6/6 failure before the fix is in the notes but was never recorded through record-check --repro. To close: the worker records the repro against the pre-fix code (e.g. a worktree at c57b8169 with the test applied), or the owner rules a 'No repro:' note acceptable. No code findings.

Repro at b4812b1f5959, test files: libs/brig/tests/integration/test_connect_proxy_launch.py; command: `uv run pytest libs/brig/tests/integration/test_connect_proxy_launch.py::test_a_port_file_an_earlier_jail_left_is_not_the_port_the_workload_is_pointed_at -q` exited 1

(26 earlier lines omitted)
```text
        planted = os.path.join(jail_dir, PORT_FILE)
        with open(planted, "w") as fh:
            fh.write(str(stale))
        with pytest.raises(ConnectionRefusedError):
            socket.create_connection(("127.0.0.1", stale), timeout=5).close()
        assert _read_nonempty(planted) == str(stale), "the stale port file was not planted"
    
        out = os.path.join(jail_dir, "got")
        jail, process = _run(
            jail_dir,
            ("localhost",),
            _outcome_script(f"http://127.0.0.1:{origin.port}/x", out),
            run_id,
        )
        try:
            seen = _wait_file(out)
            assert seen is not None, "the workload neither succeeded nor failed"
>           assert seen.startswith("HTTP 403: "), (
                f"the workload did not get a 403 from the proxy; it saw {seen!r} -- "
                f"it was pointed at the stale port {stale} the earlier jail left"
            )
E           AssertionError: the workload did not get a 403 from the proxy; it saw "ERROR URLError(ConnectionRefusedError(111, 'Connection refused'))" -- it was pointed at the stale port 44641 the earlier jail left
E           assert False
E            +  where False = <built-in method startswith of str object at 0x7ff60e8e47a0>('HTTP 403: ')
E            +    where <built-in method startswith of str object at 0x7ff60e8e47a0> = "ERROR URLError(ConnectionRefusedError(111, 'Connection refused'))".startswith

libs/brig/tests/integration/test_connect_proxy_launch.py:354: AssertionError
=========================== short test summary info ============================
FAILED libs/brig/tests/integration/test_connect_proxy_launch.py::test_a_port_file_an_earlier_jail_left_is_not_the_port_the_workload_is_pointed_at
1 failed in 0.55s
```

Round 2 (review finding: a bug closes with a recorded repro). No code changed; the finding was that the repro was never recorded with record-check --repro, and it cannot be recorded on HEAD because the test passes there. Recorded it against the code before the fix instead: a scratch git worktree at c57b8169 (the commit before the fix; brig imported from that worktree's own venv, uv sync --all-packages --offline, and I confirmed brig there has no ready_path), with only libs/brig/tests/integration/test_connect_proxy_launch.py taken from the branch HEAD (4c34d65) and committed there as b4812b1f5959 (parent c57b8169; git diff --quiet 4c34d65 b4812b1f5959 -- that file exits 0, so the recorded file is byte-identical to the one on this branch). Ran: python3 <philosophy>/scripts/record-check TASK-0150 --repro --root /home/user/bh-02 -- uv run pytest libs/brig/tests/integration/test_connect_proxy_launch.py::test_a_port_file_an_earlier_jail_left_is_not_the_port_the_workload_is_pointed_at -q. It failed as the bug says (the workload saw URLError(ConnectionRefusedError(111)) instead of the proxy's 403, pointed at the planted stale port), record-check exited 0 and the 'Repro at b4812b1f5959, test files: ...' note above is its record. Repeat runs on the same pre-fix worktree: 8 runs in all, 7 failed with ConnectionRefusedError(111), 1 passed (the race the task describes: when the proxy publishes before the wrap reads, the stale file is not read in time to matter), so the earlier note's '6 of 6' was the sample then, 7 of 8 is the sample now. Evidence this clears the finding: python3 <philosophy>/scripts/board-check close TASK-0150 prints 'ok: TASK-0150 can close' and exits 0, run after the scratch worktree was removed (git worktree remove, prune; git worktree list shows only the main checkout), so it does not depend on the worktree. The repro commit b4812b1f5959 is no longer on any branch (it was made in the scratch worktree and the branch history here is squashed to one commit), it is a loose object in this repository's .git; close-task's check (git diff --quiet b4812b1f5959 -- the test file) needs that object to still exist, so close before a git gc --prune would drop it. Nothing else was changed: the SPEC.md decision-204, the code and the tests are as the reviewer found them (the reviewer's full scripts/check, exit 0, is recorded above), so scripts/check was not re-run for this round. AC1-3 stay ticked on the evidence above and in round 1.

Check `scripts/check` exited 0

(32 earlier lines omitted)
```text
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 37%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 46%]
.......................................................s......sss...ssss [ 48%]
..ss.s...sss..ss.s.s.s..s..s.ssss.s........s............................ [ 50%]
........................................................................ [ 52%]
...............s........................................................ [ 54%]
...................sssssssssssssssssssssssssssssssssssssssssssssssssssss [ 55%]
ssssssssssssss..............................sssssssssss...s............. [ 57%]
........................................................................ [ 59%]
....................................s................................... [ 61%]
.......................................................................s [ 63%]
s....s.................................................................. [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 99%]
......................................                                   [100%]
3882 passed, 118 skipped in 205.11s (0:03:25)
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
INFO    -  Documentation built in 4.11 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```

Review round 2: closed. The full scripts/check exits 0 again (recorded); code unchanged since round 1, which found no code findings. The round-1 blocker (no recorded repro) is cleared: the repro is recorded at b4812b1f5959 (pre-fix code plus the byte-identical test), failing with ConnectionRefusedError(111) as the bug describes, and board-check close reports ok. AC1-3 met. Follow-up already filed by the worker: TASK-0164.
<!-- SECTION:NOTES:END -->
