---
id: TASK-0105
title: >-
  Make helpers and tools plainly different things to the model in the python
  section
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-15 21:00'
updated_date: '2026-10-15 21:27'
labels:
  - python
  - size-1
dependencies: []
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Asked by the owner (2026-10-15): keep tools and helpers separate, but make it obvious to the model that they are different things. Today the python section says "helper" for any function the model defines (one word, two things: decision-0005's rule) and tells of `tools.NAME` in a bullet of its own as "functions here too", never saying where each runs. A helper (a startup file's `@helper` function) is plain Python in the REPL, in the jail, able to do nothing an input can't; a tool is bh-02's, runs outside the jail, and is asked about as the model's own call to it would be.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The python section uses "helper" only for a startup file's @helper function, and says in one place that the model's own functions, helpers and tools are three different things: where each runs (the REPL in the jail, or bh-02 outside it), whether a call is asked about, and how long each lasts
- [x] #2 GLOSSARY.md's helper and tools (in an input) lines say the same; the python tool's doc page says it where it explains helpers and tools
- [ ] #3 The python plugin's tests pass with the new wording, and scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. python.py _USE: the 'Build up state' bullet says 'define a function' (rest unchanged); the last bullet (tools as functions) is replaced whole by the three-kinds text (own / @helper helpers / tools, with where each runs, whether asked about, and how long it lasts). 2. GLOSSARY.md: the tools (in an input) line and the helper line get the brief's wording. 3. docs/bh-02/how-it-works/python-tool.md: the sentence before the table, the 3-column table (own / helper / registered tool) and the paragraph under it. 4. grep bh-02 and docs for the old quoted text and update the tests/docs that quote it, nothing else. Risks: a test pinning the prompt text or the table; the grep in step 4 finds all quoting sites. Proof: scripts/check bh-02/plugins/python-cordis-plugin exit code (tests, gates, docs), a grep showing 'helper' in python.py only names @helper functions, and the diff of each file. No brig, cordis or CONTRACTS change, so no SPEC decision and no scripts/arch-check run beyond what the member check does.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- Wording changed as the brief gives it: python.py `_USE` ("define a function once" in the Build up state bullet; the tools bullet replaced by the three-kinds bullet: own = REPL, gone when it ends; helpers = `@helper` startup-file functions, plain Python in the REPL with the same limits, kept in the startup file; tools = bh-02's, outside the REPL, asked about per call, lasting as their row). GLOSSARY.md `tools` and `helper` lines; docs/bh-02/how-it-works/python-tool.md sentence, 4-column table and paragraph.
- Old wording: grep -rn for "functions here too", "define a helper once", "whose call runs as the model" over bh-02 and docs finds no source (only a stale .pyc under __pycache__).
- One test changed beyond the brief's step 5, needed for AC #3: bh-02/plugins/python-cordis-plugin/tests/test_python_tool.py line 584 asserted `"@helper" not in instructions_for(False, mine)`. The new `_USE` names `@helper` in every prompt, confined or not (worker.py binds `helper` in every input's namespace), so that assertion cannot hold. It now asserts `said not in instructions_for(False, mine)`, the startup-listing convention sentence, which keeps the test's intent (unconfined is told nothing of the listing).
- Seen failing first, with the new wording and before that test edit: `scripts/check bh-02/plugins/python-cordis-plugin` exit 1, `test_the_model_is_told_once_what_helper_does_in_a_startup_file_it_runs` (1 failed, 74 passed). After: exit 0 (format: 10 files already formatted; lint: all checks passed; types: no issues in 5 source files; tests: 75 passed; gates: ok; docs: built, ok; tokens: skipped, no bh-01 dist). Run as root (scripts/check uses the root .venv), xdist on.
- `grep -n -i helper python.py` after the change: every prompt use names a startup file's @helper function. Left as is, flagged: the startup aside says `inspect.getsource(helper) shows one of its helpers` (the decorator's name as the example).
- AC #3 is not ticked: the full scripts/check is the reviewer's to run.

- Follow-up from the orchestrator, text the model reads:
  - python.py, the startup aside: `inspect.getsource(helper)` is now `inspect.getsource(NAME) shows one of its helpers, NAME as the startup line lists it.` (the decorator's name is the example no longer). Quote updated at test_python_tool.py (the unconfined-allowlist test).
  - client.py ~749, the tools aside: `(bh-02's other tools are functions in your namespace: ...` is now `(bh-02's other tools, run by bh-02 when you call one: ...`. Quotes updated at test_python_tool.py (~1449) and bh-02/app/tests/test_python_repl.py (~150).
  - Docstrings client.py ~19 and wiring.py ~65 left as they are.
- Grep for the old phrases over bh-02 and docs: no hit left except bh-02/plugins/python-cordis-plugin/README.md:134, `inspect.getsource(helper)`, developer docs, not changed here (flagged).
- `scripts/check bh-02/plugins/python-cordis-plugin`: exit 0 (format, lint, types, 75 tests passed, gates, docs built; tokens skipped, no bh-01 dist). Root run, xdist.
- bh-02/app/tests/test_python_repl.py not run (jail lock, per the orchestrator); the full check runs it.

- Follow-up: bh-02/plugins/python-cordis-plugin/README.md:134 now says `inspect.getsource(NAME)`, NAME a helper as the startup line lists it (the only line changed there). `scripts/check bh-02/plugins/python-cordis-plugin --no-gates`: exit 0 (lint, types, 75 tests passed, docs built; the gates were not run per the orchestrator).

- From the close review: four wording fixes.
  - python.py, the startup-file lines: "Helpers worth having in every session go in" is now "Functions worth having in every session go in"; "the person may keep helpers of" (the startup-file aside, both branches) is now "the person may keep functions of", the two lines "The person may keep functions of their own in" and "the person may keep functions of their own in".
  - test_python_tool.py: the three quotes of those lines (about lines 554, 566 and 604) follow the new wording, nothing else in them.
  - docs/bh-02/how-it-works/python-tool.md, the helper column's "How long" cell: "a new REPL runs the file again (with `--no-jail`, once the model runs it)".
  - bh-02/GLOSSARY.md, the helper line: replaced whole with the wording the close review gives.
- Flagged, not changed: bh-02/plugins/python-cordis-plugin/README.md:23 still says "that helpers worth keeping go in the project's startup file" (developer docs).
- `scripts/check bh-02/plugins/python-cordis-plugin`: exit 0 (format, lint, types, 75 passed, gates, docs built; tokens skipped, no bh-01 dist).
<!-- SECTION:NOTES:END -->
