---
id: TASK-0099
title: 'Names in bh-02 say what they name, by one written rule'
status: To Do
assignee:
  - '@bruk'
created_date: '2026-10-14 15:56'
labels:
  - naming
dependencies: []
priority: high
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem
The owner (2026-10-14): the naming is hurting my head. A sweep of the shipped composition, CONTRACTS.md and GLOSSARY.md found:
- Two plugins a letter apart for different things: `agent` (the conversation loop, and the brokers it binds: `agent:loop`, `agent:tools`, `agent:system`, `agent:asides`, ...) and `agents` (sub-agents: `agents:agents`, `agents:status`, `agents:child`). About 18 files name the agents package and 12 its rows.
- `kernel.py` is not a kernel: the docs call it the startup file (`~/.config/bh-02/kernel.py`, `.bh-02/kernel.py`, 11 files), and the python row's class is `Kernel`, which GLOSSARY.md admits is 'an older name (not Jupyter's kernel)' (9 files).
- Brokers are named two ways: `agent:tools`, `agent:system`, `agent:asides` for the key they bind, `commands:registry` for what it is.
- Rows that stutter: `agents:agents`, `extensions:extensions`.
- GLOSSARY.md gives one word two meanings: `tools` (the broker row and key; the namespace's view in an input) and `python` (the tool; the row).
- No rule is written down, so each new row picks a style. The last pass, TASK-0064 (done), renamed the names that collided and made `bh-02 update-layer` and a resumed session translate old names; it set the precedent this follows.

## Outcome
One naming rule, written where a plugin author reads it, and the names that break it renamed, so a row's id, a plugin's name and a file's name each say what they name, and no word means two things without saying which.

## Must not break
- A person's layers and a resumed session: every renamed row id and component is translated by `bh-02 update-layer` and on resume, saying what changed (as TASK-0064).
- A person's existing startup file keeps running after it is renamed, with a line saying the new name.
- The model-facing names stay unless the rule needs them changed: the tools `agent`, `agent_wait`, `agent_send`, `agent_stop`, `python` and the commands the person types (`/agents`).
- The gates: renames go through `pypeeker demote` where it applies; `scripts/check` passes after each.

## Open questions
- [ ] The rule: is a row named for what it is, for the key it binds, or for the key when it is a broker? What about stutters?
- [ ] The sub-agents plugin's new name (`subagents`?) and its rows'.
- [ ] The startup files' new name (`startup.py`?), and the python row's class (`Repl`? `PythonProcess`?).
- [ ] Whether GLOSSARY.md's double meanings get new words or a line saying which sense.
- [ ] Whether the old startup-file name keeps working for good or for a release, then is refused with what to rename.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One naming rule is written in bh-02/CLAUDE.md and GLOSSARY.md, with the reason for it
- [ ] #2 No two plugins' names differ by a letter, no row id stutters, and no GLOSSARY.md term has two meanings without saying which
- [ ] #3 Every old row id, component and startup-file name a person may have is translated or still read, saying what changed; scripts/check passes
<!-- AC:END -->
