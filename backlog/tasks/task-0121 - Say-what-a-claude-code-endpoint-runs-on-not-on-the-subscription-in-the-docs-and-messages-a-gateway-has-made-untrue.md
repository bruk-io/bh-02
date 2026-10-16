---
id: TASK-0121
title: >-
  Say what a claude-code endpoint runs on, not 'on the subscription', in the
  docs and messages a gateway has made untrue
status: To Do
assignee: []
created_date: '2026-10-16 13:35'
labels:
  - models
  - docs
  - size-1
dependencies: []
priority: low
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0104.02, whose scope was the detached launcher only. Since TASK-0104.01 a claude-code endpoint with base_url and key_command runs the Claude Code CLI against a company gateway with no subscription token, but these still say bh-02 runs Claude on the subscription: bh-02/GLOSSARY.md (about line 51), CLAUDE.md (about line 46), bh-02/app/README.md (about line 4), docs/bh-02/how-it-works/loop.md (about lines 65-66), README.md (about line 128), the models plugin README's intro (about line 343), and a message in bh-02/plugins/models-cordis-plugin/src/models_cordis_plugin/named.py (about line 555). A test name in test_claude_code_credential.py (about line 99) says 'subscription' too: rename it only if it now says something false.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each listed place says what is true with both routes (the subscription token in local.env, or a gateway's base_url and key_command), and git grep for 'on the subscription' outside backlog/ finds only text that is about the subscription route itself
- [ ] #2 No behaviour changes but the message's wording, and its test (if one quotes it) follows; scripts/check for each member touched passes
<!-- AC:END -->
