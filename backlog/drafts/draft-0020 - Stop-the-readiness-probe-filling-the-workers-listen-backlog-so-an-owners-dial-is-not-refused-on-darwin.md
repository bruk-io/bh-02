---
id: DRAFT-0020
title: >-
  Stop the readiness probe filling the worker's listen backlog, so an owner's
  dial is not refused on darwin
status: Draft
assignee: []
created_date: '2026-11-08 19:35'
labels:
  - runner
  - python
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
scripts/check on main at 61cde05b failed test_a_startup_file_stopped_part_way_is_not_run_again_in_that_repl with 'the REPL could not be started again ([Errno 61] Connection refused)'. Likely cause, not yet shown on the failing test itself: python_cordis_plugin/worker.py main() calls server.listen(1), and the unconfined runner's _until_listening connects and closes as its readiness probe. If the worker has not yet accepted that probe, the owner's next dial in PythonProcess._start finds the backlog full. Measured on this Mac: against a listen(1) Unix socket with no accept, the first connect succeeds and the next three raise Errno 61 at once. Linux was not measured here; the same suites passed in the Linux container. The owner has no retry, so under load a person on darwin would see this error in place of their input running. The probe, the raw dial and listen(1) were all there before bcf17e7c, so TASK-0079.31 did not introduce it. Whether brig's wait_ready followed by Process.connect has the same window on darwin is not checked.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A dial straight after readiness is not refused while the worker has yet to accept the probe, shown by a test that holds the worker's accept back on darwin
- [ ] #2 test_a_startup_file_stopped_part_way_is_not_run_again_in_that_repl passes repeatedly under scripts/check's parallel run on darwin
- [ ] #3 The jailed path (Process.wait_ready then Process.connect) is checked for the same window, and the result said in the notes
<!-- AC:END -->
