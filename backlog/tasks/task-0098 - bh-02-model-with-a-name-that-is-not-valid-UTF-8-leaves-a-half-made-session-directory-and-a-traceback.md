---
id: TASK-0098
title: >-
  bh-02 --model with a name that is not valid UTF-8 leaves a half-made session
  directory and a traceback
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-14 14:06'
updated_date: '2026-10-17 02:32'
labels:
  - app
  - size-1
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while fixing TASK-0094. A --model value from argv bytes that are not UTF-8 reaches bh_02.sessions.create as a str holding a lone surrogate (e.g. 'x\udcff'). cordis's format_layer now refuses it (ValueError: 'a layer can't hold ...: half of a character ... write it in UTF-8'), where it used to write a layer tomllib could not read. create() has already made the session directory and written meta.json by then, so the run dies with a traceback and leaves <session dir>/meta.json with no session.toml (checked 2026-10-14: root/<id>/ holds meta.json only). Same for a resume's --model through sessions.set_model (the layer is rewritten, so there it only raises). Fix where the name enters: refuse it in the CLI (click.UsageError saying the name must be UTF-8) or write the layer before the directory is announced; say which in the task notes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 bh-02 --model <name that is not valid UTF-8> exits with a one-line usage error naming the problem, makes no session directory, and a test shows it
- [x] #2 a resume with --model and such a name changes nothing and says the same (a test)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Deferred by the owner (2026-10-15): this run fixes only critical bugs; this one is not critical (no data loss, no security exposure, a workaround exists). Not to be started without the owner's word.

Fix: refused in the CLI (where the name enters), not in sessions.create: bh-02/app/src/bh_02/cli.py gets a click callback on --model (_model_name) that raises click.BadParameter when the value does not encode as UTF-8, so the usage error (exit 2) comes before read_layers, sessions.create and sessions.set_model. sessions.py is untouched (TASK-0096 edits its models-file read). Tests: bh-02/app/tests/test_command_line.py, _NOT_UTF8 = os.fsdecode(b"claude/\xff") (the argv string for those bytes, 'claude/\udcff'); test_a_model_name_that_is_not_utf8_is_a_usage_error_and_makes_no_session (AC 1) and test_a_resume_with_a_model_name_that_is_not_utf8_changes_nothing (AC 2: snapshot of every file under the state directory is equal before and after). Seen failing first, before the fix: both exit 1 with ValueError "a layer can't hold 'claude/\udcff'", and a plain run left sessions/<id>/meta.json with no session.toml. After: stderr is click's usage block, then the one line: Error: Invalid value for '--model': 'claude/\udcff' is not valid UTF-8; write the model's name in UTF-8. Commands and results: uv run pytest bh-02/app/tests/test_command_line.py -q: 20 passed. uv run pytest bh-02/app/tests -q -m "not real_launch" -n auto --dist loadgroup (under tini, machine shared): 208 passed, 1 skipped (seatbelt test, darwin only), exit 0. scripts/check bh-02/app: exit 0 (format, lint, types, tests 242 passed 1 skipped, gates, docs). The docstring of _model_name was reworded after that run; ruff format --check, ruff check, mypy and the command-line tests were re-run and pass. Dispatched 2026-10-17 by the orchestrator as a size-1 run in worktree wt-0098; the 2026-10-15 deferral above is the owner's, so the merge decision is the orchestrator's.
<!-- SECTION:NOTES:END -->
