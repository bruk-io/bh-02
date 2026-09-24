---
id: task-0008
title: >-
  Express bhh's mode-completion dependency as a declared cordis inject, not an
  ad hoc binding lookup
status: Done
assignee:
  - Claude
created_date: '2026-09-22 01:47'
updated_date: '2026-09-22 02:03'
labels:
  - bhh
  - cordis
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up to task-0006. `bhh`'s bootstrap (`_mode_done`/`_await_mode` in `bhh/src/bhh/bootstrap.py`) reaches into `Inspection(booted.runtime).bindings.get("done")` *after* `boot()` returns, hand-rolling both the "is it there" check (a `CompositionError` if not) and the "is it the right shape" check (`isinstance(held.value, asyncio.Task)`). This grew out of a design discussion about whether `bhh` should own a fixed list of "capabilities it supports" (llm/input/output/tools/...) and fail compositions that don't match it. That framing turned out to be the wrong one: those keys belong to the *mode row*'s own injects (`chat:session` already declares them, and `unsatisfiable()` already covers them per-row); `done` is the only thing `bhh` itself actually depends on.

Rather than a harness-level capability list, express that one dependency the way every other consumer in this codebase expresses one: as a declared `inject` on a component. Mount a small `harness` component (e.g. `bhh.bootstrap:harness(*, done: asyncio.Task[None]) -> Effects`) as an extra row via `boot()`'s existing `overrides` argument. That gets `bhh` two things for free, through mechanisms that already exist and are already tested:
- `unsatisfiable()` already reports a row whose inject nothing provides, before any effect runs — no row binding `done` becomes exactly that case, with the same diagnostic quality as any other missing dependency, not a bespoke `CompositionError` message.
- `check_contract` already verifies a bound value against its consumer's annotation at commit time — annotating `done: asyncio.Task[None]` replaces the manual `isinstance` check with the same mechanism `git`/`Model`/`Registry` already rely on.
- A `harness` row that never activates is already caught by the *existing* `_raise_if_stalled(booted, "could not start")` call, with `Inspection.explain("harness")` naming exactly what it's `waiting on`. No new stall-detection code.

What's left in `_await_mode` after this is just the asyncio-level `await` and the CancelledError-vs-self-cancellation distinction task-0006 already added — that part isn't a cordis dependency question and shouldn't move.

Constraint carried over from the design discussion (flagged during review, not yet acted on): whatever this becomes must not make a *mid-run* `reload()` fatal. An unsatisfiable row during `reload()` has to stay advisory — the composition intentionally stays up on a bad layer-file edit — so this only ever changes what happens at initial `boot()`, via the same `could not start` path that already exists and is already advisory-vs-fatal in the right way.

No new cordis code is expected: `cordis.loader`'s existing `_unsatisfiable_rows`/`unsatisfiable()`/`check_contract` stay internal and untouched; this is a `bhh`-side restructuring of how it expresses its own dependency, using public cordis API (`boot(overrides=...)`, `@component`, `bind`) that already exists.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 bhh no longer reaches into Inspection.bindings post-boot to check whether `done` is present or correctly shaped; that is expressed as a declared `inject` on a component cordis mounts as part of the composition
- [x] #2 A composition whose mode row never binds `done` is caught by the existing `_raise_if_stalled(booted, "could not start")` path (or equivalent), with cordis's own "waiting on: done" diagnosis, not a bespoke CompositionError string
- [x] #3 A `done` binding of the wrong shape is caught by cordis's existing contract-checking mechanism (`check_contract`/`ContractViolation`), not a hand-rolled isinstance check
- [x] #4 A mid-run `reload()` with an unsatisfiable composition remains advisory, never fatal — this change only affects behavior at initial boot
- [x] #5 _await_mode's asyncio-level await and its CancelledError-vs-self-cancellation handling (from task-0006) are preserved, not reworked
- [x] #6 Existing bhh + cordis test suites continue to pass, including the task-0006 regression tests for both chat:session and chat:ask with an unrelated background provider
- [x] #7 mypy and scripts/arch-check pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
bhh/src/bhh/bootstrap.py gets a new `harness` component and a `ModeDone` Protocol, mounted as an extra row via `boot()`'s existing `overrides` argument.

1. `ModeDone` Protocol (runtime_checkable, local to bootstrap.py): `Awaitable[None]` + `cancelled() -> bool` — the shape `_await_mode` actually needs (await it, and ask whether IT specifically was cancelled). Not `asyncio.Task` directly: `asyncio.Task[None]` is a subscripted generic, and `cordis.component._as_class` only treats a bare `type` as a contract (`isinstance(annotated, type)` is False for a parameterized generic alias), so a concrete `asyncio.Task[None]` annotation would silently not be contract-checked. A locally-defined Protocol matches this codebase's existing convention (Model/Input/Output/Registry/Subprocess are all consumer-owned Protocols) and sidesteps the generic-subscript wrinkle entirely.
2. `@component async def harness(*, done: ModeDone) -> Effects: yield enter(contextlib.nullcontext())` — declares the one dependency and does nothing else. No bind: nothing else should depend on bhh's own plumbing row.
3. `run()`: append `Row("harness", "bhh.bootstrap:harness")` to the overrides passed to `boot()`, not to the ones the caller passed in (so a caller's own overrides aren't affected).
4. `_mode_done`'s manual `if held is None or not isinstance(...)` CompositionError disappears. Once `_raise_if_stalled(booted, "could not start")` has passed, `harness` is ACTIVE, which cordis already only allows once `check_contract` accepted the bound value against `ModeDone` — so `done` is guaranteed present and shape-correct. Fetch it directly: `booted.runtime.root.get("done")`.
5. `_await_mode`'s try/except CancelledError-vs-self-cancellation logic and the final `settle()` are unchanged.
6. CONTRACTS.md: `done`'s "Read by" column updated from "bhh's bootstrap" to "bhh's bootstrap (via its own `harness` row)" — one-line, no shape change.
7. Verify existing tests still pass under substring assertions (`_raise_if_stalled` messages gain an extra `harness#N: ...` block whenever `done` isn't bound, since `harness` now always stalls alongside the mode row in that case) — no test does exact-equality on the full stalled message, all check specific substrings, so this is expected to need no test changes, but must be verified by running the suite, not assumed.
8. Full verification: pytest (bhh + cordis), test_invariants.py, mypy, scripts/arch-check, ruff format/check.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented as planned: `_ModeDone` Protocol (Awaitable[None] + cancelled()) local to bootstrap.py; `harness` component injects `done: _ModeDone` and does nothing else (yield enter(nullcontext())); run() mounts it via an extra Row appended to overrides passed to boot(). _mode_done's hand-rolled presence/isinstance check is gone; _await_mode fetches `booted.runtime.root.get("done")` directly, trusting _raise_if_stalled("could not start") already proved it's bound and shape-correct.

Real regression found and fixed before verification finished: harness's own activation adds an extra async scheduling hop (its own fiber transition, waited on by boot()'s settle()), which shifted a pre-existing timing race — a fast background failure (angry_model's Slow/Recoverable exception) could now land and get recorded as "active, work failed" (task-0005's status string) BEFORE _raise_if_stalled("could not start") ran, misreporting a genuine Recoverable failure as a CompositionError instead of letting it propagate through _await_mode's await as designed. Root cause: _is_stalled treated task-0005's "active, work failed" status as a stall, which was never actually correct — that fiber is still ACTIVE, its setup/binds still stand (cordis/README.md), and the failure is meant to reach run() through the mode's own done-await, not through the could-not-start/stopped-early gate. Fixed _is_stalled to exclude "active, work failed" from its stalled definition. Verified with 8x repeated runs of the previously-racy test, all passing.

Consequence of that fix, recorded as a deliberate decision per advisor review (not a side effect): an UNRELATED row's background work failing is now entirely non-fatal to run() — visible via status()/explain() but never raised. This reverses a claim in task-0005's own notes ("this also fixes bhh's _raise_if_stalled for free") which turns out to have been wrong/incomplete reasoning at the time. Documented explicitly in run()'s docstring and in _is_stalled's docstring so the next reader doesn't have to rediscover it.

arch-check found two over-exposed-module-symbol findings: ModeDone (renamed to _ModeDone via `uv run pypeeker demote`, since it's genuinely only used within bootstrap.py) and harness (added to the over-exposed-module-symbol allow list in pyproject.toml, same pattern as every other plugin component named by a composition as a string — here named by run() itself via Row("harness", "bhh.bootstrap:harness") rather than a layer file, but the same reason).

Advisor caught that AC #2 and #3 had zero test coverage despite the full suite passing — passing tests proved the happy path, not the two failure paths the task was actually about. Verified the contract-checking chain is real first (`derive(harness).contracts == (('done', _ModeDone),)`) before writing tests, per advisor's suggested falsification check. Added two tests to bhh/tests/test_bootstrap.py: a mode row that never binds `done` (expects the ordinary "waiting on: done" stall diagnosis) and a mode row that binds a non-awaitable under `done` (expects the contract violation to surface as "is bound to a int, which..."). Both new test-fixture components (echo_model reused as a plain non-done-binding mode; new bad_done_mode) added to bhh/tests/conftest.py.

CONTRACTS.md's `done` row's "Read by" column updated to `bhh.bootstrap:harness`, with a sentence explaining bhh no longer reaches into the store by hand.

Final verification: full suite 538 passed (up from 536: two new tests), test_invariants 360 passed, mypy clean, scripts/arch-check clean, ruff format/check clean. Task complete.
<!-- SECTION:NOTES:END -->
