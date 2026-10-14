---
id: TASK-0098
title: >-
  bh-02 --model with a name that is not valid UTF-8 leaves a half-made session
  directory and a traceback
status: To Do
assignee: []
created_date: '2026-10-14 14:06'
labels:
  - app
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while fixing TASK-0094. A --model value from argv bytes that are not UTF-8 reaches bh_02.sessions.create as a str holding a lone surrogate (e.g. 'x\udcff'). cordis's format_layer now refuses it (ValueError: 'a layer can't hold ...: half of a character ... write it in UTF-8'), where it used to write a layer tomllib could not read. create() has already made the session directory and written meta.json by then, so the run dies with a traceback and leaves <session dir>/meta.json with no session.toml (checked 2026-10-14: root/<id>/ holds meta.json only). Same for a resume's --model through sessions.set_model (the layer is rewritten, so there it only raises). Fix where the name enters: refuse it in the CLI (click.UsageError saying the name must be UTF-8) or write the layer before the directory is announced; say which in the task notes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 bh-02 --model <name that is not valid UTF-8> exits with a one-line usage error naming the problem, makes no session directory, and a test shows it
- [ ] #2 a resume with --model and such a name changes nothing and says the same (a test)
<!-- AC:END -->
