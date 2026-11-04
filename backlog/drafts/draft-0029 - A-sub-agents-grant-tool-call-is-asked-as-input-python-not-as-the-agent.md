---
id: DRAFT-0029
title: A sub-agent's grant tool call is asked as 'input python', not as the agent
status: Draft
assignee: []
created_date: '2026-11-04T22:39:00Z'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
requesting.ASKER is fixed at Asker(Source.INPUT, "python") (bh-02/plugins/runner-cordis-plugin/src/runner_cordis_plugin/requesting.py:21) and wiring.grant_prompt always uses it (wiring.py grant()). TASK-0181.08 labels a sub-agent's needs and refused connections as the agent (python config agent, runner.start(agent=)), but a grant() call from a sub-agent's input reaches the person as 'Asked by: input python', so the person cannot tell which agent asks. Found in review of TASK-0181.08.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A grant() call from a sub-agent's input is asked as that agent, by its label
- [ ] #2 A test shows the label on the question
<!-- AC:END -->
