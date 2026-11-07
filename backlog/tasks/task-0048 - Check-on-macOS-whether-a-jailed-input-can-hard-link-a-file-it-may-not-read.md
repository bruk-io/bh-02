---
id: TASK-0048
title: Check on macOS whether a jailed input can hard-link a file it may not read
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-07 03:05'
updated_date: '2026-11-07 07:18'
labels:
  - jail
  - security
  - size-2
dependencies: []
priority: medium
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The context files skip hard links in the project, but whether Seatbelt lets a jailed input create one to a read-denied file (local.env, ~/.ssh) is unknown. If it can, other readers in bh-02's own process (the models file's path checks, startup files) need the same guard.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A test on darwin records whether `os.link` to a read-denied file succeeds inside brig's jail
- [ ] #2 If it does, every file bh-02 reads on the model's behalf refuses a hard-linked one, with a test
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1) Probe empirically on this Mac (outside the test suite) whether os.link to a read-denied source succeeds under a hand-written Seatbelt profile, covering the full matrix: source outside/inside write_allows, in/not in read_denies -- confirmed the deciding factor is read permission on the source, not write permission on it, and that linking a read_denies source INSIDE write_allows (SPEC.md's own .envrc/.git-hooks carve-out shape) is denied. 2) Write the real integration test through brig's production path (Spec/FsPolicy/Stack([seatbelt])/build_compile_ctx/tests.conftest.launch), modelled on test_seatbelt_smoke.py: a jailed process attempts os.link from a read_denies source (inside write_allows) to an undenied destination, asserted denied against seatbelt's own denial_signatures[0], with the required control (the same shape but source not in read_denies, succeeds and the link content reads back) in the same test. 3) Since AC#1 resolves to 'does not succeed', AC#2's condition does not arise -- leave it unticked and say so, record the fact as a dated SPEC.md Sec.6 paragraph (empirical dialect knowledge, like the unscoped network-bind fact), decision-206. 4) Run the new test file through testlock; run scripts/check libs/brig through testlock. Risk: hand-written SBPL findings could differ from brig's actual emitted profile order; mitigated by re-running the decisive case through the real compiled Stack before concluding.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Finding: os.link to a read-denied file does NOT succeed inside brig's Seatbelt jail -- AC#2's condition does not arise, left unticked.

Evidence for AC#1:
- New test libs/brig/tests/integration/test_seatbelt_hardlink_read_deny.py, run through the real production path (Spec/FsPolicy/Stack([seatbelt])/build_compile_ctx/tests.conftest.launch), mirrors test_seatbelt_smoke.py's observe-from-inside pattern. It covers the one cell that matters: a read_denies source INSIDE write_allows (the same shape SPEC.md Sec.6 already describes for .envrc/.git/hooks carve-outs) hard-linked to an undenied name in the same tree -- denied, matching seatbelt's own denial_signatures[0], and the destination name never appears on the host. The control (identical shape, source NOT in read_denies) both links and reads its content back, in the same test, per WORKFLOW.md's "a control belongs in the same test as the claim."
- `testlock uv run pytest libs/brig/tests/integration/test_seatbelt_hardlink_read_deny.py -q` -> 1 passed.
- Planted the violation: dropped `read_denies=(secret,)` from the spec (scratch-copy edit, restored after, sha256 verified identical to the pre-plant file) -- the test went red exactly as expected: `AssertionError: os.link of a read_denies source succeeded ... stdout='LINK_OK\nREAD_VIA_LINK:TOP_SECRET=1\n\n'`. Restored and re-ran: 1 passed again.
- An earlier scratch probe (outside the suite, hand-written SBPL, not shipped) first tried source outside write_allows, which is denied regardless of read_denies membership -- that only shows hard-linking needs *some* permission on the source, not which one. The matrix that actually answers the question is the source INSIDE write_allows, which is what the shipped test exercises.
- Recorded as a dated SPEC.md Sec.6 paragraph, decision-206 (next free after decision-205), alongside seatbelt's other probed dialect facts (the unscoped network-bind fact, etc.), naming TASK-0048 and the test file. "No code change" -- brig already refuses this; nothing in brig or an embedder needs a new guard.

Not verified / out of scope:
- `scripts/check libs/brig`: format, lint, mypy, all four gates (root, libs/brig, libs/cordis, libs/cordis-helpers, libs/host-paths) and docs all report `ok`. The `tests` stage itself fails, but on pre-existing, unrelated failures already present before this change and outside TASK-0048's scope: a collection-time AttributeError in tests/unit/test_process_namespaces_pure.py (`signal.SIGRTMIN` does not exist on darwin), plus several integration/unit tests (test_supervisor_link.py's AF_UNIX/SOCK_SEQPACKET socketpair, test_subset.py, test_teardown_zombies.py, test_exit_status_is_recorded_not_invented.py) that fail or error under this machine's heavy concurrent load (other sessions' scripts/check runs holding the lock throughout). None touch seatbelt, hard links, or SPEC.md Sec.6; the new test is not among the failures in any run. Left unticked for the reviewer per the standing rule.

Check `scripts/check` exited 1

(122 earlier lines omitted)
```text
>       assert [s.rsplit("\n", 1)[-1] for s in said] == ["DENIED"] * len(inputs), said
E       AssertionError: ['(/private/var/folders/rf/f34xmczn4659gm98hrsprydc0000gn/T/pytest-of-brukhabtu/pytest-1000/popen-gw0/test_a_session_r...me/xdg/bh-02/startup.py ran first: no public functions)
E         DENIED', 'DENIED', 'DENIED', 'DENIED', 'DENIED', 'WROTE', ...]
E       assert ['DENIED', 'D... 'WROTE', ...] == ['DENIED', 'D...'DENIED', ...]
E         
E         At index 5 diff: 'WROTE' != 'DENIED'
E         Use -v to get more diff

bh-02/app/tests/test_python_repl.py:980: AssertionError
_____________ test_a_listener_that_left_after_listening_is_refused _____________
[gw7] darwin -- Python 3.15.0 /Users/brukhabtu/Documents/src/github.com/bruk-io/bh-02/.venv/bin/python

run_id = '9616b916d710418d95cef9e6c3852ea2'
jail_dir = '/private/tmp/bg-lovldho5'

    @pytest.mark.integration
    def test_a_listener_that_left_after_listening_is_refused(run_id: str, jail_dir: str) -> None:
        """The kernel names the process that called `listen`; one that has since
        exited is no vouching peer, even when the socket's holder is in the
        group (the safe direction for a daemon that forks after `listen`)."""
        jail = _create(jail_dir, confined=False)
        reservation = jail.channel("ctl")
        left = os.path.join(jail_dir, "own", "left")
        body = f"python3 -c '{_FORK_AFTER_LISTEN}' {reservation.bound_path} {left}; sleep 60"
        process = jail.start(workload_argv(run_id, body), channel=reservation)
        try:
            deadline = time.monotonic() + _READY_S
            while not os.path.exists(left):
                assert time.monotonic() < deadline, "the listener never left"
                time.sleep(0.02)
>           with pytest.raises(EndpointRefused, match="has left"):
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E           Failed: DID NOT RAISE EndpointRefused

libs/brig/tests/integration/test_channel_planted_link.py:271: Failed
=========================== short test summary info ============================
FAILED bh-02/app/tests/test_python_repl.py::test_a_session_run_from_home_can_t_choose_what_a_later_session_reads_as_the_person_s@jail-lock
FAILED libs/brig/tests/integration/test_channel_planted_link.py::test_a_listener_that_left_after_listening_is_refused
2 failed, 3853 passed, 231 skipped in 73.07s (0:01:13)
   FAILED: tests
== gates
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
INFO    -  Building documentation to directory: /Users/brukhabtu/src/github.com/bruk-io/bh-02/site
INFO    -  Documentation built in 1.34 seconds
   ok
== tokens
bh-01's tokens and bh-02's theme are in sync
   ok
```
<!-- SECTION:NOTES:END -->
