---
id: TASK-0206
title: Two tests fail now and then in a full scripts/check on darwin
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-07 04:50'
updated_date: '2026-11-07 22:30'
labels:
  - tests
  - darwin
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Seen in TASK-0202's three scripts/check runs on a 28-core Mac at -n 8 (2026-11-06), each in one run of three: bh-02/plugins/tui-cordis-plugin/tests/test_tui_working.py::test_at_the_real_clock_and_interval_it_appears_after_a_second_and_counts ('Working · 2s' not seen within 3.0 s, line 320; also failed in an earlier -n 8 run) and libs/brig/tests/integration/test_channel_planted_link.py::test_a_listener_that_left_after_listening_is_refused (DID NOT RAISE EndpointRefused). Both look timing- or load-dependent; neither is retried away.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each failure is explained (load, a race in the code, or a test premise) and fixed, seen failing before the fix where the cause can be planted
- [ ] #2 Each passes in three scripts/check runs in a row
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. brig: darwin LOCAL_PEERPID names the connection's peer (the accepting process once something accepted) and fails ENOTCONN once that peer closed (probe in scratchpad). Fix the two tests' premises, not the dial: the forking child holds the socket and never accepts; the serving workload holds each connection until the client closes. 2. SPEC.md decision-208 (no code change): darwin's verified semantics and residuals; correct the unverified sentence; grep for quoters. 3. TUI: Textual's skipping timer can jump 1s to 3s under load; the test waits for a count larger than the first instead of the exact 2s frame. 4. Proof: plants (drop the has-left clause; block the loop 1.5s in the TUI test) seen red; 20 runs on darwin and Linux green; scripts/check per member. AC2 left to the reviewer.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner stand-in (Opus), 2026-11-07: TASK-0198's review hit the brig half of this again (2 of 3 standalone runs of test_channel_planted_link.py on darwin), and TASK-0198 was let close with this bug carrying it. Two failure modes are now on record. (a) 'DID NOT RAISE EndpointRefused': wait_ready accepted a listener that had left. That is the unsafe direction for the dial's peer check (brig/run/dial.py, darwin LOCAL_PEERPID), so treat it as a possible jail-guarantee bug, not as load noise, until it is explained. (b) A refusal with the wrong reason: '[Errno 57] Socket is not connected' from LOCAL_PEERPID instead of 'has left'. That is safe, but the test does not pin it. TASK-0079.31 relies on this dial. DRAFT-0021 reports the same failure and should be folded into this task, not promoted on its own.

Owner stand-in (Opus), 2026-11-06: TASK-0198 will not fix this test; it is this task's alone. A lead from TASK-0198's worker, not yet confirmed: in libs/brig/src/brig/run/dial.py (around lines 153-178), the darwin branch of _read_peer reads LOCAL_PEERPID and sets left=False unconditionally. The Linux branch checks pidfd liveness before and after it reads the group. That asymmetry is the likely cause of mode (a), 'DID NOT RAISE'. Fixing it changes the peer check, so it needs a SPEC.md decision first. Mode (b) should be pinned by the same fix: the test should state which refusal reason darwin gives.

Folded in from two drafts (archived), 2026-11-07. (1) 'brig's planted-link refusal test fails on darwin under the full parallel check': TASK-0079.34's review ran scripts/check (full tier, xdist) on macOS 27.0.1 on 2026-11-07 and test_a_listener_that_left_after_listening_is_refused FAILED (no traceback kept in the -q summary); the orchestrator's serial run of 2026-11-06 passed it. It is in the verified dial TASK-0079.31 will rely on, so a load-dependent failure may be a real race in the dial's leader/peer check. (2) 'brig's planted-link channel tests fail on darwin: kernel can't report the listener': in TASK-0201's full check (2026-11-07, macOS 27) both test_a_listener_that_left_after_listening_is_refused and test_a_link_planted_with_the_empty_stack_is_refused_by_readiness_and_connect failed with EndpointRefused '... the kernel could not report who listens there ([Errno 57] Socket is not connected)' from brig/run/dial.py:219. That is mode (b) above, and it shows mode (b) also hits the second test, test_a_link_planted_with_the_empty_stack_is_refused_by_readiness_and_connect, which this task did not name before. The fix should leave both tests passing on macOS and Linux, still asserting the refusal each was written to, and still failing if that refusal is removed.

Worker claude, 2026-11-07. Causes, with evidence. BRIG, both modes: darwin LOCAL_PEERPID is the connection's peer, not the listen caller. Probe on macOS 27.0.1, a listener that forks and exits with its child holding the socket: child not accepting gives the listen pid, exited; child accepted with the connection open gives the child's pid, alive and in the group; child accepted and closed gives OSError 57 ENOTCONN. The forking workload's child accepted and closed every connection, so the host's peer read raced it three ways: has left (pass), the live child in the group (mode a, DID NOT RAISE), ENOTCONN (mode b). The serving workload closed each connection right after sending, so a genuine control's dial could read ENOTCONN (mode b in the empty-stack test, and seen once in the control of test_a_peer_the_kernel_cannot_report). Not a dial race; the dial's checks are unchanged. Baseline before the fix: 20 runs of test_channel_planted_link.py on darwin, 4 failed (3 DID NOT RAISE, 1 Errno 57). Fix: the forking child holds the socket and never accepts; the serving workload holds each connection until the host closes it. SPEC.md decision-208 records the measured darwin semantics and residuals, no dial code change; TASK-0210 filed for the darwin close-first residual and the identical serving workload in test_channel_reservation_starts.py. Plant: has-left clause removed from _peer_refusal on a scratch-backed copy, sha256 restored 22209aa7: the fixed test red 3 of 3. TUI, two causes. 1: Textual's interval skips ticks it is late for, so a loaded loop shows 1s then 3s and the exact 2s frame is never seen; the test now waits for a count larger than the first. Planted a 2.2 s loop block after the first appearance: the old test failed with the recorded symptom, the new one passed. 2: found in the 20-run proof, Working 0s at the first real tick, because Textual sleeps 0.5 ms short and the widget floored 0.9995 s. The widget now rounds; new test test_a_tick_a_hair_early_says_the_second_it_is_nearest is red against the old widget and green after. Plant that stops the count at 1.5 s: the real-clock test red; restored, sha256 0a6b35db. Proof: darwin 20 of 20 test_channel_planted_link.py; darwin 20 of 20 test_tui_working.py plus test_tui_command_working.py; Linux via scripts/linux-jail-check --shell with bubblewrap, 20 of 20 of test_channel_planted_link.py plus test_tui_working.py, 33 passed each, bwrap test included. scripts/check libs/brig exit 0, 1309 passed 180 skipped, gates and docs ok; scripts/check bh-02/plugins/tui-cordis-plugin --no-gates --no-docs exit 0, 345 passed. AC2, three full scripts/check runs, left unticked for the reviewer.

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
.....................................................s..s.......s.ssssss [ 49%]
ssssssssssssssssssssssssss..sssssssssssssssssssssssss..ssssssssssssssss. [ 51%]
ssssssssss........s.s.............s..................................... [ 52%]
........................................................................ [ 54%]
..................s.sss.ssssssssssssssssssssssssssssssssssssssssssssssss [ 56%]
sssssssssssssssss...s..........................................sssssssss [ 58%]
sssssssss.s..........s.................................................. [ 59%]
........................................................................ [ 61%]
........................................................................ [ 63%]
........................................................................ [ 65%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
.................................................s...................... [ 73%]
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
..............................................................           [100%]
3863 passed, 231 skipped in 70.93s (0:01:10)
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
INFO    -  Documentation built in 1.29 seconds
   ok
== tokens
bh-01's tokens and bh-02's theme are in sync
   ok
```

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
.......................................................s....ssssssssssss [ 49%]
ssssssssssssssssssssssss.s.ssssssssssssssssssssss.ssss..ssssssssssssssss [ 51%]
sssssss.........s.........s............................................. [ 52%]
........................................................................ [ 54%]
....................sssssssssssssssssssssssssssssssssssssssssssss.ssssss [ 56%]
sssssssssssssssss.s..........s.................................sssssssss [ 58%]
sssssssss..s...........s................................................ [ 59%]
........................................................................ [ 61%]
........................................................................ [ 63%]
........................................................................ [ 65%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
.................................................s...................... [ 73%]
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
..............................................................           [100%]
3863 passed, 231 skipped in 71.11s (0:01:11)
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
INFO    -  Documentation built in 1.28 seconds
   ok
== tokens
bh-01's tokens and bh-02's theme are in sync
   ok
```

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
.......................................................s...sssssssssssss [ 49%]
ssssssssssssssssssssssss.....ssssssssssssssssssssssss...ssssssssssssssss [ 51%]
sssssss.s.......s.........s............................................. [ 52%]
........................................................................ [ 54%]
.............s.....sssssssssssss.sssssssssssssssssssssssss.sssssssssssss [ 56%]
sssssssssssssss.ss....s......s.................................sssssssss [ 58%]
sssssssss...s.........................s................................. [ 59%]
........................................................................ [ 61%]
........................................................................ [ 63%]
........................................................................ [ 65%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
................................................s....................... [ 73%]
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
..............................................................           [100%]
3863 passed, 231 skipped in 72.63s (0:01:12)
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
INFO    -  Documentation built in 1.28 seconds
   ok
== tokens
bh-01's tokens and bh-02's theme are in sync
   ok
```
<!-- SECTION:NOTES:END -->
