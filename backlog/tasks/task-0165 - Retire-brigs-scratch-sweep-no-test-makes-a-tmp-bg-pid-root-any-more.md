---
id: TASK-0165
title: 'Retire brig''s scratch sweep: no test makes a /tmp/bg<pid> root any more'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 23:15'
updated_date: '2026-10-19 00:30'
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
- [x] #1 The sweep, its helper module, its unit tests and the --sweep-aged option are removed, or the notes say why they stay
- [x] #2 scripts/check libs/brig passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Grep confirms no test or helper makes a /tmp/bg<pid> root (the only f-string is conftest's spawn registry FILE /tmp/bg<pid>-spawnreg, which predicate 3 spared; the sweep never removed it). The static guard tests/unit/test_no_test_names_a_directory_from_its_pid.py already refuses a new pid-named path. 2. Delete libs/brig/tests/scratch_sweep.py and tests/unit/test_scratch_sweep.py; delete _scratch_sweep and pytest_addoption (--sweep-aged) from tests/conftest.py; reword the _JAIL_DIR_PREFIX comment that cites the sweep. 3. SPEC.md/WORKFLOW.md/README.md do not describe the scratch sweep (WORKFLOW's 'leak sweep' is the process sweep, a different thing, kept), so no spec change. 4. Proof: uv run pytest libs/brig -m unit (and the guard test, test_jail_dir_fixture), grep for leftovers, then scripts/check libs/brig. Risk: conftest imports (time/Iterator) still used elsewhere; ruff will say.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Retired the scratch sweep. Removed libs/brig/tests/scratch_sweep.py, libs/brig/tests/unit/test_scratch_sweep.py, and from libs/brig/tests/conftest.py the session-scoped autouse _scratch_sweep fixture and pytest_addoption (--sweep-aged); reworded the _JAIL_DIR_PREFIX comment that cited the sweep. Evidence no test makes a /tmp/bg<pid> root: grep of libs/brig/tests, bh-02, scripts for prefix="bg" / /tmp/bg followed by a pid expression finds only conftest's spawn registry path f"/tmp/bg{harness_pid}-spawnreg" (a file). Every other mkdtemp prefix is bg- / bg-oci- / bg-else- / bg-outside- (a dash after bg, outside predicate 2 arm a), and tests/unit/test_no_test_names_a_directory_from_its_pid.py (kept) refuses a new test that names a path from getpid(), so the sweep is not the net for a future one either. Spawn registry: /tmp/bg<pid>-spawnreg is untouched; the sweep never removed it (predicate 3 spared it, it is a file) and nothing else does, so it stays as it was. Docs: SPEC.md, WORKFLOW.md, README.md, MILESTONES.md do not describe the scratch sweep or cite decision-121 (WORKFLOW.md's 'leak sweep' is the /bin/ps process sweep, a different fixture, kept), so no spec text changes and no new decision (test-only change). Runs: uv run pytest libs/brig/tests/unit + test_jail_dir_fixture.py -n auto: 1035 passed, 3 skipped, and /tmp/bg* listing identical before and after; uv run pytest libs/brig/tests/unit -q --sweep-aged now exits with pytest's unrecognized-argument usage error (option gone); scripts/check libs/brig exit 0 (1368 passed, 111 skipped; format, lint, mypy, gates, docs ok). Nothing to plant: this removes a fixture rather than adding a gate.
<!-- SECTION:NOTES:END -->
