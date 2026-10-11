---
id: TASK-0081
title: >-
  Let scripts/check collect on Linux: warden-systray's tests import rumps, which
  installs only on darwin
status: Done
assignee:
  - '@claude'
created_date: '2026-10-11 15:58'
updated_date: '2026-10-11 16:41'
labels:
  - warden
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
On Linux, `scripts/check` (and a bare `uv run pytest -q`) stops at collection: examples/warden/plugins/warden-systray-cordis-plugin/tests/test_systray_wiring.py and test_tray.py import warden_systray_cordis_plugin, whose tray.py imports rumps, a dependency declared only for sys_platform == 'darwin'. So the tests step is red on every Linux host before any test runs. Found by TASK-0075's worker, 2026-10-11.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 On Linux, scripts/check's tests step collects every member, with the systray tests skipped by name (not erroring) where rumps is absent
- [x] #2 On darwin the systray tests still run
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Both systray test modules now call pytest.importorskip('rumps') before importing the package. Linux: uv run pytest examples/warden -q -rs gave 13 passed, 2 skipped, each skip named 'could not import rumps'. scripts/check: tests step collected everything (2132 passed, 27 failed, 31 skipped); the 27 failures are bwrap/root/NO_PROXY/zombie environment failures in brig, bh-02 jail tests (test_python_repl, test_runner_confined), not collection errors; gates, docs ok. AC2 unverified here: on darwin rumps is installed so importorskip does not skip, judged from code. Did not plant a failing check (a collection skip, no safety property).

Closed 2026-10-11 by the orchestrator, who did not do the work: criterion 1 re-run (uv run pytest examples/warden: 13 passed, both systray modules skipped by name); criterion 2 judged from the code (importorskip skips only where rumps is absent), darwin unavailable here.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
On Linux the warden-systray tests skip by name where rumps is absent, so scripts/check gets past collection; on darwin they run as before.
<!-- SECTION:FINAL_SUMMARY:END -->
