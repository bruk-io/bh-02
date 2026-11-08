---
id: TASK-0210
title: >-
  brig: on darwin a workload that answers and closes at once can fail wait_ready
  (decision-209)
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-07 21:52'
updated_date: '2026-11-08 20:43'
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
Ruling, decision-210 in libs/brig/SPEC.md: Proposed by the worker, for the owner to confirm. A LISTEN workload holds a connection until its peer closes; on darwin a server that closes first stays refused with EndpointRefused, at once, as decision-186 rules. Nothing is handed back or called ready unverified. No code change to the dial; docstrings of Process.wait_ready and Process.connect and the README say it for embedders.

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
<!-- SECTION:NOTES:END -->
