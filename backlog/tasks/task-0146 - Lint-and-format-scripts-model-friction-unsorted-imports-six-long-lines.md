---
id: TASK-0146
title: 'Lint and format scripts/model-friction (unsorted imports, six long lines)'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 12:20'
updated_date: '2026-10-18 19:41'
labels:
  - scripts
  - size-1
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
scripts/model-friction has no .py suffix, so the PostToolUse hook and the root ruff config never check it. Run on the file, ruff check --no-fix reports 7 findings (unsorted imports, 6 lines over 110 characters) and ruff format --check wants two lines wrapped. All pre-existing, none from TASK-0138, which found them and left them alone (scope). Fix formatting and lint only: no behaviour change.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 uv run ruff check --no-fix scripts/model-friction exits 0
- [x] #2 uv run ruff format --check scripts/model-friction exits 0
- [x] #3 scripts/model-friction --json over the same sessions prints what it printed before
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Baseline before any edit: build a synthetic sessions dir in the scratchpad (not the repo; this machine has no bh-02 sessions) with one transcript that trips every signal, one on local/qwen, a torn line, and a dir with no meta. Save the --json, the default report, --model --json, --examples, --help and the missing-dir error to scratchpad, with exit codes.
2. Lint and format: ruff's one import fix is the extra blank line before 'type Message' (the imports themselves are already sorted). The five long lines are dict strings in SIGNALS (4) and one argparse help at line 354; wrap each by implicit string concatenation so every string value is unchanged, the argparse call by ruff format. No text is shortened, no noqa, no rename.
3. Prove the gates: ruff check --no-fix and ruff format --check fail before (seen: exit 1, 6 findings, 1 format hunk), pass after.
4. Behaviour: rerun the same baseline commands after the edit and cmp each output and exit code; check the --json output covers every signal so the comparison has teeth.
5. Run uv run pytest bh-02/app/tests/test_model_friction.py -q (it runs the script). No member code changes, so no scripts/check; scripts/arch-check --no-fix once since scripts/ changed.
Risks: the wrapped strings must stay identical (check by importing the dict before and after with the values compared, not only the report). Brief says 7 findings and 2 format lines; ruff reports 6 and 1 hunk: say so in the notes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Start commit db98d178a4107af1ffa296a4ca78ccb6a649e820 (branch ccr-8cdd69a0-gt1lov). Only scripts/model-friction changed.
Before: ruff check --no-fix exit 1, 6 findings: unsorted-imports (one extra blank line before 'type Message') and 5 line-too-long (lines 38, 40, 44, 53, 354). The brief said 7 findings and 6 long lines; ruff reports 6 and 5. ruff format --check exit 1, one hunk (the --model add_argument call, line 354); the brief said two lines.
Change: removed the extra blank line; ruff format wrote the four long SIGNALS values as parenthesised single-line strings (text unchanged) and split the --model add_argument call. No text shortened, no noqa, no rename.
After: uv run ruff check --no-fix scripts/model-friction -> 'All checks passed!', exit 0. uv run ruff format --check scripts/model-friction -> '1 file already formatted', exit 0.
Behaviour: no bh-02 sessions on this machine (~/.local/state/bh-02 holds only jails/), so I built a synthetic sessions dir in the scratchpad (4 sessions, one on local/qwen, a torn line, a non-object line, a bad meta.json, a dir without a transcript; 25 inputs; all 17 signals in the --json). Before and after, the same 9 commands (--json, report, --examples 5, --model local/qwen --json and report, --model nothere --json, --help, missing dir, default dir): stdout, stderr and exit code byte-identical (cmp exit 0 each; exit codes 0,1 as before). SIGNALS, _KINDS, _CHANGED, _STARTUP_FILE, _RUNNERS compared by value after import: equal.
Teeth: a copy with 'cat' renamed to 'catx' in _KINDS gives a different --json (cmp exit 1, line 4), so the comparison catches a behaviour change.
Tests: uv run pytest bh-02/app/tests/test_model_friction.py -q -> 2 passed, exit 0.
Gates: scripts/arch-check --no-fix -> exit 0, root, brig, cordis, cordis-helpers, host-paths all ok. No member changed, so no scripts/check MEMBER. The full scripts/check was not run and is not claimed. scripts/linux-jail-check not run (not asked).

Check `scripts/check` exited 0

(31 earlier lines omitted)
```text
........................................................................ [ 32%]
........................................................................ [ 34%]
........................................................................ [ 36%]
........................................................................ [ 38%]
........................................................................ [ 40%]
........................................................................ [ 42%]
........................................................................ [ 43%]
........................................................................ [ 45%]
........................................................................ [ 47%]
.......s..ss....sss..ss.s..ss.s.s...s...s..ss...s..ssss.ss.ss......s.... [ 49%]
........................................................................ [ 51%]
........................................s............................... [ 53%]
.........................................sssssssssssssssssssssssssssssss [ 54%]
ssssssssssssssssssssssssssssssssssss...............................sssss [ 56%]
ssss...s............ss.................................................. [ 58%]
........................................................................ [ 60%]
........................................................................ [ 62%]
...............s.s...s.................................................. [ 64%]
........................................................................ [ 65%]
........................................................................ [ 67%]
........................................................................ [ 69%]
........................................................................ [ 71%]
.............................s.......................................... [ 73%]
........................................................................ [ 75%]
........................................................................ [ 76%]
........................................................................ [ 78%]
........................................................................ [ 80%]
........................................................................ [ 82%]
........................................................................ [ 84%]
........................................................................ [ 86%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 95%]
........................................................................ [ 97%]
........................................................................ [ 98%]
.............................................                            [100%]
3817 passed, 118 skipped in 212.43s (0:03:32)
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
INFO    -  Documentation built in 4.76 seconds
   ok
== tokens
   skipped: no /home/user/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
