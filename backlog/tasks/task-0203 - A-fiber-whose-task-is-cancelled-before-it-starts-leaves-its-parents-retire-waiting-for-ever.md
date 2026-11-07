---
id: TASK-0203
title: >-
  A fiber whose task is cancelled before it starts leaves its parent's retire
  waiting for ever
status: To Do
assignee: []
created_date: '2026-11-07 04:50'
updated_date: '2026-11-07 04:54'
labels:
  - cordis
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in TASK-0202 (2026-11-06, macOS, Python 3.15.0rc2). When every task on a loop is cancelled at once (asyncio.Runner.close, pytest-asyncio's loop teardown) while a composition is mid-boot, one task survives: a parent fiber's undo awaits Fiber.retire -> settled -> shield(child.inertia), and no task is left to resolve that inertia. _live resolves it in its except CancelledError, but a task cancelled before its coroutine first runs never enters that try, so _end_transition never happens. Repro before TASK-0202's bh_02.run fix: a test that does wait_for(run([*layers(), patch]), 0.02) with test_booting's interactive heartbeat patch hung in teardown at asyncio/runners.py _cancel_all_tasks (faulthandler dump); dumping tasks after cancelling them all left only Task-2 at runtime.py:99 settled via retire (runtime.py:119) from an undo (_run, runtime.py:373). TASK-0202 removed the trigger in bh_02.run (it now shuts the runtime down when cancelled mid-boot); cordis itself still hangs whoever cancels its tasks that way.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A cordis test cancels every task of a runtime mid-transition (some before their first step) and the loop's shutdown ends; seen hanging before the fix
- [ ] #2 test_invariants.py passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Same trigger shape elsewhere (found while closing TASK-0202, not changed there): examples/warden/app/src/warden/bootstrap.py awaits boot() (line 84, via _boot) before _serve's unwinding begins, so a warden run cancelled mid-boot leaves its runtime's rows on the loop as bh_02.run did.
<!-- SECTION:NOTES:END -->
