---
id: DRAFT-0020
title: Full-suite-only setup ERRORs in host-paths appender and warden tests on darwin
status: Draft
assignee: []
created_date: '2026-11-07 05:00'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
scripts/check on a 28-core Mac (2026-11-07, recorded on TASK-0169.06) reports 25 ERRORs; 17 are brig (TASK-0198), but 8 are in libs/host-paths/tests/test_host_paths_appender.py (3) and examples/warden/** (5). Run alone (-p no:cacheprovider, same files) they all pass (56 passed). The recorded output is truncated so the error text is not visible; the cause under the full parallel run is unknown and no task owns it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The cause of the setup errors under the full run is explained
- [ ] #2 scripts/check on the 28-core Mac shows no ERROR in host-paths or warden tests, or each is filed under the task that owns its cause
<!-- AC:END -->
