---
id: TASK-0041
title: Don't read a models file the model's code can write
status: Done
assignee: []
created_date: '2026-10-07 03:05'
updated_date: '2026-10-07 03:05'
labels:
  - models
  - security
dependencies: []
references:
  - 'https://github.com/bruk-io/bh-02/pull/8'
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A models.toml table can point an openai model's `key` (a local.env line) at any `base_url`, and bh-02 sends it from its own process. When the models file is inside the project the jail lets inputs write (bh-02 run from the home directory, XDG_CONFIG_HOME in the project, or a link into it), the model could send a credential to a server of its choosing.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A models file inside the project, as named, as resolved, or through any directory or link on the way, is not read; `/model`, the catalog and the step error say why and where it must live
- [x] #2 The built-in models and the model row's `extra` keep working
- [x] #3 An openai model's `key` may not name `CLAUDE_CODE_OAUTH_TOKEN`
- [x] #4 Tests use temporary directories and fake local.env lines only
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed in dc76e77 (models_cordis_plugin.named in_project/withheld, Catalog.problem); tests/test_models_file_trust.py. Verified on branch ccr-934e6775-vdsnnr: ruff, mypy and scripts/arch-check clean; pytest bh-02 libs/cordis-helpers -m 'not real_launch' 560 passed (brig jail tests deselected, they fail in a Linux container); real-launch tests 24 passed (test_the_terminal_going_away_leaves_and_ends_the_kernel fails on main in this container too).
<!-- SECTION:FINAL_SUMMARY:END -->
