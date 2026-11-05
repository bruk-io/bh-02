---
id: TASK-0194
title: Sub-agents get the grant tool, asking as the agent
status: To Do
assignee: []
created_date: '2026-11-04T22:39:00Z'
updated_date: '2026-11-05T03:52:00Z'
labels:
  - runner
  - subagents
  - size-2
dependencies: []
modified_files:
  - bh-02/plugins/runner-cordis-plugin/src/runner_cordis_plugin/wiring.py
  - bh-02/plugins/runner-cordis-plugin/src/runner_cordis_plugin/requesting.py
  - bh-02/plugins/subagents-cordis-plugin/src/subagents_cordis_plugin/agents.py
  - bh-02/plugins/subagents-cordis-plugin/src/subagents_cordis_plugin/child.py
  - bh-02/app/src/bh_02/bh-02.toml
  - bh-02/app/tests/conftest.py
  - bh-02/CONTRACTS.md
  - bh-02/GLOSSARY.md
  - docs/bh-02/using/jail.md
  - docs/bh-02/how-it-works/jail-and-approval.md
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A sub-agent's conversation is made of the agents row's rows (bh-02.toml: loop, tools, transcript, model, system, asides, access, memory, on-touch, executor, python), and grant-prompt is not among them, so the child's own tools row has no grant tool: a sub-agent's input that calls tools.grant(...) gets an unknown tool, and its system prompt has no grant section. Its standing needs (python config needs) and its refused connections are asked as the agent (TASK-0181.08). To decide: does a sub-agent get grant()? If yes, it must not use requesting.ASKER (Asker(Source.INPUT, 'python'), runner_cordis_plugin/requesting.py:21), which grant_prompt's grant() always uses; the request is asked as the agent, by its label. Found in review of TASK-0181.08 (first filed as the label alone).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A sub-agent has the grant tool and its system section; a call asks the person under the agent's label (agent NAME (TYPE)), never as input python
- [ ] #2 The session's grant tool still asks as input python, and there is still one prompt and one /grants per session
- [ ] #3 The docs and READMEs no longer say a sub-agent has no grant tool, and say a sub-agent's grant applies to the session
- [ ] #4 scripts/check and scripts/linux-jail-check (both modes) pass
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Starts from bbf66ad's successor on bhabtu/quirky-ride-g68g31 (this task's promotion). The owner decided on 2026-11-05 that sub-agents get the `grant` tool.

### Order of work

1. runner plugin, split the tool from the prompt. `runner:grant_prompt` keeps what there is one of per session: `grants.serve(prompt)`, the asides that tell the model what was decided, and `/grants`. A new component, `runner:grant_tool` (wiring.py), registers the `grant` tool (`runs="harness"`) and the `system` section `grants`. It depends on `grants`, `tools`, `system`, `runner` and `approval`, with config `agent: str = ""`. Its asker is `Asker(Source.AGENT, agent)` when `agent` is set and `Asker(Source.INPUT, "python")` otherwise. This replaces the fixed `requesting.ASKER`: a pure `requesting.asker(agent)` returns the asker. A child can't mount `grant_prompt`, because that would serve a second prompt on the one broker the realm exposes. It can mount `grant_tool`, which only asks.
2. bh-02.toml: a `grant` row (`use = "runner:grant_tool"`) beside `grant-prompt`. Add `"grant"` to the agents row's `rows`, so every child has it. It isn't one of the type-grantable `tools`: its only effect is a question to the person, so it widens nothing a type limits.
3. subagents plugin: `AgentsConfig.python_row` becomes `agent_rows: Sequence[str] = ("python", "grant")`. Every row named there that the child has gets the child's label written into its config as `agent` (child.py, agents.py). Breaking the old config key is fine: there's no released format to keep.
4. Tests:
   - runner: `grant_tool` with `agent` set asks as `agent general-1 (general)`. Without it, the tool asks as `input python`. The existing `grant` tool tests move to the new row.
   - subagents: a child's `grant` row config carries its label.
   - app: test_child_boot.py (or the nearest real-composition test) shows a child's tool list includes `grant`, and that a child's `grant` call reaches the person's question labelled with the agent. The `NO_AGENTS` snippet in bh-02/app/tests/conftest.py disables the new `grant` row as well as `grant-prompt`.
5. Docs: CONTRACTS.md (the two components), the runner and subagents READMEs, GLOSSARY (`grant` tool), docs/bh-02/using/jail.md and how-it-works/jail-and-approval.md. Each currently says a sub-agent has no `grant` tool; that line goes, and each says a sub-agent's request shows its label.

### Risks

- A grant a sub-agent gets applies to the whole session (every jail), the same as a need or a refused connection. The question names the agent, so the person decides knowing that. The docs say it.
- The parent's asides still tell the parent model about an answer to a child's request. That's harmless (the grant reaches the parent's jail too) and stays.
- Splitting the row means a layer that mounts `grant-prompt` without `grant` has no tool. The shipped layer mounts both.

### Proof

scripts/check; scripts/linux-jail-check in both modes. Plant a failure: with the child's `agent` not written into the `grant` row, the label test fails (seen, then restored).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner's decision, 2026-11-05: yes, give sub-agents the grant tool.
<!-- SECTION:NOTES:END -->
