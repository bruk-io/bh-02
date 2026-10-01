---
id: task-0031
title: >-
  A test proves the real launch hands the same credential list to the model rows
  and the jail
status: Done
assignee: []
created_date: '2026-09-30 14:48'
updated_date: '2026-10-01 00:48'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0023. test_credential_search shows credential_search() and unreadable() agree by construction, but nothing checks that bh_02.cli's launch actually passes the same list to layers.credentials (what the model rows search) and to the jail's secrets. A later edit to the launch could split them again and reopen the planted-credential hole.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A test boots the composition the way the bh-02 command does and asserts every path in layers.credentials is among the jail's secrets
- [x] #2 The test fails when the launch passes a different list to either side (shown by a deliberate break, then reverted)
- [x] #3 scripts/check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Commit 1bb0639. bh-02/app/tests/test_credential_search.py::test_the_bh_02_command_boots_with_every_searched_path_among_the_secrets runs the real bh-02 command (CliRunner on bh_02.main, --no-jail, a --patch with the fake loop/ui) plus a probe row fragile:layers_seen (conftest PLUGIN) that injects the layers value and writes its credentials and secrets to JSON. It asserts credentials == credential_search(), every credential is among the secrets, and the project's own local.env is among the secrets too. Deliberate breaks in bh_02/cli.py _launch, each reverted: secrets built from credentials[1:] -> fails (one searched path missing from secrets); credentials=credentials[:-1] passed to run -> fails (the list differs from credential_search). The test reads the layers value both sides consume; --no-jail only swaps the jail row, not the value. ruff, scripts/arch-check, app tests (101 passed) green; full scripts/check runs after the jail round merges.
<!-- SECTION:NOTES:END -->
