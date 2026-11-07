---
id: TASK-0199
title: The runner's interpreter-deny tests build their fixture on darwin
status: To Do
assignee: []
created_date: '2026-11-07 04:27'
labels:
  - runner
  - darwin
  - tests
  - size-1
dependencies: []
priority: medium
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-0079.34's re-run (macOS 27.0.1, 2026-11-06), with and without Claude Code's sandbox: test_runner_confined.py's test_a_jail_denies_the_interpreter_bh_02_runs_on_when_it_lies_in_the_project, test_a_jail_denies_the_directory_of_each_link_from_the_interpreter_bh_02_runs_on_to_its_file and test_the_walk_to_the_interpreter_follows_relative_links_and_dots_and_ends_at_a_loop fail in their fixture: shutil.copy2 of the uv Python into the project raises PermissionError EPERM (copystat's flags; a plain copy2 to a fresh temp dir works). No jail starts, so the denies they guard are untested on darwin. TASK-0169.04's notes called these 'host sandbox' failures; they are not.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The three tests build their interpreter on darwin and pass; each still fails if the deny it guards is removed (seen failing)
- [ ] #2 The runner plugin's tests pass on macOS and Linux
<!-- AC:END -->
