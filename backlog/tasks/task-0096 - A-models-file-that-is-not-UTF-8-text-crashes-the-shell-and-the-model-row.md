---
id: TASK-0096
title: A models file that is not UTF-8 text crashes the shell and the model row
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-14 13:05'
updated_date: '2026-10-17 04:18'
labels:
  - models
  - size-1
  - finish-moved
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
- [x] #1 sessions.create records no model for it and bh-02 starts; the shell-and-row contract test in test_session_dirs.py has a case of it and fails if either side crashes or they disagree
- [x] #2 scripts/check passes
- [x] #3 A models file that is not UTF-8 text is the model row's ModelsError saying what to do (fix it or remove it), never a traceback, and bh-02 starts
- [x] #4 docs/bh-02/using/models.md says which new sessions list as 'default' in bh-02 sessions (a default that is not a name, an unreadable file) and that one whose default names no model lists by that name; the models plugin README says which roots the shell and the row each check the models file against, as the code does
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Red first: add a non-UTF-8 models file to the contract test (test_session_dirs.py _CONTRACT, bytes support in _placed) and to test_models_broken_file.py _UNREAD; run them, keep the tracebacks (UnicodeDecodeError out of read_models and create).
2. Fix read_models (named.py): catch UnicodeDecodeError with the OSError wording, kind models_file, 'is not UTF-8 text; fix it or remove it'.
3. Fix sessions.create (only the read's except clause, plus the type of the local that carries the error and _pinned's parameter/case): UnicodeDecodeError is an unreadable file, records no model, stack 'default'.
4. Docs: docs/bh-02/using/models.md (which new sessions list as default: not a name, no default, not TOML, key that is no table, unreadable incl. not UTF-8, in the project; a default naming no model lists by that name, and fix the 'such a session ... as default' sentence that is wrong for that case) and the models README (not-UTF-8 in the unreadable-file lines; shell roots = working dir + the session's cwd, row roots = working dir + the model row's cwd; the shell has no layer cwd).
5. Proof: pytest on the two test paths; scripts/check bh-02/plugins/models-cordis-plugin (with docs), scripts/check bh-02/app --no-gates --no-docs; arch-check only if outside a member (docs and tests are inside members; mkdocs docs check is in scripts/check). Tick criteria only with evidence; criterion 2 is scripts/check at root, which I do not run, so leave it for the reviewer unless member checks cover it.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Deferred by the owner (2026-10-15): this run fixes only critical bugs; this one is not critical (no data loss, no security exposure, a workaround exists). Not to be started without the owner's word.

Orchestrator, 2026-10-17: finish moved before work started. Criterion 1 said the built-in models stay usable (/model sonnet switches); TASK-0104 removed built-in models (owner's call: no built-ins, no backwards compatibility), so with an unreadable file there is no model until it is fixed. Criterion 1 is now the error alone, and is listed last after the edit (the CLI appends).

Worker report (wt-0096, starting commit 2fd63fa). Machine shared with three other workers, so no timings are recorded.

What changed: models_cordis_plugin/named.py read_models: UnicodeDecodeError -> ModelsError("models_file", "the models file PATH is not UTF-8 text; fix it or remove it"). bh_02/sessions.py: create's read catches (OSError, UnicodeDecodeError) and records no model (stack default); _pinned's parameter and case take UnicodeDecodeError too; create's local `file` annotation widened (nothing else in create). Tests: test_session_dirs.py _CONTRACT gains "not UTF-8 text" (a UTF-16 file with a BOM, FF FE); _placed writes bytes. test_models_broken_file.py _UNREAD gains "not UTF-8 text" (_file writes bytes). Docs: docs/bh-02/using/models.md (which new sessions list as default; the old "such a session is listed as default" sentence was wrong for a default that names no model, which lists by that name; not-UTF-8 added to the unreadable-file sentence); models plugin README (shell and row roots; not-UTF-8 in the two lists).

Planted check (seen failing before the fix, pytest -k "UTF or utf or not_utf or a_file_that_can_not_be_read or shell_and_the_model_row or status_bar"): 4 failed, all UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff. Row side: named.py read_models via providers.known. Shell side: sessions.py:223 in create (the contract test). After the fix the same selection: 30 passed.

Proof commands:
- uv run pytest bh-02/plugins/models-cordis-plugin bh-02/app/tests/test_session_dirs.py -q: 389 passed, 2 skipped.
- scripts/check bh-02/plugins/models-cordis-plugin (gates and docs): exit 0; format, lint, types, tests 352 passed 2 skipped, gates ok, docs built ok.
- scripts/arch-check --no-fix (docs changed outside a member): exit 0, every gate ok.
- scripts/check bh-02/app --no-gates --no-docs: exit 1 both times. Each failure is test_python_repl.py::test_a_jailed_input_cannot_plant_a_credential_where_the_model_row_looks (its project-listing assertion, under the jail-lock group). Re-run alone: passed (4 of 4 runs). The direct command uv run pytest bh-02/app/tests -q -n auto --dist loadgroup passed with the change (241 passed, 1 skipped) and at the starting commit (240 passed, 1 skipped). Run of scripts/check bh-02/app at the starting commit: exit 1 on a different load-sensitive pty test (test_real_launch.py::test_keys_typed_as_the_modal_comes_up_do_not_answer_it). So this command is not green on this shared machine, with or without the change. The cause of the jail test's failure under scripts/check was not found.
- Real start (a pty driver, scratch models file, non-UTF-8, outside the project): with the change bh-02 is ready, the status bar reads "model: default (unusable)", a message answers "error: the models file ... is not UTF-8 text; fix it or remove it", no traceback, Ctrl-Q exit 0. At the starting commit the same start exits 1 with a traceback from sessions.create (sessions.py:223).

Criteria: 1 and 4 are ticked. 2 is left for the reviewer (scripts/check at root not run; app member check not green here, see above). 3 is left unticked: the criterion says the shell uses "the working directory and the layer's cwd". The code does not do that. create is given the CLI's working directory and uses it plus os.getcwd(), and a layer's cwd composes after create (a --patch that sets the model row replaces the session's whole, pins_model). The README now says what the code does. The reviewer should decide whether the criterion's wording is amended.

Orchestrator, 2026-10-17: finish moved again, on the docs criterion. It asked the README to say the shell and the row both use the working directory and the layer's cwd as roots; the worker found the shell does not (sessions.create checks the CLI's working directory with os.getcwd(); a layer's cwd composes after create, and a layer that sets the model row replaces the session's whole, pins_model). Docs say what the code does, so the criterion now asks for the roots each side really checks. Also the owner's word to start, which the 2026-10-15 deferral asked for: "ok wrap up all tasks that you are able to" (2026-10-17).

Full scripts/check on 5cf6e37 (this task's commits with the rest of the batch): exit 0, format, lint, types, tests 3454 passed 50 skipped, five gates, docs (orchestrator, 2026-10-17; log at the session scratchpad, check-batch4b.txt).
<!-- SECTION:NOTES:END -->
