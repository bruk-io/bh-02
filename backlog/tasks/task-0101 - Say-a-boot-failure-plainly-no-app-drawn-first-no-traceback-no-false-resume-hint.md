---
id: TASK-0101
title: >-
  Say a boot failure plainly: no app drawn first, no traceback, no false resume
  hint
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-15 02:27'
updated_date: '2026-10-17 03:54'
labels:
  - app
  - size-2
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Moved out of the naming intent TASK-0099 (was TASK-0099.09), deferred by the owner (2026-10-15): this run fixes only critical bugs, and this is not critical (the error is said and bh-02 exits; nothing is lost). Three ways a boot failure reads worse than it should: (1) a layer naming a use no plugin provides fails at boot with the loader's error, but the ui row starts first and the TUI draws its banner, composer and status bar for 1 to 2 seconds before bh-02 shuts down and prints the error; look at whether the shell can check the rows' states before the ui row starts, or hold the ui row until the chat row's dependencies are met, without making the ui depend on rows it must not reload with (a design question: say what is chosen in the notes). (2) A layer row with no use (a --patch, a session.toml) makes cordis's compose raise ValueError, which bh_02.cli's _run does not catch, so the person sees a traceback instead of a layer error naming the row and what to add (found by TASK-0099.08's close review). (3) When a session fails at boot, bh-02 still prints 'session ... (uv run bh-02 --resume to continue it)', offering a resume that fails the same way (found by TASK-0099.07's close review). Not to be started without the owner's word.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A launch whose composition cannot start prints the error without first drawing the app (checked in a pty: the screen never shows the composer), or the notes say why that cannot be done without a worse dependency
- [x] #2 A layer row with no use makes bh-02 exit with a layer error naming the row and what to add, never a traceback; a test through the real launch
- [x] #3 A session that fails at boot is not offered a resume; the message says it failed and what to change
- [x] #4 scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Order: (1) tests first, seen failing on the starting commit: real launch of a stale use (screen never shows the composer, never enters Textual's alternate screen), a patch row with no use and a hand-edited session.toml row with no use (layer error naming the file, the row and what to add; no Traceback), a resumed session that fails at boot (no 'to continue it' hint; says it failed and what to change). (2) bootstrap.py: read_layers returns each layer's rows; run() checks, before boot mounts anything, (a) a row no layer below adds and that has no use -> LayerError naming file, row, what to add; (b) every enabled row's use resolves (cordis.loader.resolve, what the loader does in _mount) -> NotStarted 'could not start:' with the loader's own 'ROW: unresolved: ...' line. Pure parts split from the I/O (decide split). (3) cli.py: a resumed session that did not start prints a line saying so and naming its layer, not the resume hint. (4) docs: layers.md, sessions.md, app README. Design (criterion 1): a static pre-flight in the shell, not holding the ui: the ui depends on nothing (test_booting asserts resolve(ui).inject == set()), so holding it until loop/commands/jobs are active would make it depend on them and reload it with /model. Covers rows that cannot resolve; a row waiting on a key or whose component raises is only known by running rows, so it still draws first (said in notes). Risks: pre-flight resolves each use once more than the loader (measure start time before/after, interleaved); wording of the unresolved line drifting from the loader's (a test compares the two). Proof: new tests, uv run pytest bh-02/app/tests -q -n auto --dist loadgroup under tini, scripts/check bh-02/app once, scripts/arch-check --no-fix if I touch anything outside the member (docs).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Orchestrator, 2026-10-17: the owner's word to start it, which the earlier deferral asked for: "ok wrap up all tasks that you are able to" (in conversation, this date).

TASK-0101 worker notes (2026-10-17).

DESIGN (criterion 1). Chosen: a static check in the shell before any row mounts, not holding the ui. bootstrap.run() now (a) reads the layers (read_layers returns each with its rows), (b) refuses a row with no use that no earlier row added (LayerError naming file, row, what to add), (c) resolves every enabled row's use with cordis.loader.resolve, the call the loader makes in _mount, and raises NotStarted "could not start:\nROW: unresolved: ..." before Runtime() exists, so no row (the ui included) starts. Not done, and why: holding the ui until the chat row's dependencies are active would make tui:ui depend on loop/commands/jobs (and through loop on model, tools, transcript, system, approval, output, asides, executor), so a /model switch or /clear, which reload those, would reload the ui and lose the screen; the ui depending on nothing is TASK-0089's must-not-break and test_booting.test_every_shipped_layer_names_a_plugin_component_for_every_row asserts resolve(ui).inject == set(). Holding it by flipping its row from disabled to enabled after boot does not work either: the loader's watcher re-reads its config on every layer-file save and would put the held state back. What this does NOT cover: a row that resolves but cannot run (waits on a key no row binds, e.g. tools disabled; or its component raises). That is known only by running rows, and refusing on declared provides alone would refuse a component that binds without declaring it. For those the ui still draws first, then the error as before (checked: a layer with tools disabled still draws, 2.0 s). Said in docs/bh-02/using/layers.md and app/README.md.

Cost: the pre-flight resolves each use once more (the loader already does it twice at boot: boot's unsatisfiable check, then _mount). Measured in process: 30 rows, second pass 113-118 ms (about 75% is importlib.metadata.entry_points at ~4 ms a call). Time to the composer in a real pty launch, old/new interleaved, 3 rounds after a warm-up, machine shared with another worker: old 1.51 s median (1.51, 1.52, 1.41), new 1.54 s (1.67, 1.47, 1.54): inside the noise.

(2) A layer row with no use: before, compose raised ValueError inside boot() and bh-02 printed a Traceback (seen). Now exit 1: "error: FILE: row 'mine' has no `use`, and no layer below it adds a row 'mine'; add use = "plugin:component" to make it a row of your own, or, to change a row bh-02 has, write that row's id (/rows lists them)". Same for a hand-edited session.toml on --resume.

(3) A resumed session that did not come up (NotStarted or LayerError) no longer prints "(uv run bh-02 --resume to continue it)"; it prints "session ID  did not start and is kept as it was; change what the error above names, in this session's own layer (PATH) or in a --patch file". A new session that does not start is still discarded, silent as before.

TESTS, each seen failing on the starting commit (7d4c934) then passing:
- test_real_launch: test_a_patch_naming_a_use_no_plugin_provides... (now also _never_drawn: no Textual alternate-screen switch \x1b[?1049h in the pty bytes and the composer line never written; failed: "the app was drawn first"); test_a_resumed_session_whose_layer_names_a_use... (never drawn + no "to continue it"/"--resume" + the did-not-start line; with the pre-flight in and the cli change reverted it failed only on the hint, "assert 'to continue it' not in ..."); new test_a_patch_row_with_no_use_that_no_layer_added_is_a_layer_error_naming_the_row_and_what_to_add (failed with the Traceback; also asserts no session left); new test_a_session_layer_row_with_no_use_is_the_same_layer_error_and_the_session_is_kept (failed likewise). They wait on the process exit, not on time (TASK-0097's rule).
- test_booting: test_a_patch_row_with_no_use_that_no_layer_added_is_a_layer_error_naming_it (replaces test_a_composition_that_cannot_be_read_says_why_instead_of_crashing, which pinned the old loader-failure text; run(trace=) hears nothing); test_a_row_that_cannot_resolve_stops_the_run_before_any_row_starts (trace hears nothing; the cause alone, no "waiting on"); test_the_line_for_a_row_that_cannot_resolve_is_the_one_the_loader_gives_it (the pre-flight line equals the loader's status() text for the same row, so the two wordings cannot drift). All three failed before.
- test_command_line: test_a_resumed_session_that_cannot_start_is_kept_and_not_offered_a_resume (was ..._is_kept and asserted the false hint is present).

RUNS: uv run pytest bh-02/app/tests -q -n auto --dist loadgroup (under tini): 247 passed, 1 skipped. scripts/check bh-02/app: format, lint, types, tests (247 passed, 1 skipped), gates (root, brig, cordis, cordis-helpers, host-paths) and docs (mkdocs) all ok, tokens skipped (no bh-01 beside the repository); exit 0 (read as PIPESTATUS, the output went through tail). Criterion 4 left unticked: scripts/check as a whole is the reviewer's.

FILES: bh-02/app/src/bh_02/bootstrap.py, cli.py; tests above; docs/bh-02/using/layers.md, sessions.md, reference/command-line.md; bh-02/app/README.md; bh-02/CLAUDE.md (one line under The running harness).

NOT DONE / for the owner, unsized: the unmet-dependency and component-raises cases still draw the app first (needs either cordis exposing a pre-mount check of declared provides that refuses only when sure, or the ui row starting last, which the ui-depends-on-nothing rule forbids).

No repro: as a failing test on this commit, since the fix is in it; the repros are the real-launch tests named above (test_a_patch_row_with_no_use..., test_a_session_layer_row_with_no_use..., test_a_resumed_session_whose_layer_names_a_use...), which the worker saw fail on 7d4c934 and the reviewer saw pass here.
<!-- SECTION:NOTES:END -->
