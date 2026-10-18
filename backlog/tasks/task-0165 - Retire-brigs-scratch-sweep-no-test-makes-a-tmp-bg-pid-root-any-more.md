---
id: TASK-0165
title: 'Retire brig''s scratch sweep: no test makes a /tmp/bg<pid> root any more'
status: To Do
assignee: []
created_date: '2026-10-18 23:15'
labels:
  - brig
  - size-2
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0151 moved every brig integration and e2e test to conftest's jail_dir / new_jail_dir fixtures, which make a tempfile.mkdtemp directory (/tmp/bg-<8 random characters>) and remove it after the test. The session-scoped _scratch_sweep fixture in libs/brig/tests/conftest.py (decision-121) sweeps /tmp/bg<harness pid>* roots after the run, takes a snapshot of /tmp before it, and has an --sweep-aged option; nothing makes a root of that name now (its predicate 2 arm a needs the name after bg to start with the pid, and the fixture's names start with a dash), so it lists /tmp twice per worker for nothing. The spawn registry's file /tmp/bg<pid>-spawnreg is a file and was always spared (predicate 3). Decide whether to retire the sweep with tests/scratch_sweep.py, tests/unit/test_scratch_sweep.py and the --sweep-aged option, or to keep it as a net for roots a future test leaves.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The sweep, its helper module, its unit tests and the --sweep-aged option are removed, or the notes say why they stay
- [ ] #2 scripts/check libs/brig passes
<!-- AC:END -->
