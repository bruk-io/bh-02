---
id: TASK-0058
title: Split the kernel plugin into a python plugin and a runner plugin
status: To Do
assignee: []
created_date: '2026-10-09 00:36'
updated_date: '2026-10-09 03:07'
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

Refined by the review against cordis of 2026-10-09 (the separation, duplicates and docs review): three things about running code are tangled today. Approval computes `confined` in two places (`kernel:approval`, and the kernel's own `confined` for what the model is told), and the rule and the asking are one row, which depends on `output`. The jail stops other rows' processes: `/release` kills the extensions worker, which only notices when its socket dies, and without a python tool nothing ever ends a release, so extensions would never load again. And `tui:status` depends on all of `kernel` (and on `models`) for three fields: it reloads on every `/clear`, the frame carries keep-and-grace code only to stop the fields blinking, and it reads the jail's grades once, so a Python process restarted in place never updates them.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A python plugin offers `python:tool`: the Python process and the `python` tool, registered with `tools`; the kernel plugin is gone
- [ ] #2 A runner plugin offers `runner:confined` (brig), `runner:unconfined`, `runner:approval` and `runner:release`, bound under `runner` and `approval`; only the runner plugin imports brig
- [ ] #3 `runner:approval` is the rule alone, depending on the runner alone: whether a call that runs in the runner runs unasked (confined) or must be put to the person. Asking (`output.confirm`) is not part of it. The python tool reads that rule rather than computing `confined` itself, so one place decides what runs unasked
- [ ] #4 Each owner holds its own start: the python row starts and stops its Python process, the extensions row its worker. `runner:release` notifies them (a registration each), and each stops its own process; the runner never kills another row's process, and a release ends with the next start whichever owners there are
- [ ] #5 The runner reports the grades of each start it makes. The jail field in the status bar is a row of its own over the runner, apart from the session and model fields, so it neither reloads on `/clear` nor shows stale grades after the Python process restarts in place; the frame's keep-and-grace code is deleted
- [ ] #6 `memory:memory` is `memory:files`
- [ ] #7 `/release` still stops the Python process and its jail until the next input, and the extensions load again after it
- [ ] #8 `bh-02 update-layer` and a resumed session translate every old name (`kernel:*`, `brig:jail`, `memory:memory`, and rows that name the `kernel` and `jail` keys), saying what changed
- [ ] #9 The gates' rules and lists that name the old packages (`brig-one-adapter`, `worker-stdlib-only`, the purity budget, the allow lists) name the new ones, and bh-02/CLAUDE.md, CONTRACTS.md, GLOSSARY.md, the READMEs and the docs site use the new names
<!-- AC:END -->
