---
id: TASK-0081
title: >-
  Let scripts/check collect on Linux: warden-systray's tests import rumps, which
  installs only on darwin
status: To Do
assignee: []
created_date: '2026-10-11 15:58'
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
- [ ] #1 On Linux, scripts/check's tests step collects every member, with the systray tests skipped by name (not erroring) where rumps is absent
- [ ] #2 On darwin the systray tests still run
<!-- AC:END -->
