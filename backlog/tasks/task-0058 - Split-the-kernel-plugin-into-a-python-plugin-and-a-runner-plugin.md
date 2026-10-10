---
id: TASK-0058
title: Split the kernel plugin into a python plugin and a runner plugin
status: Done
assignee: []
created_date: '2026-10-09 00:36'
updated_date: '2026-10-09 14:30'
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
- [x] #1 A python plugin offers `python:tool`: the Python process and the `python` tool, registered with `tools`; the kernel plugin is gone
- [x] #2 A runner plugin offers `runner:confined` (brig), `runner:unconfined`, `runner:approval` and `runner:release`, bound under `runner` and `approval`; only the runner plugin imports brig
- [x] #3 `runner:approval` is the rule alone, depending on the runner alone: whether a call that runs in the runner runs unasked (confined) or must be put to the person. Asking (`output.confirm`) is not part of it. The python tool reads that rule rather than computing `confined` itself, so one place decides what runs unasked
- [x] #4 Each owner holds its own start: the python row starts and stops its Python process, the extensions row its worker. `runner:release` notifies them (a registration each), and each stops its own process; the runner never kills another row's process, and a release ends with the next start whichever owners there are
- [x] #5 The runner reports the grades of each start it makes. The jail field in the status bar is a row of its own over the runner, apart from the session and model fields, so it neither reloads on `/clear` nor shows stale grades after the Python process restarts in place; the frame's keep-and-grace code is deleted
- [x] #6 `memory:memory` is `memory:files`
- [x] #7 `/release` still stops the Python process and its jail until the next input, and the extensions load again after it
- [x] #8 `bh-02 update-layer` and a resumed session translate every old name (`kernel:*`, `brig:jail`, `memory:memory`, and rows that name the `kernel` and `jail` keys), saying what changed
- [x] #9 The gates' rules and lists that name the old packages (`brig-one-adapter`, `worker-stdlib-only`, the purity budget, the allow lists) name the new ones, and bh-02/CLAUDE.md, CONTRACTS.md, GLOSSARY.md, the READMEs and the docs site use the new names
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- `python-cordis-plugin` (was kernel's): `python:tool` fills the `python` row and binds no key. `Kernel(runner, config, access, *, rule)` reads `confined` from the `approval` rule; `stopped()` (was `release()`) stops only its own Python process, refusing while an input runs. The row acquires `runner.on_release(stopped)`, `tools.register(python)` and `system.add("python")`.
- `runner-cordis-plugin` (was brig's, plus kernel's `unjailed`, `approval` and `release`): `runner.Runner` over a mechanism (`BrigJail`, `Unjailed`): `start`, `report`/`notice` of the last start, `on_start`, `on_release`, `release`, `released`. `/release` asks each owner's stop, then the mechanism's `release`, which no longer stops anything: it waits for a start under way, sweeps, and says what is free, what another session holds, and whether a program its owner did not stop still runs. A start ends a release.
- `runner:approval` binds `Approval(runner)`: `confined` and `unasked(request)`, depending on `runner` alone. Asking moved to the askers: `agent.loop.Asked(rule, output)` for the loop, `rule.unasked or output.confirm` in the extensions host.
- Extensions: injects `runner`, `approval`, `output`; `Extensions.stopped()` is its `/release` stop; a change while released starts a worker (ending the release), an unchanged directory waits for the next start. `extensions_cordis_plugin.testing.PlainJail` is now a mechanism tests wrap in `Runner`.
- TUI: `tui:grades` (`GradesField`) is the jail field, over `runner` (`report`, `on_start`) and `approval` (`confined`), its notice told once per new text; `tui:status` shows session and model only. The frame's keep-and-grace (`RowsUp`, `settling`, `Frame.release`, `held_after`) is deleted.
- `memory:memory` is `memory:files`.
- `update-layer`: ids `kernel`->`python`, `jail`->`runner`, `jail_status`->`grades`; uses `kernel:*`, `brig:jail`, `memory:memory`, `tui:jail_status`; a `clear` naming `kernel` names `python`. Tested in `test_outdated_layers.py`.
- Gates: `brig-one-adapter` names `runner_cordis_plugin`, `worker-stdlib-only` `python_cordis_plugin.worker`, the budget and allow lists the new modules.
- Found on the way, committed separately (e474301): CPython 3.15's `Process.wait()` waits for the pipes to close, so a `!COMMAND` leaving a background program holding its output waited for it; `shell_command` now watches the return code.
<!-- SECTION:NOTES:END -->
