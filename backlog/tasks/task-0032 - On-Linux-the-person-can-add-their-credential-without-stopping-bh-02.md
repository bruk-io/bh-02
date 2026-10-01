---
id: task-0032
title: On Linux the person can add their credential without stopping bh-02
status: Done
assignee: []
created_date: '2026-09-30 14:48'
updated_date: '2026-10-01 02:33'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-0023. When bh-02 has no local.env at a searched path under the project, a Linux jail holds that path with a read-only placeholder so a cell can't plant one. While the session runs, the person can't create their own credential there either; the session notice says to stop bh-02 first. Adding the credential mid-session should not require quitting.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The person can create their credential file at a held path during a session, through a documented step (e.g. a command that releases the hold and restarts the kernel), without a cell getting a window to plant or read one
- [x] #2 After that step the model row uses the new credential and the jail masks it
- [x] #3 The session notice and README describe the step; scripts/check and scripts/linux-jail-check pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Commits a2f7f70, a08ed8c. New /release command (kernel:release row): ends the kernel's worker and jail now, which removes the placeholders when no other bh-02 jail of the user runs, sweeps what dead jails left, and reports which credential paths are free and which another session still holds. Nothing runs until the next cell, whose new jail either masks the file now there (read and write both refused) or holds the path again, so a cell gets no window. /restart kernel is not the step: it holds the path again at once (shown in the test). The model row with no credential reads the new file at the next message with no restart. A model already running keeps its credential until /restart model, and the answer says so. A running cell is refused (stop the reply first); under --no-jail /release just stops the worker. Docs: session notice, both READMEs, CONTRACTS.md, GLOSSARY.md, bh-02/CLAUDE.md, bh-02.toml. Tests: kernel release tests and test_on_linux_release_frees_where_the_model_row_looks_until_the_next_cell (real bwrap, stand-in credential), red first; released_for/holding unit test written alongside; test_a_credential_added_mid_session_is_read_at_the_next_step pins existing model-row behaviour. Verified after merging into leftovers: scripts/check 1821 passed / 26 skipped, all green; scripts/linux-jail-check 95 passed / 1 skipped; a live bh-02 launch with the default jail answered after a cold start, /model both ways and /clear (2.5-2.6 s), with no jail process left afterwards.
<!-- SECTION:NOTES:END -->
