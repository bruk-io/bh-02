---
id: TASK-0100
title: >-
  Mark startup-file helpers with @helper, and show the model their signatures
  (decision-0004)
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-14 15:57'
updated_date: '2026-10-15 18:30'
labels:
  - python
  - size-2
dependencies:
  - TASK-0099.02
references:
  - >-
    backlog/decisions/decision-0004 -
    Show-the-startup-files-helpers-to-the-model-by-signature-marked-with-helper.md
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Build decision-0004 (accepted 2026-10-14 by Fable for the owner, with two changes). It waits for TASK-0099.02 only, which renames the startup files (startup.py) and the python row's class (PythonProcess) that this task edits; TASK-0099.03 does not touch these files. In short: the Python process binds helper in the namespace; @helper marks a callable and returns it unchanged; after each startup file the startup line lists its helpers as name(signature), control characters stripped and each cut at 160 characters, then counts the other public names as hidden; help(name) gives the docstring; the python section says the convention once; told at startup only. Unconfined (--no-jail) stays as today: nothing listed. After /compact the signatures live only in the model's summary: an accepted limit. Kept out: slash commands, a directory of startup files, the REPL's environment, helpers defined after startup.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A startup file's @helper functions are listed in the first input's output as name(signature), and its other public names only counted as hidden; a test of each, seen failing before the change
- [x] #2 A signature with control characters or over 160 characters is cleaned and cut, and one inspect.signature can't read is name(...); a test of each
- [x] #3 help(name) shows a helper's docstring, and @helper returns the function unchanged; a test of each
- [x] #4 The python section, the plugin README, docs/bh-02/how-it-works/python-tool.md and GLOSSARY.md (helper) say the convention; the worker stays standard library only; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Tests first, seen failing: add tests for AC1-3 (real Python process: startup file with two @helper functions and one plain name -> first input lists both by signature, counts one hidden; help(name) prints the docstring; helper(f) is f) and direct unit tests of the pure formatting (control characters stripped, cut at 160, name(...) when no signature, the wording). Run them before the change: they fail.
2. worker.py: bind `helper` in the namespace at construction (before any startup file runs), set __bh_helper__ = True, return the argument; bound once, so an input that rebinds it keeps its own (as with tools). Standard library only.
3. client.py: _startup_input prints one JSON line (each helper name and raw signature text or null, count of other public names). The host parses it (untrusted) and formats it in pure functions (signed, startup_ran): control characters stripped, cut at 160, name(...) when unreadable. Failure forms and unconfined unchanged.
4. Update the ~20 old-wording assertions in test_python_tool.py and test_python_repl.py (files without helpers: `no helpers; N names hidden`), plus the one test that used `helper` as an undefined name.
5. Docs: _keep sentence (decision-0004 point 5), plugin README, docs/bh-02/how-it-works/python-tool.md, GLOSSARY.md helper line.
6. Proof: pytest on the python plugin and bh-02/app with -n auto --dist loadgroup, scripts/check bh-02/plugins/python-cordis-plugin, then scripts/check bh-02/app --no-gates --no-docs. Risks: JSON line vs the 20,000-character output cap (a too-long line is told as not listable); the worker gate (stdlib only); the purity budget (new functions pure). The full scripts/check is the reviewer's.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built decision-0004 as accepted. Files: python-cordis-plugin worker.py (binds `helper`), client.py (the startup input and the aside), python.py (`_keep`), README.md, tests (test_python_tool.py, new test_python_listing.py); bh-02/app/tests/test_python_repl.py; docs/bh-02/how-it-works/python-tool.md; bh-02/GLOSSARY.md (one `helper` line after `startup file`).
- Where the formatting runs (the call): on the host. The startup input prints, last, one line of JSON ({helpers: [[name, signature text or null]], hidden: count}); the host reads it as data and words it in two pure functions, client.signed (name + signature; control characters C0/DEL/C1 stripped; cut at 160 characters with a trailing ellipsis; name(...) for null) and client.startup_ran (the aside; a last line that is not that shape is said not to be a listing, never quoted). Why: the host already treats the Python process's text as untrusted output; the cleaning and the cut are then plain Python that tests call directly rather than a string of code; and the in-process part stays small (marked? signature text, capped at 4 x 160 characters so the line stays under the worker's 20,000-character output cap). A file with so many helpers that the line passes that cap is said not to be listable (known limit, not built around).
- worker.py: `_helper` (named helper) sets __bh_helper__ = True and returns its argument; it is in the namespace from construction, so it is bound once, before any startup file, and an input that rebinds `helper` keeps its own (the same way a rebound `tools` is left alone). Standard library only; `_had` now starts from the namespace so `del helper` does not read as never defined.
- A helper is a public name the file bound (the old set) that is callable and has `getattr(v, "__bh_helper__", False) is True`; the rest are counted. A helper whose signature repr raises or whose inspect.signature fails is name(...); an object that raises on getattr is counted hidden. Helpers are listed in the order the file made them (as the decision's example does), not sorted.
- Wording: `(PATH ran first: helpers a(x), b(); 3 other names hidden)`, `no helpers; N names hidden`, second file `ran next`; singular `1 other name` / `1 name`; no count when helpers are listed and none hidden; a file that bound nothing keeps `ran first and defined: nothing`. Failure forms unchanged.
- Unconfined: nothing listed, `_keep` says nothing of @helper there, and test_unconfined_neither_startup_file_runs_unasked passes unchanged. Two unconfined/real-worker tests that list the namespace had to change by one name because `helper` is bound for every input (decision point 1; it also makes a file using @helper run under exec): test_a_call_runs_its_code_and_the_namespace_holds_only_what_inputs_put_there ([] -> ['helper']) and test_unjailed_inputs_share_a_namespace_of_plain_python_and_each_is_asked_about (['x'] -> ['helper', 'x']); plus test_a_startup_file_stopped_part_way... (confined) ['A', 'time'] -> ['A', 'helper', 'time']. One test used `helper` as an undefined name (NameError hint): renamed to `toolbox`.
- Old wording: 27 occurrences of `ran first/next and defined: ...` in test_python_tool.py and test_python_repl.py changed to `no helpers; N names hidden`.

Evidence (root; tester+tini where said):
- Seen failing before the change: the five real-process tests (listed by signature + one hidden counted; no-helper wording; help() docstring and helper(f) is f; unconfined helper bound and a rebound one kept; a stand-in answering every attribute is not a helper) failed on the old source (NameError: helper / old wording), test_python_listing.py failed at import (no signed/startup_ran), and the later-added `_keep` sentence test and the real-bwrap listing test (test_on_linux_a_startup_file_s_helpers_are_listed_by_signature_from_inside_the_jail) failed with the src stashed, passed after. Planted violation: with _CUT = 100000 and the control-character pattern reduced to NUL, 5 tests failed (the AC2 unit tests and the end-to-end signature test); restored, all pass.
- uv run pytest bh-02/plugins/python-cordis-plugin bh-02/app -q -n auto --dist loadgroup: 270 passed, 1 skipped (one run had test_real_launch::test_while_the_model_restarts... fail under full-core load; it passes alone, and passes with my change stashed: a timing flake, not related).
- su tester -c "tini -s -- .venv/bin/python -m pytest -q -p no:cacheprovider bh-02/plugins/python-cordis-plugin bh-02/app/tests/test_python_repl.py": 109 passed, 1 skipped (the real bwrap jail tests run, startup listing included).
- scripts/check bh-02/plugins/python-cordis-plugin: exit 0 (format, lint, types, 73 tests, gates incl. worker-stdlib-only and the purity budget, docs build; tokens skipped: no bh-01 dist). scripts/check bh-02/app --no-gates --no-docs: exit 0 (199 passed, 1 skipped). scripts/arch-check --no-fix: exit 0.
- AC1: test_a_startup_file_s_helpers_are_listed_by_signature_and_its_other_names_only_counted (two @helper functions + one plain name: both by signature, 1 other name hidden), the person/project pair test, and the real-jail test. AC2: tests/test_python_listing.py (control characters, cut at 160, name(...), wording, malformed lines) and test_a_helper_s_signature_is_cleaned_cut_or_dots_whatever_its_defaults_repr_does through the real process. AC3: test_help_shows_a_helper_s_docstring_and_helper_returns_what_it_marks (help(run_tests) prints the docstring; helper(f) is f).
- AC4: `_keep` (once, confined only), the plugin README, docs/bh-02/how-it-works/python-tool.md (new Helpers subsection) and GLOSSARY.md (`helper`) say the convention; the worker is still standard library only (gate passed). "scripts/check passes" for the whole workspace is left to the reviewer: only the per-member checks above were run.
<!-- SECTION:NOTES:END -->
