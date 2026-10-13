---
id: TASK-0087
title: Let the models file name the default model
status: To Do
assignee: []
created_date: '2026-10-13 22:33'
labels:
  - models
  - size-2
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Asked by the owner (2026-10-13), who runs a local OpenAI-compatible server and wants new sessions on it without a flag. Today the model row's default is 'sonnet' unless a layer or --model names another (models_cordis_plugin/named.py: the row config's default), and ~/.config/bh-02/models.toml has no default key. The workarounds are poor: a shell alias; naming a model 'sonnet' to replace the built-in; or a --patch layer setting the model row's config, which replaces the whole config and stops /model from switching. Wanted: a top-level default = "NAME" in the models file. Precedence, lowest first: the built-in 'sonnet', the models file's default, a layer's model row default (a session's own layer, which /model and --model write), --model. So a resumed session keeps the model it was on, and /model and --model still switch. The default chooses the spend, so it is read only from the models file in host.trusted, as model tables are, never from the project.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A top-level default = "NAME" in the models file chooses the model a new session starts on when neither --model nor a layer names one; a resumed session keeps its own; /model and --model still switch
- [ ] #2 A default that names no model, or is not a name, is said with what to write (the house style for models-file problems), and bh-02 still starts; a test of each
- [ ] #3 /model's list marks which model is the default and where that came from (built-in or models file)
- [ ] #4 docs/bh-02/using/models.md and the models plugin's README describe it; scripts/check passes
<!-- AC:END -->
