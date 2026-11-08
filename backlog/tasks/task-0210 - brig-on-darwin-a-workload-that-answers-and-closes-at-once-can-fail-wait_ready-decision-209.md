---
id: TASK-0210
title: >-
  brig: on darwin a workload that answers and closes at once can fail wait_ready
  (decision-209)
status: Done
assignee:
  - '@claude'
created_date: '2026-11-07 21:52'
updated_date: '2026-11-08 22:38'
labels:
  - brig
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-209 (TASK-0206) measured darwin's LOCAL_PEERPID: once the serving end has closed a connection the read fails with ENOTCONN, and the dial refuses (decision-186), so Process.wait_ready on darwin can raise EndpointRefused for a genuine workload that writes a greeting and closes before the host reads its peer. Linux keeps SO_PEERCRED after the close. Decide whether the readiness dial should treat that case otherwise (a SPEC ruling, owner's call), or document it for embedders. Also: libs/brig/tests/integration/test_channel_reservation_starts.py's _SERVE closes each connection at once, the same latent race TASK-0206 removed from test_channel_planted_link.py.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The darwin behaviour for a server that closes first is ruled in SPEC.md and implemented or documented
- [x] #2 test_channel_reservation_starts.py's serving workload no longer races the host's peer read on darwin
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Order of work: (1) decision-210 is the next free number, all refs swept. (2) Measure on this Mac how often a close-first workload fails wait_ready, for the trade-off. (3) Write the two tests first and see them fail: the serving workload holds a connection, red against the old workload; a server that closes first is refused on darwin through the real kernel read, with a held server as the control, forced by delaying the peer read, red with the dial mutated to treat ENOTCONN otherwise. (4) SPEC.md decision-210 after decision-209: the refusal stands, the workload holds the connection, no dial code change; docstrings and README say it for embedders. (5) Fix the serving workload as TASK-0206 fixed test_channel_planted_link.py. (6) scripts/check libs/brig, scripts/linux-jail-check, one commit. Risk: the ruling is the owner's, so it is marked proposed in the notes with the alternatives. Not done: a retry, a skip or a loosened assertion.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Ruling, decision-210 in libs/brig/SPEC.md: the owner confirmed it on 2026-11-08, as the worker proposed it. A LISTEN workload holds a connection until its peer closes; on darwin a server that closes first stays refused with EndpointRefused, at once, as decision-186 rules. Nothing is handed back or called ready unverified. No code change to the dial; docstrings of Process.wait_ready and Process.connect and the README say it for embedders.

Trade-off: a genuine answer-and-hang-up workload on darwin sees EndpointRefused (the kernel could not report who listens there, Errno 57) from wait_ready or connect when its close beats the host's peer read, and readiness otherwise, so it can pass many times and then fail. It has to change to hold its connections. Linux is unaffected. Measured: real close-first workload through wait_ready on this Mac, 0 refusals of 100 idle and 0 of 100 with every core busy twice over, so the race is rare and the measurement did not reproduce the failure seen in the full scripts/check; that failure is taken from the delegation brief.

Alternatives rejected. (a) Read ENOTCONN as verified or hand the connection back: trusts a peer nobody checked, and a host socket reached through a link swapped after the lstat would count. (b) LOCAL_PEERCRED as a fallback: it reports a uid and groups, not a pid, so it cannot answer whether the peer is in the started process's group; from knowledge of the darwin API, not measured here. (c) Re-dial on ENOTCONN, ready() reading False: the strongest alternative, the owner may prefer it. Each dial stays fully verified and nothing unverified is handed back, and it would spare close-first workloads the random refusal. Rejected because it reverses decision-186's rule that an unreportable peer is a refusal, a workload that always loses the race gets a slow WaitReadyTimeout in place of a prompt named refusal, and a foreign closing server reached through a swapped link would be connected to repeatedly until the timeout in place of once.

Evidence. New test test_the_serving_workload_holds_a_connection_until_the_host_closes_it: seen failing against the old _SERVE (Failed: DID NOT RAISE TimeoutError, the second read got end of file), green after the two-line fix, the same change TASK-0206 made. New test test_a_server_that_closes_first_is_refused_where_the_kernel_loses_its_peer forces the race by holding the host's peer read until the server has closed, through the real kernel read, with a holding server as the control: green on darwin and in the Linux container (Linux takes the branch where the process answers). Seen failing with dial.py planted to hand back the socket on ENOTCONN (Failed: DID NOT RAISE EndpointRefused); restored from a scratch copy, sha256 22209aa7 before and after. test_channel_reservation_starts.py 20 runs on darwin, 0 failed (4 passed, 1 skipped each). scripts/check libs/brig rc=0: 1312 passed, 180 skipped, gates and docs ok. scripts/linux-jail-check default run rc=1: 1 failed, 329 passed, 4 skipped; the failure is test_a_linux_jail_ends_when_the_host_replaces_or_removes_a_secret_it_holds at assert not seen.exists(), the assertion TASK-0211 already tracks, in a test this change does not touch. Rerun alone with both changed brig test files in the container, rc=0, 15 passed. That rerun does not clear the default run; it stays red for TASK-0211. Both changed brig test files are in the default jail-check list, and passed in that run too (its only failure is the one above). Not verified: the full scripts/check, and the original flake cannot be reproduced on demand, so the proof is the held-connection property, not the flake's absence.

Check `scripts/check` exited 0

```text
== format
878 files already formatted
   ok
== lint
All checks passed!
   ok
== types
Success: no issues found in 208 source files
   ok
== tests
bringing up nodes...
bringing up nodes...

........................................................................ [  1%]
.........................................................s...sssss..ssss [  3%]
.s...ss....s................................................sssss.....ss [  5%]
sssss................................................................... [  7%]
........................................................................ [  8%]
........................................................................ [ 10%]
........................................................................ [ 12%]
..................s....................................................s [ 14%]
ss.s.s..s.s..s.ssssss..s..s.s.........s..........sss.................... [ 15%]
........................................................................ [ 17%]
........................................................................ [ 19%]
........................................................................ [ 21%]
...........................................ss........................... [ 22%]
........................................................................ [ 24%]
........................................................................ [ 26%]
.......................................s................................ [ 28%]
........................................................................ [ 29%]
........................................................................ [ 31%]
........................................................................ [ 33%]
........................................................................ [ 35%]
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 47%]
..........................................................s.....ssssssss [ 49%]
sss.sssssssssssssssssssssssss.ssssssssssssss..ssssssssssss.sssssssssssss [ 50%]
ssssssssss...s.............s...............s............................ [ 52%]
........................................................................ [ 54%]
........................sssssssss.ssssssssssssssssssssssssssssssssssssss [ 56%]
ssssssssssssssssssssss.....s........................................ssss [ 57%]
ssssssssssssss.s.........s.............................................. [ 59%]
........................................................................ [ 61%]
........................................................................ [ 63%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
..........................................................s............. [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 98%]
...................................................................      [100%]
3868 passed, 231 skipped in 84.56s (0:01:24)
   ok
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
INFO    -  Documentation built in 1.27 seconds
   ok
== tokens
bh-01's tokens and bh-02's theme are in sync
   ok
```

Review 2026-11-08 (reviewer, at e2c6abb6 and its board-only successors): NOT CLOSED, on instruction: decision-210 waits on the owner. Everything else is met. scripts/check exit 0, 3868 passed, 231 skipped, recorded above; this answers the worker's 'not verified: the full scripts/check'. scripts/linux-jail-check default exit 0, 330 passed, 4 skipped, recorded on TASK-0079.31, so both changed test files passed on Linux. Forcing test checked with no file changed: dial patched in-process to trust ENOTCONN gives 'Failed: DID NOT RAISE EndpointRefused' at test_channel_planted_link.py:390; unpatched, the two files give 12 passed, 2 skipped. AC2: by reading, the old _SERVE closes after answering, so the second recv returns end of file and the new test fails; the worker saw this. AC2's proof is the held-connection property; the original flake was never reproduced (0 of 200). Findings. (medium) SPEC.md says 'Ruled 2026-11-08' and tells decision-209's reader the residual is 'settled', with no mark that it is proposed; AC1 is ticked on that wording. Mark it proposed until the owner confirms, or confirm it. (medium, if confirmed) The refusal a close-first workload gets says 'the kernel could not report who listens there' and that a process of the jail can write the channel directory; it reads as an attack and does not say to hold the connection, which CLAUDE.md asks of an error message. (low) Process.connect's docstring gives OSError as 'nothing listens there yet', and the README says only wait_ready then connect, but a full backlog after wait_ready also refuses (TASK-0215 measured it); only the SPEC says so. (low) The new test reaches dial_module._read_peer and _Peer, private names; the gates pass, and the file's earlier test already patches _read_peer. Before close: this bug needs a repro record, or a note starting 'No repro:'; board-check close reports it. The worker's planted-mutation run and the reviewer's above would be its evidence.

No repro: the original race did not reproduce on demand: a real close-first workload through wait_ready gave 0 refusals in 200 tries on this Mac (100 idle, 100 with every core busy twice over). The evidence is the forced-race test, test_a_server_that_closes_first_is_refused_where_the_kernel_loses_its_peer, seen failing with dial.py planted to hand back the socket on ENOTCONN (Failed: DID NOT RAISE EndpointRefused), and the failure the delegation brief reports from a full check.

Second round, after the owner confirmed decision-210 on 2026-11-08. SPEC.md back to ruled wording at both decision-210 places and the decision-209 cross-reference, and a bullet on the refusal's text. dial.py: a peer read failing ENOTCONN now says the server closed the connection before its peer could be read, so who answered is unverified, and that a LISTEN workload must hold each connection until the host closes it (decision-210), without the channel-directory sentence; other failures keep their wording, and what the dial refuses is unchanged. This replaces the first round's no code change to the dial: the wording is code. Process.connect's docstring and the README say a full backlog also refuses after wait_ready. Seen failing: the forced-race test against the old text (Regex pattern did not match, expected closed the connection), green after. Unit tests cover the ENOTCONN and EINVAL wording on every platform. scripts/check libs/brig rc=0, 1314 passed, 180 skipped, gates and docs ok. scripts/linux-jail-check default rc=0, 330 passed, 4 skipped. No failures this round. Not re-run: the dial.py plant.

Check `scripts/check` exited 0

(32 earlier lines omitted)
```text
........................................................................ [ 35%]
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 47%]
...........................................................s......ssssss [ 49%]
sssssssssssss.ssssssssss.sss.sssssssssssssssssssssssssss..ssssssssssssss [ 50%]
ssssssssss.s...s...s............s....................................... [ 52%]
..................s..................................................... [ 54%]
.......................s..ssssssssssssssssssssssssssssssssssssssssssssss [ 56%]
ssssssssssssssssssss.s...s..s......................................sssss [ 57%]
ssssssssssssss.s........................................................ [ 59%]
........................................................................ [ 61%]
........................................................................ [ 63%]
........................................................................ [ 64%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 71%]
........................................................s............... [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 98%]
.....................................................................    [100%]
3870 passed, 231 skipped in 75.43s (0:01:15)
   ok
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

Review 2026-11-08, second round (reviewer, at 732ee14e): CLOSED. decision-210 confirmed by the owner. AC1 and AC2 met.

Runs. scripts/check full tier via record-check: exit 0, 3870 passed, 231 skipped (the previous review's 3868 plus the two new unit tests), recorded above; no file changed by it. Changed test files, unpatched: 25 passed, 2 skipped. Forcing test with the dial made to trust ENOTCONN in-process, no file changed: 1 failed, 8 deselected, as it should, 'Failed: DID NOT RAISE EndpointRefused' at test_channel_planted_link.py:392, so the test forces the ruling and not only the text. scripts/linux-jail-check default: FAILED, exit 1, 1 failed, 329 passed, 4 skipped, not re-run.

The failure: bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py:755, test_a_linux_jail_ends_when_the_host_replaces_or_removes_a_secret_it_holds, 'assert not seen.exists() and absent.is_dir()', AssertionError, seen exists at /tmp/pytest-of-bh/pytest-0/test_a_linux_jail_ends_when_th0/project/seen. Only the tail of the output was kept (the reviewer's tail -15 cut the rest), so the full traceback is not on record. It matches TASK-0211's description: the same test, assertion and third start under the default run on a Mac host. It is a recurrence of that flake by that match, not a proven cause. The assertion is about a file the jail's program plants, not about the dial's text, and this commit changed only the wording in that path. The worker's run of this check gave 330 passed, 4 skipped.

Prior findings. SPEC settled: handled, ruled wording at decision-210, its implementing line and the decision-209 cross-reference; no 'proposed' left in the SPEC's decision-210 lines. ENOTCONN message: handled, says the server closed first, who answered is unverified, and to hold each connection, citing decision-210. Docs on a full backlog: handled in Process.connect's docstring and the README. Repro: the 'No repro:' note is present, board-check close reports ok. Private names in tests: left as they are, gates pass.

Dial refuses what it refused: yes, by reading. The one raise site now raises what _unread_peer_refusal returns, and both its branches return EndpointRefused; the surrounding close on BaseException is untouched. guidance: only formats the message, read in no control flow, passed only on the ENOTCONN branch. The _peer_refusal path and the path check keep the default. Regression guard: test_a_peer_the_kernel_cannot_report_is_refused_not_waited_out asserts the other wording stays.

Findings, none filed. (low) dial's, host.py's and the runner's connect docstrings still give OSError as 'nothing listens there yet' only; Process.connect, the public one, has the backlog case. (low) A foreign closing server reached through a swapped link now gets the hold-your-connections guidance rather than the channel-directory sentence: still refused and still called unverified, as decision-210 chose. (low) The change to dial.py departs from the first round's 'no code change to the dial'; the notes explain it, and it was what the prior finding asked.
<!-- SECTION:NOTES:END -->
