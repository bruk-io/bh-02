---
id: TASK-0099
title: 'Names in bh-02 say what they name, by one written rule'
status: To Do
assignee:
  - '@bruk'
created_date: '2026-10-14 15:56'
updated_date: '2026-10-14 16:40'
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
- The gates: renames go through `pypeeker rename` where it applies (`demote` only makes a name private); `scripts/check` passes after each.

## Open questions
- [x] The rule: answered by Fable for the owner (2026-10-14): a plugin is named for its subject; a component for what it is, read after the plugin's name (`commands:registry`, `models:catalog`, `agent:tools`), never repeating its plugin; a row id for the one key it binds, else its role (as CONTRACTS.md already says). When a broker's key is the plugin's own name, the component names the kind (`registry`), so stutters vanish by the rule. One word, one thing; a thing seen from two places keeps its word with a label saying where. Why: a layer author reads `id` and `use` and should know what fills the role without opening the plugin.
- [x] The sub-agents plugin: `subagents` (package `subagents_cordis_plugin`; GLOSSARY.md already says sub-agent). The row id `agents` stays (the person's word: `/agents`, `agents: N running`, `clear` lists, the row's own `rows` config). `:status`, `:child`, `:output` keep their names; `agents:agents`'s new component name is for TASK-0099.01 (Fable's lean: `subagents:parent`, pairing with `child`). The row id `agents_status` becomes `agents-status`, the one two-word id with an underscore.
- [x] The startup files: `startup.py` (`~/.config/bh-02/startup.py`, `.bh-02/startup.py`): Python's own word (`PYTHONSTARTUP`), the config key is already `startup`, the GLOSSARY term already 'startup file'. The python row's class: `PythonProcess`, config `PythonProcessConfig`. worker.py keeps its name (the gates name it; the model never sees it); its private `_Kernel` and `__kernel__` are TASK-0099.02's call.
- [x] GLOSSARY.md's double meanings: no new words; each (`tools`, `python`) is one thing seen from two places and already carries its label. The rule writes that down.
- [x] The old startup-file name keeps working for good, as `outdated._RENAMED` does: when `startup.py` is absent and `kernel.py` is there, run it and say the new name once per REPL start. No expiry, no refusal.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One naming rule is written in bh-02/CLAUDE.md, with the reason for it; GLOSSARY.md carries the renamed terms
- [ ] #2 No two plugins' names differ by a letter, no component repeats its plugin's name, and no GLOSSARY.md term has two meanings without a label saying which
- [ ] #3 Every old row id, component and startup-file name a person may have is translated or still read, saying what changed; scripts/check passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted 2026-10-14 by Fable standing in for the owner (he delegated these decisions): open questions answered above; AC #1 keeps the rule in one place (bh-02/CLAUDE.md), AC #2 says 'no component repeats its plugin's name' (agents:agents is a component; no row id stutters). Added to the sweep: the row id agents_status, the one two-word id with an underscore. TASK-0099.01 starts now.

TASK-0099.01 wrote decision-0005 (proposed, awaiting the owner): the rule, subagents:parent, the sweep, the rename table. It filed TASK-0099.04 (extensions:extensions to extensions:process) and TASK-0099.05 (the rule into bh-02/CLAUDE.md, after .02, .03 and .04), and added to .02 and .03.
<!-- SECTION:NOTES:END -->
