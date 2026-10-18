---
id: TASK-0166
title: >-
  Remove the directories brig's other tests leave in /tmp: bg-sv-<8> from
  tests/supervised_jail.py first
status: To Do
assignee: []
created_date: '2026-10-18 23:15'
labels:
  - brig
  - size-2
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while fixing TASK-0151. tests/supervised_jail.py::new_jail_dir makes tempfile.mkdtemp(prefix='bg-sv-', dir='/tmp') and nothing removes it: two new /tmp/bg-sv-<8> directories (each with jail.json, procs/, chan/, supervisor/) per integration+e2e run, measured by listing /tmp before and after one run on this machine. Other tests make a random directory the same way and were not checked here (the docker and darwin ones cannot run on this machine): e2e/test_process_namespaces.py and e2e/test_supervised_jail.py (bg-ws-), integration/test_channel_planted_link.py (bg-plant-, bg-outside-), integration/test_bwrap_jail_dir_sealed.py (bg-seal-), integration/test_oci_runtime.py, test_oci_flags_in_effect.py and tests/oci_jail.py (bg-oci-*). They are not a reuse hazard (the names are random) but they fill /tmp. Give each a fixture that removes it, or conftest's new_jail_dir where the directory is a jail directory.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After one run of 'uv run pytest libs/brig -m "integration or e2e" -n auto --dist loadgroup', /tmp holds no directory the run made (compare ls -A /tmp before and after)
- [ ] #2 scripts/check libs/brig passes
<!-- AC:END -->
