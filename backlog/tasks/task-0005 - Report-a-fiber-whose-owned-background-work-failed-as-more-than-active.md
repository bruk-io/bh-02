---
id: task-0005
title: Report a fiber whose owned background work failed as more than "active"
status: Done
assignee:
  - Claude
created_date: '2026-09-16 17:51'
updated_date: '2026-09-22 02:03'
labels:
  - cordis
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while restructuring bhh (task-0003). `background_step.finished` in `cordis/src/cordis/runtime.py` records the error on `fiber.error` and `rt._failure` but never changes the fiber's state, so `loader.describe` and `Loader.status()` report "active" for a row whose work has died. `idle()` re-raises the failure, so a bootstrap that waits on it sees it; a bootstrap that inspects status (bhh's `_raise_if_stalled`) does not. Decide the right shape: `describe` saying `active, work failed: ...` when `fiber.error` is set on an ACTIVE fiber, or a state for it, and make `Inspection.explain` say it too.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Loader.describe (and thus Loader.status()) reports a Live fiber that is State.ACTIVE with fiber.error set as "active, work failed: {error!r}", not plain "active"
- [x] #2 Inspection.explain's header line reflects the same distinction, not just the buried `error:` line it already prints
- [x] #3 No new State enum member — checked with advisor: avoid touching decide()/resolve_target and the paper's theorems in test_invariants.py for a reporting-only change
- [x] #4 cordis/tests/test_invariants.py passes unchanged
- [x] #5 A test exercises describe()/status() and explain() against a fiber whose background work actually failed (via background_step/idle()), not a synthetic fiber.error assignment
- [x] #6 scripts/arch-check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Shape decision (per task's own framing and advisor's earlier note on 0004): use a describe-string, not a new State. A truly ACTIVE fiber whose background work died is detectable as `fiber.state is State.ACTIVE and fiber.error is not None` — FAILED is terminal (decide(): "never retried as this fiber"), so an ACTIVE fiber with a set error can only mean its background work failed after activation, not a setup/teardown failure (those transition through FAILED or reset via a fresh fiber).

1. cordis/src/cordis/loader.py `describe()`: add a branch before the plain `Live(fiber=fiber)` case: `Live(fiber=fiber) if fiber.state is State.ACTIVE and fiber.error is not None: return f"active, work failed: {fiber.error!r}"`. This also fixes bhh's `_raise_if_stalled` for free: `_is_stalled` does exact string comparison against "active", so the new string is correctly treated as stalled without touching bhh/src/bhh/bootstrap.py.
2. cordis/src/cordis/inspection.py `explain()`: change the header line to say the same thing when this condition holds, so the two surfaces (loader.describe, Inspection.explain) agree instead of only the buried `error:` line hinting at it.
3. Test: mount a component that does `yield background(failing_coro())`, await `rt.settle()` then wait for the background task to fail and be recorded (no need to call idle()), assert `describe`/`status()` says "active, work failed: ..." and `explain()`'s header says the same.
4. Run test_invariants.py to confirm no behavioral drift (no state machine change expected, but verify).
5. scripts/arch-check.

Out of scope: bhh/src/bhh/bootstrap.py's `_raise_if_stalled`/`_is_stalled` do not need code changes since the fix is transparent to them (confirmed by reading their exact-string-equality check), but will be covered by the existing bhh test suite passing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented as planned: loader.describe() and Inspection.explain() both say "active, work failed: {error!r}" for a Live/ACTIVE fiber whose fiber.error is set (background work died), instead of plain "active". No new State — confirmed via test_invariants.py (360 passed, unchanged).

Advisor caught a real regression before I marked this done: fiber.error was never cleared at the top of _lifetime, so "active, work failed" was STICKY — a fiber whose background work died, then reloaded cleanly on a dependency change, would report work-failed forever, and since _is_stalled does exact-string comparison against "active", this would make bhh's _raise_if_stalled("stopped early") kill a healthy composition. Fixed with one line: fiber.error = None at the top of _lifetime's loop, alongside the existing committed/performed resets (a fresh setup starts clean). Added test_a_stale_background_failure_does_not_survive_a_reload in test_runtime.py to pin it.

Advisor also flagged AC #5 was only tested via describe(Live(...)) with a hand-built Live/Entry, not through the real Loader.status() that bhh actually calls. Added test_loader_status_reports_active_work_failed_through_a_real_row in test_loader.py using a real boot()ed composition (module-level _boom_worker component resolved via module:attribute) asserting booted.loader.status()['worker'] directly.

Docs updated per the same discipline as task-0004: cordis/README.md's Fiber concept now describes the sticky-but-cleared active/work-failed status string; bhh/src/bhh/bootstrap.py's run() docstring now mentions loader.status() marking the row so _raise_if_stalled catches it even without going through idle() first.

Final verification: full suite 534 passed, test_invariants 360 passed, mypy clean, scripts/arch-check clean, ruff format/check clean. Task complete.

Correction (task-0008): the claim below that this "fixes bhh's _raise_if_stalled for free" turned out to be wrong in one direction — treating "active, work failed" as a stall in _raise_if_stalled's could-not-start/stopped-early gate caused a real regression (a fast Recoverable failure racing and getting misreported as a CompositionError instead of propagating normally). task-0008 changed bhh's `_is_stalled` to exclude "active, work failed" from what it considers stalled. The status string itself (this task's actual deliverable, in describe()/explain()) is unaffected and still correct.
<!-- SECTION:NOTES:END -->
