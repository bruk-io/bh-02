---
id: TASK-0107
title: >-
  Tell the model of the startup files' functions by progressive disclosure, with
  no decorator (decision-0006)
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-16 02:03'
updated_date: '2026-10-16 03:27'
labels:
  - python
  - size-3
  - finish-moved
dependencies:
  - TASK-0106
references:
  - >-
    backlog/decisions/decision-0006 -
    Tell-the-model-of-the-functions-the-startup-files-define-by-progressive-disclosure-with-no-decorator.md
modified_files:
  - bh-02/plugins/python-cordis-plugin/src/python_cordis_plugin/client.py
  - bh-02/plugins/python-cordis-plugin/src/python_cordis_plugin/worker.py
  - bh-02/plugins/python-cordis-plugin/src/python_cordis_plugin/python.py
  - bh-02/plugins/python-cordis-plugin/README.md
  - bh-02/plugins/python-cordis-plugin/tests/test_python_listing.py
  - bh-02/plugins/python-cordis-plugin/tests/test_python_tool.py
  - bh-02/app/tests/test_python_repl.py
  - bh-02/app/tests/test_model_friction.py
  - bh-02/GLOSSARY.md
  - docs/bh-02/how-it-works/python-tool.md
  - docs/bh-02/using/sessions.md
  - scripts/model-friction
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Build decision-0006 points 1-6 (accepted 2026-10-16). In short: a startup file's public functions (defined in it; exactly __all__'s callables when it has one) are listed by signature in the aside before the first input's output at each REPL start, up to 600 characters across the REPL's startup files in the order they run, the rest by name; help(name) and inspect.getsource are the pulled levels; the python section says the convention, what it costs in context and the docstring convention; @helper, the helper name, __bh_helper__ and the word helper in its startup-function sense go. Supersedes TASK-0100's marking; keeps its data line, cleaning, 160-character cut and identifier rule.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The python section of the system prompt states which functions are told, what they cost (listed every REPL; a leading underscore keeps one untold; a docstring and source cost nothing until asked for) and the docstring convention, and each sentence holds with and without the jail
- [x] #2 @helper, the helper name, __bh_helper__ and the word helper are gone from the code, the model-facing text, GLOSSARY.md and the docs, and a startup file that still says @helper fails at start with a NameError on the startup line
- [ ] #3 scripts/check passes
- [x] #4 At each REPL start the aside lists every told function of the REPL's startup files by signature up to 600 characters across them, in the order they run, and the rest by name, and tests cover __all__ (an imported name included), a private name, a name only imported, and files past the budget
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Order of work
1. Tests first, seen failing against the old source: rewrite test_python_listing.py (pure: the line {"told": [[name, sig|null]]}, shape checks, non-identifier names dropped, the 600 budget threaded as `left`, names only past it, "no public functions"); test_python_tool.py and bh-02/app/tests/test_python_repl.py (real worker: told = public callables the file defines; `__all__` exactly its callables, imported included; a private name; a name only imported; a lambda; a callable instance; an alias of an earlier file's function; a name `__all__` lists that was never bound; two files sharing the budget; `@helper` -> NameError on the startup line; the frame sentences).
2. client.py: `_startup_input` prints {"told": ...}; in the process: `__all__` (list/tuple, new or changed object after the file) -> exactly its callables, else public callable function/method/class not held before the file with __module__ == the namespace __name__. `_BUDGET = 600` beside `_CUT`; `startup_ran(name, when, line, left) -> (aside, left)` threaded through the `_opening` loop (a local, no state on the class); the first miss closes the budget. Aside `PATH ran first: functions a(x); by name only: b`, `no public functions`.
3. worker.py: remove `_helper`, `_HELPER`, the binding, `__bh_helper__`. python.py: `_HELPERS` -> `_TOLD` (confined only) and `_DOCSTRINGS`; the three kinds become own / startup files' / tools; the person's-file sentence reworded. No ruff or mypy mention.
4. Docs: plugin README, python-tool.md, GLOSSARY.md, sessions.md, scripts/model-friction; grep -rni helper bh-02 docs and list what is kept.

### Risks
- The listing line vs the 20,000-character output cap (known limit kept). worker-stdlib-only gate. Purity budget (new functions pure). Docs anchor `#helpers` renamed (strict docs build). The 600 is in the prompt text and in `_BUDGET` (a test ties them). A variable name in `_opening` (`left`) already in use.

### Proof
- Planted violations seen failing (budget, held-before, module clause, routine/class clause, the try/except, the closed budget, the `__all__` identity). scripts/check bh-02/plugins/python-cordis-plugin, scripts/check bh-02/app --no-gates --no-docs, scripts/arch-check (scripts/model-friction changed), tester+tini run of the real bubblewrap tests. The full scripts/check is the reviewer's.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-16: finish moved before any work: the owner set the signature budget to 600 characters (was 1,500, too long) on accepting decision-0006, and the budget spans the REPL's startup files. The word 'helper' goes in its startup-function sense only: brig's jail helpers and credential helpers keep theirs.

Built decision-0006 points 1-6 (supersedes TASK-0100's marking). Files: python-cordis-plugin client.py, worker.py, python.py, README.md, tests (test_python_listing.py rewritten, test_python_tool.py); bh-02/app/tests/test_python_repl.py and test_model_friction.py; bh-02/GLOSSARY.md; docs/bh-02/how-it-works/python-tool.md, docs/bh-02/using/sessions.md; scripts/model-friction (one description string).

Choices (each has a test):
- Which functions are told, decided in the Python process (client._startup_input): a name with no leading underscore whose value is callable, is a function/method/class (inspect.isroutine or isclass), was not an object the namespace held before the file ran, and has __module__ == the namespace __name__. So: def, class and a lambda bound to a public name are told; an import (join, a module, partial) is not; a name bound to what an EARLIER file made (the project's `display = show`) is not told again (the held-before clause is also what keeps a file from re-listing every earlier file's functions); an instance, even a callable one, is data and not told (decision: help/getsource work badly on instances); a value that raises when asked is left alone and the file does not fail. The dis STORE_NAME set and the hidden count are gone.
- __all__: when the file binds it (a list or tuple that is a new object after the file ran, not one an earlier file left), exactly the callables it names, in its order, deduplicated, imported and underscored ones included; a name it lists that the file never bound, and an entry that is no string, tell nothing; a set or string __all__ counts as none (ruff reads only list/tuple).
- Budget: _BUDGET = 600 beside _CUT, counted on signed() text (name(signature), after cleaning and the 160 cut, not the separators). startup_ran(name, when, line, left) -> (aside, left) is threaded through the _opening loop as a local (`spare`), no class state. The first function that does not fit ends the signatures AND closes the budget (0 left): it and everything after it, in that file and the next, is by name only. Past a closed budget a later file's short signature is not shown out of order (test_the_first_function_that_does_not_fit_closes_the_budget_for_the_files_after_it).
- Data line {"told": [[name, sig|null]]}; _bound keeps every shape check (list of [str, str|None] pairs, anything else None; the old {"helpers","hidden"} shape is not the listing), non-identifier names are dropped, not counted. Aside: `PATH ran first: functions a(x), b(); by name only: c, d`; a file that tells none: `PATH ran first: no public functions`; unchanged failure forms.
- Frame (python.py): _HELPERS replaced by _TOLD (which functions, cost, 600, underscore untold, help/getsource free; confined only, as _HELPERS was: unconfined nothing is listed so it would be false) and _DOCSTRINGS (the convention; true with or without the jail, said when the project's file, the model's to write, is named). The three kinds of function are now the model's own, the startup files', and tools. The person's-file sentence now says getsource shows "the source of one of its functions". No ruff/mypy mention. The 600 in _TOLD and _BUDGET are tied by test_two_files_share_600_characters_of_signatures (600 fits to the character, 605 does not) and the _TOLD text test.
- Removed: worker._helper/_HELPER/binding/__bh_helper__, _HELPERS, the helper names in docstrings and comments. A file that still says @helper fails at start: test_a_startup_file_that_still_uses_the_old_decorator_fails_at_start_with_a_name_error (real worker): "ran first and failed ... File <path>, line 1, in <module> @helper ... NameError: name 'helper' is not defined", and the next file still runs.

Evidence (root unless said; Python 3.15.0b4):
- Seen failing first: with the new tests written and the old source, 42 of the python plugin's tests failed (every new startup test: __all__, private name, name only imported, budget, two files, old-decorator NameError, the frame tests, the namespace listings). After: 89 passed.
- Planted violations in client._startup_input / _fitted, each seen failing and restored: _BUDGET 700 (2 failed), 599 (1 failed: the 600-to-the-character test); without the held-before clause (7 failed); without the __module__ clause (2); without the isroutine/isclass clause (2: the instance test and the misbehaving-object test); the first `except Exception` of _bh_made narrowed (1: the misbehaving-object test, the file then "ran first and failed"); the budget not closed after the first miss (4); __all__ always taken as the file's own (1: test_all_names_only_what_the_file_that_bound_it_made).
- scripts/check bh-02/plugins/python-cordis-plugin: exit 0 (format, lint, types, 89 tests, gates incl. worker-stdlib-only and the purity budget, docs strict build; tokens skipped: no bh-01 dist). scripts/check bh-02/app --no-gates --no-docs: exit 0 (199 passed, 1 skipped). scripts/arch-check --no-fix: exit 0 (scripts/model-friction changed). Also green: subagents, extensions, agent and runner plugin tests.
- su tester -c "tini -s -- .venv/bin/python -m pytest -q -p no:cacheprovider bh-02/plugins/python-cordis-plugin bh-02/app/tests/test_python_repl.py": 126 passed, 1 skipped (seatbelt is darwin's); the real bubblewrap listing test (test_on_linux_a_startup_file_s_functions_are_listed_by_signature_from_inside_the_jail) runs there.
- AC #3 (scripts/check passes) is NOT ticked: the full scripts/check is the reviewer's.
- AC #1: _TOLD/_DOCSTRINGS/the three-kinds bullet are quoted in tests (test_the_model_is_told_once_which_startup_functions_are_told_and_what_they_cost, ..._docstring_convention_..._with_or_without_a_jail, test_the_old_name_for_a_startup_function_is_nowhere_in_what_the_model_is_told). _TOLD is confined only (nothing is listed unconfined); the docstring sentence holds either way and is said when the project's file is named.
- AC #2: grep -rniI helper bh-02 docs: what is left, kept for another sense: brig jail helpers (runner plugin jail.py, README, test_runner_confined.py), credential helpers / apiKeyHelper / key_command helper (models plugin, docs/bh-02/using/models.md), "private helpers" (bh_02/sessions.py), a row key named "helpers" in test_agents_child.py; and in the python plugin's tests the old decorator on purpose: test_python_tool.py (the @helper NameError test; the assertion that the model is told no "helper") and test_python_listing.py (the same assertion on the aside, and the pre-decision-0006 {"helpers": ...} line, which must not be taken for a listing). Nothing in client.py, worker.py, python.py, the plugin README, GLOSSARY.md or docs says it; scripts/model-friction said "the model keeping its helpers" and now says "functions for later sessions".
- Not verified: darwin (seatbelt) path; scripts/linux-jail-check (Docker) was not run; the listing line is still bounded by the worker's 20,000-character output cap (a file with hundreds of functions is said not to be listable, as before; public-by-default makes it likelier, no task filed: it needs ~250 functions).
<!-- SECTION:NOTES:END -->
