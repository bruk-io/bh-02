---
id: task-0006
title: 'Decide how a mode signals completion, since idle() is process-wide'
status: Done
assignee:
  - Claude
created_date: '2026-09-16 17:51'
updated_date: '2026-09-18 15:03'
labels:
  - cordis
  - bhh
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while restructuring bhh (task-0003). `Runtime.idle()` returns when no fiber anywhere owns background work, and bhh's bootstrap treats that as "the mode finished". The moment a provider gains its own `background` (a heartbeat, a reconnect loop), `bhh ask` never exits and `bhh` never ends on Ctrl-D. "A mode ends" is a harness concept cordis does not have. Options: the mode component signals completion (a bound future, an event) and the bootstrap retires the loader on it; or cordis gains a scoped wait ("this fiber's owned work is done"). Also record here that an override row's `config` replaces the row's rather than merging (`composition.compose`), which the CLI documents; decide whether a patch should merge.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decision: Option A (a mode component binds a completion signal; bhh's bootstrap awaits that, not Runtime.idle()) — not a new cordis primitive. cordis stays free of the harness concept "a mode ends", matching its own stated design (README: cordis knows nothing about agents, models, tools, UI)
- [x] #2 chat-cordis-plugin's `session` and `ask` each capture the Task `background(...)` returns and `bind("done", task)`; both declare `provides=("done",)`
- [x] #3 CONTRACTS.md documents the new `done` key: value shape, bound by, read by
- [x] #4 bhh's bootstrap.run() awaits the `done` binding instead of Runtime.idle(); a composition whose active mode row never binds `done` fails loudly with an actionable CompositionError, not a silent hang or a fallback to idle()
- [x] #5 A background task cancelled by its own fiber's teardown (a row that leaves mid-run and takes `llm`/`input`/`output` with it) is treated as "the mode stopped", not propagated as CancelledError — falls through to the existing _raise_if_stalled("stopped early") diagnosis, matching prior behavior
- [x] #6 A genuine `llm`/`completion` Recoverable failure (or any exception) from the mode's own work still propagates out of run() with the same shape as before (idle() used to re-raise it)
- [x] #7 Full bhh + cordis test suite passes unchanged in intent (test_ask_fails_loudly_when_the_model_does, test_a_row_that_leaves_mid_run_is_reported_rather_than_a_silent_exit, test_a_composition_that_cannot_start_says_what_it_is_waiting_on, etc.)
- [x] #8 A new test demonstrates the actual bug fixed: a provider with its own unrelated background work (a heartbeat) no longer keeps `bhh ask`/run() alive after the mode's own `done` task completes
- [x] #9 The override-config replace-vs-merge sub-question is recorded as a decision (replace, as already documented — a patch that only merges can never remove a key), not implemented as a code change; a new task if a change is later wanted
- [x] #10 scripts/arch-check and mypy pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Design (confirmed with advisor): Option A. cordis gets no new primitive; "a mode ends" stays a harness (bhh) concept expressed as an ordinary binding, the same mechanism as `llm`/`input`/`output`.

1. chat-cordis-plugin/src/chat_cordis_plugin/wiring.py: `session` and `ask` change from `yield background(coro)` (return discarded) to `task = yield background(coro); yield bind("done", task)`. Add `provides=("done",)` to both (task-0004's contract: a bind should be declared).
2. CONTRACTS.md: new `done` row — "an awaitable (asyncio.Task[None]) that resolves when the mode's own run ends" — bound by `chat:session`, `chat:ask`; read by bhh's bootstrap.
3. bhh/src/bhh/bootstrap.py `run()`: replace `await booted.runtime.idle()` with a `_await_mode(booted)` helper:
   - `_raise_if_stalled(booted, "could not start")` still runs FIRST (unchanged): if the mode row never activates, `done` was never going to be bound anyway, and this gives the better diagnosis.
   - Look up the `done` binding via `Inspection(booted.runtime).bindings.get("done")`; if absent, raise `CompositionError("no row bound \`done\`; a mode row binds an awaitable that resolves when its own run ends")` — fail loud, no silent fallback to the old process-wide `idle()` (that would just keep the bug alive for any composition that doesn't adopt the contract).
   - `await` the task, but `contextlib.suppress(asyncio.CancelledError)`: the mode's own fiber cancels its background task via the ordinary undo path when it deactivates (a dependency it needs disappeared) — that is "the mode stopped early", not a real failure, and must fall through to the existing `_raise_if_stalled(booted, "stopped early")` afterward, not propagate as CancelledError. A genuine Recoverable/other exception from the work itself still propagates (awaiting a task re-raises its exception the same way `idle()` did).
   - `await booted.runtime.settle()` right after, before the second stall check, so a deactivation triggered by the task ending/being cancelled has fully applied before status is inspected (idle() did this internally; a bare `await task` does not).
4. Tests:
   - New test in bhh/tests/test_bootstrap.py: a provider with unrelated background work of its own (a fake heartbeat/reconnect loop bound alongside `llm`, structured like `fragile_model` in conftest.py's PLUGIN) does not keep `run()` from returning once `ask`'s own `done` task completes — this is the literal bug the task describes.
   - Run the existing bhh + cordis suites (test_bootstrap.py, test_cli.py, test_loader.py's editing test) to confirm no behavioral drift in the scenarios above.
5. Record the override-config decision (replace, not merge) in these implementation notes; no code change.
6. mypy, scripts/arch-check, full suite, ruff format/check.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented as planned (Option A, confirmed with advisor): chat-cordis-plugin's session/ask capture background()'s Task and bind it as "done" (provides=("done",) added). CONTRACTS.md documents the new key. bhh's bootstrap.run() now awaits _await_mode(booted) instead of Runtime.idle(); _mode_done() raises CompositionError with an actionable message if no row bound "done" or the bound value isn't an asyncio.Task.

Negative-test proof: temporarily reverted _await_mode back to booted.runtime.idle() and reran the new regression test — it failed with TimeoutError as expected, confirming the test genuinely catches the bug before restoring the fix. (Note: a stray `git checkout --` during this experiment wiped the uncommitted bootstrap.py edits since nothing was committed yet; redone from scratch and reverified. Lesson: commit or use the scratchpad before touching tracked files for a throwaway experiment.)

Advisor review caught three gaps before marking done: (1) only chat:ask was covered by a regression test — added a second test for the interactive chat:session path (input exhausts, session's converse() returns, done resolves) with a heartbeat row alongside it, using a new OneMessage/one_message_ui test double in bhh/tests/conftest.py. (2) _await_mode's CancelledError suppression was unconditional, which would have swallowed a real external cancellation of the run() coroutine itself, not just the mode's own fiber cancelling its own task — narrowed to check `task.cancelled()` before suppressing, re-raising otherwise. (3) held.value was untyped Any, so an absent-done check didn't catch a mode row that bound something non-awaitable under "done" — added an isinstance(held.value, asyncio.Task) check folded into the same CompositionError.

Override-config decision (task's second half, recorded per advisor's guidance — not implemented, no code change): config REPLACES a row's whole config on override/patch, as composition.compose already does and the CLI already documents. This stays as-is: a patch that only merged could never remove a key from a row's config, which is a real capability the current replace semantics provides. If merge semantics are wanted later, that's a new task with its own blast radius (composition.compose, CLI docs, --patch semantics), not a rider on this one.

Final verification: full suite 536 passed, test_invariants 360 passed, mypy clean (including the isinstance-narrowed asyncio.Task return type), scripts/arch-check clean, ruff format/check clean. Task complete.
<!-- SECTION:NOTES:END -->
