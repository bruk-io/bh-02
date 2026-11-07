---
id: TASK-0209
title: >-
  On darwin a tree renamed onto an absent pin, or a write root renamed into
  another, carries files past a carve-out
status: Done
assignee:
  - '@claude'
created_date: '2026-11-07 19:34'
updated_date: '2026-11-07 22:25'
labels:
  - security
  - brig
  - darwin
  - size-3
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0197 (decision-207), measured with sandbox-exec on macOS 27.0.1 under brig's profile shape. Seatbelt judges a rename by its source and destination paths only. decision-207 pins each EXISTING directory between a write root and a carve-out (file-write-unlink on its literal path), which refuses renaming it away or over it. Two shapes stay open: (1) a directory between a root and a carve-out that is ABSENT (bh-02 run from a home with no ~/.config: ~/.config/bh-02 is a trusted carve-out) - a workload makes x/bh-02/startup.py and renames x onto ~/.config, planting a file at the carve-out's path; a rename's destination is checked as file-write-create, which a pin cannot deny without refusing mkdir there. On Linux the runner holds the topmost absent ancestor; on darwin nothing does. (2) A write root renamed whole into another write root (the project into the jail's scratch), edited there and renamed back: no pin lies between root and carve-out for it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each shape is reproduced by a test on darwin that fails before the fix and is seen failing with the fix removed
- [x] #2 On darwin neither shape lets a jailed input put a file at a write_denies path; brig's SPEC.md rules the remedy (decision-N)
- [x] #3 Linux unchanged: scripts/linux-jail-check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. SPEC.md decision-208 (TASK-0209): shape 2 - seatbelt also pins each write root that holds a carve-out with (deny file-write-unlink (literal ROOT)) (parity with bwrap, whose root is a mount); shape 1 - an absent pin is the embedder's to make before launch on darwin (every absent one, not only the topmost), the existing pin rule then holds it; amend decision-207's open-gaps sentence and the profile docstring. 2. brig: render_sbpl emits the root pins; unit golden/ordering tests; real-kernel test_seatbelt_pins gains the root-rename shape with its control (renames inside the root still work). 3. runner: on darwin make the absent pins as placeholders through the Linux record/lock/sweep machinery, release sweeps on darwin too; darwin app test: tree renamed onto absent ~/.config refused, control write inside it allowed. 4. Plant: remove each fix (scratch copy + sha256), see each test fail. 5. Checks: brig + runner member checks, linux-jail-check. Risks: placeholder cleanup on darwin leaving dirs; seatbelt root pin refusing rmdir of the project root (same as bwrap's mount).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Shape 2 (brig): render_sbpl now emits (deny file-write-unlink (literal ROOT)) for each write root (not /) with a write deny strictly beneath it, after the carve-outs and before the decision-207 pins. New real-kernel test libs/brig/tests/integration/test_seatbelt_pins.py::test_a_write_root_above_a_carve_out_can_t_be_renamed_into_another_root: workspace renamed into a second root (scratch), carve-out file rewritten there, renamed back. Before the fix it FAILED with rename_root_away/rewrite_moved/rename_root_back all OK (file planted); after, the rename away is DENIED with seatbelt's signature and the same-jail control (rename inside the root, rename out into the scratch, write, chmod, utimes on the root) is OK. Unit golden/ordering/pin tests in test_seatbelt_profile.py updated for the root pin.

Shape 1 (runner, darwin): no pure-profile remedy (a rename destination is file-write-create, the same as mkdir), so the embedder makes every absent pin before launch: BrigJail._absent_pins (brig's pins, not lexists), made through the Linux placeholder record/lock/sweep machinery, which now runs on darwin too; release() sweeps on darwin too. New darwin tests in bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py: test_a_darwin_jail_holds_an_absent_directory_above_a_write_deny_against_a_rename_onto_it (home with no .config, ~/.config/bh-02 trusted; input renames x/bh-02/startup.py onto ~/.config) FAILED before the fix (rename OK, file planted at the denied path); after, the rename is EPERM from the sandbox and a write in ~/.config is OK. Control test test_a_darwin_jail_removes_the_directory_it_made_above_a_write_deny_once_it_stops: made while running, removed with its record after stop.

Ruling: SPEC.md section 6 decision-208 (TASK-0209), decision-207 marked amended. Docs: profile.py docstring, runner jail.py docstrings, runner README.

Planted (scratch copy + sha256, restored to matching digests): root-pin line replaced by pass, and runner made Linux-only again: all three new tests FAILED (rename_root_away OK; rename OK instead of Operation not permitted; ~/.config not made).

Checks: testlock scripts/check libs/brig -> all ok (1310 passed, 180 skipped; gates ok; docs ok). testlock scripts/check bh-02/plugins/runner-cordis-plugin --no-gates --no-docs -> ok (82 passed, 33 skipped) after fixing two long lines. Darwin app/extensions/python tests: testlock pytest bh-02/app/tests/test_python_repl.py bh-02/plugins/extensions-cordis-plugin bh-02/plugins/python-cordis-plugin -n 8 -> 243 passed, 14 skipped.

Linux: testlock scripts/linux-jail-check -> exit 0, 327 passed, 4 skipped. The runner's Linux path is unchanged (lock, placeholders and release were already Linux behaviour; only darwin gained them); the profile change is seatbelt's. README also says the root pin's cost (an input can't rename or remove the project directory itself, as on Linux).

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
..................................................s..s.......sssssssssss [ 49%]
sssssssssssssssssssssss.s.ssssssssssssssssssssssssss...sssssssssssssssss [ 51%]
ssssss..s...ss.......................................................... [ 52%]
........................................................................ [ 54%]
....................ssssss.ssssssssssssssssssssssssss.ssssssssssssssssss [ 56%]
ssss..sssssssss...sss.s..s.s........s...........................ssssssss [ 58%]
ssssssssss.............s...........s.................................... [ 59%]
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
.............................................................            [100%]
3862 passed, 231 skipped in 69.83s (0:01:09)
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
INFO    -  Documentation built in 1.31 seconds
   ok
== tokens
bh-01's tokens and bh-02's theme are in sync
   ok
```

No repro: the fix is already committed (550cec5d), so the repro tests pass on this tree; the failing-before evidence is the worker's plant run above (fixes removed by scratch copy + sha256: test_seatbelt_pins.py::test_a_write_root_above_a_carve_out_can_t_be_renamed_into_another_root and test_runner_confined.py::test_a_darwin_jail_holds_an_absent_directory_above_a_write_deny_against_a_rename_onto_it both failed). Reviewer reran both: 2 passed.

Review (reviewer agent): closed. Full check (record-check --tier full, through testlock) green: 3862 passed, gates, docs, tokens ok; tree clean afterwards. AC1: three new tests with plant evidence in notes. AC2: root pin in render_sbpl and absent-pin creation in BrigJail._absent_pins close both shapes; SPEC.md decision-208 rules it, decision-207 amended. AC3: linux-jail-check exit 0 (327 passed) per worker; Linux code path unchanged in the diff. Findings: none blocking. Documented trade-offs: a jailed input can no longer rename/remove the project root on darwin (Linux parity); an empty ~/.config or .git exists on the host while a darwin jail runs and is swept after. No drafts filed.
<!-- SECTION:NOTES:END -->
