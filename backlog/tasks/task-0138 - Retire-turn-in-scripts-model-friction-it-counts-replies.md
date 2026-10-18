---
id: TASK-0138
title: 'Retire turn in scripts/model-friction: it counts replies'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 04:15'
updated_date: '2026-10-18 12:20'
labels:
  - scripts
  - naming
  - size-1
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-0009 retires "turn". TASK-0136.02 renamed every use under bh-02/ and docs/bh-02/; scripts/model-friction (outside that scope) still has the `interrupted` signal's text "a turn the person stopped mid-input", the `Totals.turns` field and the `turns` counter in main, all of which mean a reply (a user message that is not feedback). Prose and names only: no behaviour change.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 scripts/model-friction has no turn: the signal text says reply, Totals.turns is Totals.replies, and the counter is named for what it counts
- [x] #2 scripts/model-friction --json and its report print what they printed before (the report already says replies)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Capture before-output: build a synthetic sessions dir under the scratchpad (no real bh-02 sessions exist here: ~/.local/state/bh-02/sessions is absent) covering the signals, plain user replies and feedback nudges; save --json, the report and --help.
2. Edit scripts/model-friction only: the interrupted signal text 'a turn' -> 'a reply'; Totals.turns -> Totals.replies; the main counter turns -> replies (the report's f-string reads totals.replies).
3. Proof: grep for the word turn in the script before (2 hits) and after (none); diff the before/after --json (must be identical) and report (must differ only in the interrupted meaning line, which AC 1 requires).
4. Run bh-02/app/tests/test_model_friction.py (the script's only test; it runs the script via subprocess --json).
5. scripts/arch-check --no-fix once (a file outside every member changed); no scripts/check, as no member changed.
6. Squash to one commit from e093e93 (the start), with the delegation's attribution lines.
Risk: the report's interrupted line text changes, so the report is not byte-identical; say so rather than hide it.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed scripts/model-friction only (prose and names; no behaviour change). The interrupted signal text is now 'a reply the person stopped mid-input'; Totals.turns is Totals.replies; main's counter (user messages that are not feedback) is replies.

AC 1 evidence: git show e093e93:scripts/model-friction | grep -n -E '\bturn' printed 6 lines (exit 0, the starting commit); grep -n -E '\bturn' scripts/model-friction now prints nothing (exit 1). The planted check here is that before-count, not a test: this is a rename with no safety property.

AC 2 evidence: no bh-02 sessions on this machine (~/.local/state/bh-02/sessions absent), so I built a synthetic sessions dir in the scratchpad (2 sessions, 5 replies, 13 inputs, every signal, a feedback nudge, a cut-off line, one session on local/qwen). Before and after (the same command each time):
- --json (all, and --model local/qwen): byte-identical (cmp exit 0).
- --help and the missing-directory error: identical (cmp exit 0, exit 1 both).
- report: identical in every count, the headline ('2 sessions, 5 replies, 13 inputs') and each example list, except the one meaning line the rename is for: 'interrupted ... a turn the person stopped mid-input' is now 'a reply the person stopped mid-input' (diff exit 1, one line; the --model report differs the same way). Ticked because the only changed output is the signal text AC 1 asks for; the reviewer decides whether that fits 'print what they printed before'.

Tests: uv run pytest bh-02/app/tests/test_model_friction.py -q -> 2 passed (exit 0).
Lint: uv run ruff check --no-fix scripts/model-friction exits 1 with 7 findings (unsorted imports, 6 long lines) and ruff format --check reports one hunk: all on lines I did not touch and pre-existing; the script has no .py suffix, so the repo's hook and root ruff config never check it. Not fixed here (scope).
Gates: scripts/arch-check --no-fix -> exit 0, every gate ok (root, brig, cordis, cordis-helpers, host-paths). No member changed, so no scripts/check. scripts/check (the full one) is not run and AC of the reviewer's is not claimed.
Not run: scripts/linux-jail-check (not asked).

Correction: ruff format --check reports two hunks in the script (the _TOUCHED regex and the --model add_argument line), not one; both are in lines I did not touch.
<!-- SECTION:NOTES:END -->
