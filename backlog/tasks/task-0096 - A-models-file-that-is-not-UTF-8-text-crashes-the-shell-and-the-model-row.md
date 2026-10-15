---
id: TASK-0096
title: A models file that is not UTF-8 text crashes the shell and the model row
status: To Do
assignee: []
created_date: '2026-10-14 13:05'
updated_date: '2026-10-15 02:27'
labels:
  - models
  - size-1
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while building TASK-0093 (probed on e049e4b): a models.toml holding bytes that are not UTF-8 (b'\xff\xfe default = 1') raises UnicodeDecodeError out of BOTH bh_02.sessions.create (Path.read_text(encoding='utf-8'), only OSError is caught) and models_cordis_plugin.named.read_models (same), so bh-02 dies with a traceback at start instead of saying what is wrong with the file. UnicodeDecodeError is a ValueError, not an OSError. Fix: read_models turns it into a ModelsError (kind models_file, what to write: 'is not UTF-8 text; fix it or remove it', which known() now carries behind the built-ins, as for any unreadable file); sessions.create treats it as an unreadable file (records no model, as TASK-0093 does for an OSError). Both sides in the same change, under the app's shell-and-row contract test (test_session_dirs.py), which gains a file of that kind.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A models file that is not UTF-8 text is the model row's ModelsError with what to write, never a traceback, and the built-in models stay usable (/model sonnet switches)
- [ ] #2 sessions.create records no model for it and bh-02 starts; the shell-and-row contract test in test_session_dirs.py has a case of it and fails if either side crashes or they disagree
- [ ] #3 scripts/check passes
- [ ] #4 docs/bh-02/using/models.md says which new sessions list as 'default' in bh-02 sessions (a default that is not a name, an unreadable file) and that one whose default names no model lists by that name; the models plugin README says the shell and the row both use the working directory and the layer's cwd as roots (from TASK-0093's close review)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Deferred by the owner (2026-10-15): this run fixes only critical bugs; this one is not critical (no data loss, no security exposure, a workaround exists). Not to be started without the owner's word.
<!-- SECTION:NOTES:END -->
