---
id: TASK-0159
title: 'Say an openai endpoint, not a openai endpoint, in the models file''s errors'
status: To Do
assignee: []
created_date: '2026-10-18 19:28'
labels:
  - models
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in TASK-0158's review. named.py _endpoint_problem builds 'is not a setting of a {provider} endpoint', which reads 'a openai endpoint'. Error messages are part of the product (root CLAUDE.md, Conventions). TASK-0158 added tests that match the full message (test_models_discovery.py _why, test_named_models.py), so they change with it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The models file's errors say 'an openai endpoint' and 'a claude-code endpoint' (the article follows the provider's name), and no other message in the models plugin builds an article before a provider name wrongly
- [ ] #2 The tests that match the message follow it; scripts/check passes
<!-- AC:END -->
