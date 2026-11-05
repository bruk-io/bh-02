---
id: TASK-0194
title: A sub-agent has no grant tool; if it gets one, it must ask as the agent
status: To Do
assignee: []
created_date: '2026-11-04T22:39:00Z'
updated_date: '2026-11-05T03:52:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A sub-agent's conversation is made of the agents row's rows (bh-02.toml: loop, tools, transcript, model, system, asides, access, memory, on-touch, executor, python), and grant-prompt is not among them, so the child's own tools row has no grant tool: a sub-agent's input that calls tools.grant(...) gets an unknown tool, and its system prompt has no grant section. Its standing needs (python config needs) and its refused connections are asked as the agent (TASK-0181.08). To decide: does a sub-agent get grant()? If yes, it must not use requesting.ASKER (Asker(Source.INPUT, 'python'), runner_cordis_plugin/requesting.py:21), which grant_prompt's grant() always uses; the request is asked as the agent, by its label. Found in review of TASK-0181.08 (first filed as the label alone).
<!-- SECTION:DESCRIPTION:END -->
