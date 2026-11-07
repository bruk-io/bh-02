---
id: TASK-0197
title: >-
  On darwin a session run from home lets an input write what a later session
  reads as the person's
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-07 04:27'
updated_date: '2026-11-07 19:45'
labels:
  - security
  - runner
  - darwin
  - size-3
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found 2026-11-06 on macOS 27.0.1 (Python 3.15.0rc2), with and without Claude Code's sandbox: bh-02/app/tests/test_python_repl.py::test_a_session_run_from_home_can_t_choose_what_a_later_session_reads_as_the_person_s fails at line 980 - the sixth of the paths it tries is WROTE where the test expects DENIED. TASK-0169.04's worker saw it and reported it identical on the base commit; nobody filed it. Until it is diagnosed this reads as a hole in the darwin jail (a jailed input planting a file a later session trusts), not a test problem; if diagnosis shows the test is wrong on darwin, the notes say why and the test is fixed rather than skipped.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The path that is written is named and the cause found (Seatbelt profile, spec_for's denies, or the test's expectations on darwin), with the evidence in the notes
- [x] #2 On darwin a jailed input cannot write any path the test lists; the test passes on macOS and still fails if the deny is removed (seen failing)
- [ ] #3 scripts/check passes on Linux (scripts/linux-jail-check too) and the test passes on macOS
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Diagnosis by probe: inputs 5 and 6 rename HOME/xdg and HOME/.config, the existing parents of the trusted carve-outs; Seatbelt checks a rename against its source and destination paths only, so the subtree rides along. 2. SPEC.md first: amend decision-168's sentence that seatbelt needs no pin, add decision-207: seatbelt pins each directory between a write root and a carve-out with a file-write-unlink deny on its literal path. 3. render_sbpl emits the pins after the carve-outs, from brig.mech.bwrap.pins as oci does; resolved already carries them via build_compile_ctx. 4. Unit tests: golden and order fixtures get the pin resolutions and line; a new unit test pins the emission; seen failing with it removed. 5. Prove: the bh-02 home-session test red before, green after, red with the pin loop removed; brig seatbelt tests; linux-jail-check; scripts/check for brig and the app. Risk: the pin must not stop ordinary work; probed that mkdir, file create, chmod and utimes still work. Out of scope, filed: a write root renamed into another write root, and a tree renamed onto an absent ancestor.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner stand-in (Opus), 2026-11-06: Approved in this run (Opus worker, security). Condition: close only with the written path named and the cause shown; if the test's darwin expectation is what is wrong, say why with evidence and fix the test - no skip, no xfail, no widening of what counts as DENIED. The reviewer checks AC #2's seen-failing step.

Diagnosis (AC 1): two inputs were written, not one; pytest shows only the first diff. Index 5 renamed <tmp>/home/xdg (the parent of the trusted <tmp>/home/xdg/bh-02) to home/moved, and index 6 renamed <tmp>/home/.config (the parent of the trusted, absent ~/.config/bh-02) to home/moved-too; a temporary diagnostic test, since removed, printed WROTE for both. Cause: brig's Seatbelt profile. SBPL judges a rename by its source and destination paths only, so the deny on xdg/bh-02 never sees its parent leave with it. Probed with sandbox-exec under brig's profile shape (deny default, system.sb): renaming the parent away, rewriting the denied file under the new name and renaming it back all succeeded, and the changed file was then at the denied path. SPEC.md decision-168 had held that seatbelt needs no pin. The test's darwin expectation is right. Fix in brig (SPEC first): SPEC.md decision-207, with decision-168's sentence amended. render_sbpl emits one (deny file-write-unlink (literal RESOLVED)) per directory brig.mech.bwrap.pins names, after the carve-outs. Probed: file-write-unlink refuses a rename-away and a rename over an existing pin, while mkdir, file create, chmod and utimes inside or on the pin stay allowed; file-write* on the literal would also refuse utimes. AC 2: the home-session test passes; with the pin line planted out of profile.py (scratch copy, sha256 eebc23a4... restored and matched) it failed again at index 5, WROTE != DENIED, seen. New unit tests in test_seatbelt_profile.py (pin emission, refusal of an unresolved pin, control with no pin); with the pin line removed, the new test, the golden and the sealed /private/tmp case failed, seen. Runs: scripts/check libs/brig exit 0 (1308 passed); scripts/check bh-02/app --no-gates --no-docs exit 0 (359 passed); runner and python plugin tests 253 passed; brig seatbelt/darwin tests 84 passed; scripts/linux-jail-check exit 0 (327 passed, 2 skipped). AC 3 is left for the reviewer: the full scripts/check was not run. Filed TASK-0209 for two gaps that are measured and named in decision-207: a tree renamed onto an absent pin, and a write root renamed into another root.

Added libs/brig/tests/integration/test_seatbelt_pins.py: a real seatbelt jail in which a rename of the pin away and a rename over an existing empty pin are refused with seatbelt's denial signature, the carve-out's file stays unchanged, and, in the same jail as the control, mkdir, write and remove inside the pin plus chmod and utime on it succeed. decision-207 cites it. With the pin line planted out of profile.py it failed (rename_away and rename_over both OK), seen; restored, sha256 eebc23a4... matched. Re-run of scripts/check libs/brig: exit 1, only from libs/brig/tests/integration/test_channel_planted_link.py, which compiles an empty Stack on darwin, so no seatbelt is involved. Run alone it failed 1 time in 5. This is the known flake TASK-0206, not this change; the first scripts/check libs/brig run passed with it.

Check `scripts/check` exited 0

(32 earlier lines omitted)
```text
........................................................................ [ 35%]
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 44%]
........................................................................ [ 45%]
........................................................................ [ 47%]
............................................s.......s......sssssssssssss [ 49%]
sssssssssssssss.sssssss.ssssssssssssssssssssssssss...sssssssssssssssssss [ 51%]
ssss.s.......s.......................................................... [ 52%]
....s................................................................... [ 54%]
...............s..ssssssssssssssssssssssssssss.sssssssssssssssssssssssss [ 56%]
ssssssssssss...s..s..s..s................................sssssssssssssss [ 58%]
sssss................................................................... [ 59%]
........................................................................ [ 61%]
........................................................................ [ 63%]
........................................................................ [ 65%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
.............................................s.......................... [ 73%]
........................................................................ [ 75%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 96%]
........................................................................ [ 98%]
..........................................................               [100%]
3859 passed, 231 skipped in 72.56s (0:01:12)
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
INFO    -  Documentation built in 1.25 seconds
   ok
== tokens
bh-01's tokens and bh-02's theme are in sync
   ok
```
<!-- SECTION:NOTES:END -->
