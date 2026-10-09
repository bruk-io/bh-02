---
id: TASK-0058
title: Split the kernel plugin into a python plugin and a runner plugin
status: To Do
assignee: []
created_date: '2026-10-09 00:36'
labels:
  - kernel
  - brig
  - memory
dependencies:
  - TASK-0056
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The kernel plugin mixes two concerns. One is the python tool: the persistent Python process and the `python` tool that sends it inputs. The other is running code at all: `kernel:approval` (whether the model's code runs unasked), `kernel:unjailed` (an unconfined runner) and `kernel:release`, while the brig plugin's `brig:jail` is the confined runner. The owner and the glossary agreed the terms (Python process, input, runner, confined and unconfined) and the names: the python tool's component is `python:tool` (`python:python` reads oddly), the runners are `runner:confined` (brig behind it) and `runner:unconfined`, and `memory:memory` becomes `memory:files` for the same reason. With the tools broker (TASK-0056) in place, the python row only registers its tool, so nothing outside the plugin reaches the Python process.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A python plugin offers `python:tool`: the Python process and the `python` tool, registered with `tools`; the kernel plugin is gone
- [ ] #2 A runner plugin offers `runner:confined` (brig), `runner:unconfined`, `runner:approval` and `runner:release`, bound under `runner` and `approval`; only the runner plugin imports brig
- [ ] #3 `memory:memory` is `memory:files`
- [ ] #4 `/release` still stops the Python process and its jail until the next input, and the status bar reads the jail's grades from the runner
- [ ] #5 `bh-02 update-layer` and a resumed session translate every old name (`kernel:*`, `brig:jail`, `memory:memory`, and rows that name the `kernel` and `jail` keys), saying what changed
- [ ] #6 The gates' rules and lists that name the old packages (`brig-one-adapter`, `worker-stdlib-only`, the purity budget, the allow lists) name the new ones, and bh-02/CLAUDE.md, CONTRACTS.md, GLOSSARY.md, the READMEs and the docs site use the new names
<!-- AC:END -->
