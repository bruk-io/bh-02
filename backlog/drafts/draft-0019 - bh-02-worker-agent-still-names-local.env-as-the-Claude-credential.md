---
id: DRAFT-0019
title: bh-02-worker agent still names local.env as the Claude credential
status: Draft
assignee: []
created_date: '2026-11-07 03:41'
labels:
  - agents
  - docs
  - size-1
dependencies: []
priority: low
type: chore
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the reviews of TASK-0169.04 and TASK-0171, not filed then. .claude/agents/bh-02-worker.md:69-70 says 'Never print, log, copy or commit the Claude credential (`local.env`), and never set `ANTHROPIC_API_KEY`.' TASK-0169.04 retired local.env (the token comes from the endpoint's key in models.toml) and TASK-0171 reworded the ANTHROPIC_API_KEY rule (only in the Claude Code CLI child's explicit environment). Both workers left the agent file alone as the owner's configuration, so the next worker is told the old rule.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 bh-02-worker.md states the credential rule as CLAUDE.md now does: the token and API key come from an endpoint's key, reach only the Claude Code CLI child's explicit environment, and are never printed, logged, copied or committed
- [ ] #2 No mention of local.env remains under .claude/
<!-- AC:END -->
