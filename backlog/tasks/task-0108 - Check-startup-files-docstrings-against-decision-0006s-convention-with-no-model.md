---
id: TASK-0108
title: >-
  Check startup files' docstrings against decision-0006's convention, with no
  model
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-16 02:03'
updated_date: '2026-10-16 04:15'
labels:
  - python
  - size-3
  - finish-moved
dependencies:
  - TASK-0106
  - TASK-0107
references:
  - >-
    backlog/decisions/decision-0006 -
    Tell-the-model-of-the-functions-the-startup-files-define-by-progressive-disclosure-with-no-decorator.md
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Build decision-0006 point 7's docstring half: ruff (--isolated, D101, D103, D205, D415, D419) plus bh-02's own rule for what ruff has none for (an example; doctest blocks that parse, each with a blank line before it), run in the jail at each REPL start; ruff becomes a dependency of the python plugin. Waits for TASK-0106 (acceptance) and TASK-0107 (it rewrites the aside and the set of told functions this reports on). Open for the plan: the example rule's command name and home, since plugin-layering keeps the app's CLI from importing the python plugin.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Confined, at each REPL start, ruff with bh-02's flags and bh-02's example rule check each startup file in the jail (the person's from the text the host hands the REPL), and tests cover each finding and a file with none
- [x] #2 The aside names each told function that misses and the rule codes it breaks, never a tool's message text, and a finding never stops a file running or hides a function; unconfined, nothing runs unasked and the python section gives the model the commands
- [x] #3 The ruff line for CI and a pre-commit hook is documented, and the example rule runs as a command with no session and no model, exiting 1 on a finding and 0 on none
- [x] #4 scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Where the rule lives (the first decision, each constraint checked, not assumed)
One standalone stdlib-only file in the plugin, `python_cordis_plugin/startup_check.py`: a pure core (source text in, findings out: bh-02's example rule with `ast` + `doctest.DocTestParser`, and the mapping of ruff's JSON to told names) and a thin shell, run BY PATH as a program (`python -I startup_check.py ...`) in the jail and by the `bh-02 check-examples FILE...` subcommand, which finds the file with `importlib.util.find_spec("python_cordis_plugin")` and runs it, never importing the package. Checked: (1) `find_spec` of a top-level name imports nothing (python -I: package and cordis absent from sys.modules after it; bootstrap.code_directories already relies on this); (2) `import python_cordis_plugin` does import cordis (sys.modules after it), so `-m` and an import are out for the jail program; (3) worker-stdlib-only polices only `modules = [...]` (the gate's config), so the new file is added there and a planted non-stdlib import must fail it; (4) plugin-layering is about import symbols, and a name given to find_spec is not one (arch-check shows it); (5) import-time-side-effects allows a program only by name: the file is added to that allow (its `if __name__` guard), as worker.py is. Rejected: a new lib/ member (plugin-layering's _LIBRARIES would need editing, and the jail program is still a file run by path); an import from bh_02 (forbidden); `-m` (imports cordis).

### Order of work
1. ruff as a runtime dependency of the python plugin (pyproject), `uv lock`, `uv sync --all-packages`; confirm `uv tool install ./bh-02/app` gets it (the app depends on the plugin; `uv tree --package bh-02 --no-dev`).
2. Tests first, seen failing: the pure rule (each finding: example, doctest malformed, doctest with no blank line before it; none; a `::` block; a private function skipped; `__all__` respected, incl. a class), ruff mapping (canned reports and real ruff), the program's exit codes (0 none, 1 finding, 2 usage/unreadable), the aside wording (`client.startup_checked`), the real worker (Confined, unjailed) on a file with findings and one without, the python section sentences, and in bh-02/app/tests a real bubblewrap jail running both on a file with findings and one without, and `bh-02 check-examples`.
3. startup_check.py: `Finding(name, line, code, message)` frozen; `examples(source)`, `ruff_findings(source, report)`, `grouped(...)` pure; shell `main(argv)`: `startup_check.py [--ruff] [--json] [--name NAME] FILE...` (FILE or `-` for stdin: the host hands the person's file as text), human lines `FILE:LINE: NAME: CODE message` or one JSON line `{"misses": [[name, [codes]]]}`; ruff run as `sys.executable -m ruff check --isolated --no-fix --select D101,D103,D205,D415,D419 --output-format json --stdin-filename NAME -` over the text on stdin. Told statically by the same rule as point 1 (public defs/classes, or exactly the literal `__all__`'s that the file defines), last definition of a name wins; the host intersects with the live told set. Nothing executes the file.
4. client.py: `_check_input` (an input that runs the program with subprocess in the REPL, leaving no names), run after a startup file that told something, in the same try as the file's own input; `startup_checked(name, told, line)` pure: only live-told names, codes from a closed set in canonical order, never a message; "" for none; `PATH docstrings could not be checked` when the check did not run. A finding never stops a file or hides a function. Unconfined: nothing runs; python.py gives the model the two commands. Confined: python.py says files are checked at REPL start and how to see detail.
5. cli.py: `check-examples` (exit code passed through). Root pyproject: gate allows (worker-stdlib-only, import-time-side-effects, print-input/terminal-io, purity budget for the shell, over-exposed allow for the click command).
6. Docs: docs/bh-02/how-it-works/python-tool.md, command-line.md, plugin README, GLOSSARY, with a pre-commit hook and a CI step.
7. Update the existing exact-aside tests whose startup files define undocumented functions (they now carry a finding aside).

### Risks
Existing tests assert exact asides for undocumented functions (~20): they change by design. doctest import costs ~100 ms (imports pdb, unittest): imported only when a told docstring has `>>>`. ruff column/row mapping: D101/D103 at the def row, D205/D415/D419 at the docstring span. A file the program cannot parse is "could not be checked", not a finding. Typing (mypy) is TASK-0109: left out.

### Proof
Plant: break the example check (and the blank-line check) and see tests fail; plant a non-stdlib import in startup_check.py for worker-stdlib-only; real bwrap jail test; tester+tini run; timing of the check added to a REPL start, warm and cold. scripts/check bh-02/plugins/python-cordis-plugin, scripts/check bh-02/app --no-gates --no-docs, scripts/arch-check. The full scripts/check is the reviewer's.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-16: finish moved before any work, on the owner's word: ruff does what it has rules for (the probe showed it calls public what decision-0006 point 1 tells, __all__ included), bh-02's own rule only for examples, and it runs in the jail rather than the host. Typing (mypy) split to TASK-0109.

Built decision-0006 point 7 (docstring half). Chosen home (plan, constraints checked): python_cordis_plugin/startup_check.py, one stdlib-only file, run BY PATH (python -I startup_check.py) in the jail and by `bh-02 check-examples FILE...`, which finds it with code_directories (importlib.util.find_spec by name) and never imports the package. Checked, not assumed: find_spec of the top-level name leaves python_cordis_plugin and cordis out of sys.modules; `import python_cordis_plugin` puts cordis in; `python -I -X importtime startup_check.py` names no cordis/python_cordis_plugin/host_paths (test); worker-stdlib-only polices only its `modules` list (module added; a planted `import host_paths` made scripts/arch-check fail with the rule's message, restored); import-time-side-effects allows the program by name; plugin-layering saw no import from bh_02. Files: python-cordis-plugin startup_check.py (new), client.py, python.py, pyproject.toml (ruff>=0.16.7, uv.lock by `uv lock`), README.md, tests (test_python_startup_check.py new, test_python_tool.py); bh-02/app cli.py, README.md, tests (test_command_check_examples.py new, test_python_repl.py); root pyproject.toml (gate allows and purity budget); docs python-tool.md, command-line.md; GLOSSARY.md.

How it works: after a startup file that ran and told something, a second input (client._check_input, same try as the file's own) runs the program under sys.executable -I: --ruff --json NAME for the project's file (read in the jail) or --name=NAME - with the text on stdin for the person's (handed by the host). The program runs `sys.executable -m ruff check --isolated --no-fix --select D101,D103,D205,D415,D419 --output-format json --stdin-filename=NAME -` and bh-02's rule (ast + doctest.DocTestParser, doctest imported only when a docstring has >>>), maps ruff's rows to the told definitions (D101/D103 at the def line, the rest in the docstring's lines; private functions, methods and the module docstring dropped) and prints {"misses": [[name, [codes]]]}, codes only. The host (client.startup_checked) keeps only names the live listing told, only codes of the closed set CODES, in the file's order and CODES order; anything else is `PATH docstrings could not be checked`; a clean file or one that tells nothing adds nothing. Aside: `PATH docstring findings: a D103, example; b doctest`. A finding stops nothing and hides nothing (tests). Unconfined nothing runs; python.py gives the two commands (_CHECK_BY_HAND), confined it says the files are checked at start and how to see detail (_CHECKED); both under 700/500 characters (test).

Findings worth knowing: (1) ruff does NOT raise D103 for an underscored name that `__all__` lists, and reads a set/string `__all__` as naming nothing public (no D103 at all), though decision-0006 point 1 tells them; those miss `example` alone (documented in the README and docs, tested). (2) `lint.ignore` in a project's ruff config does not loosen a CLI --select run; per-file-ignores and exclude do, and --isolated stops both (tests with those configs, seen failing without --isolated). (3) Existing exact-aside tests whose startup files define undocumented functions (~20 in test_python_tool.py and 2 in test_python_repl.py) now carry the finding aside: updated with a _bare helper, by design.

Evidence (root unless said; Python 3.15.0b4, ruff 0.16.7): scripts/check bh-02/plugins/python-cordis-plugin: exit 0 (format, lint, mypy, 137 tests, gates, docs strict build; tokens skipped: no bh-01 dist). scripts/check bh-02/app --no-gates --no-docs: exit 0 (209 passed, 1 skipped). scripts/arch-check --no-fix: exit 0. `uv tree --package bh-02 --no-dev` lists ruff under python-cordis-plugin under bh-02, so `uv tool install ./bh-02/app` gets it. su tester -c "tini -s -- .venv/bin/python -m pytest -q -p no:cacheprovider bh-02/plugins/python-cordis-plugin bh-02/app/tests/test_python_repl.py bh-02/app/tests/test_command_check_examples.py": 183 passed, 1 skipped (seatbelt). Real bubblewrap: test_on_linux_both_checks_run_in_the_jail_on_a_file_with_findings_and_one_without runs both checks inside bwrap over the person's file (absent from the jail: its text was handed in) and a project file with findings, shows `False` for the person's path existing, and runs the two commands the prompt gives from the model's REPL in the same jail (ruff exit 1, rule exit 1).

Planted violations, each seen failing and restored: example check never fires (many example tests failed); blank-line check off (3 failed); --isolated dropped (4 failed: the two config tests and the two prompt tests); aside names names the file did not tell (3); any code accepted (2); summary carries messages (many); aside in the check's order (2); no `--` before a startup file named -odd.py (1); non-stdlib import in startup_check.py (arch-check: worker-stdlib-only).

Timing added to a REPL start, a real bwrap jail, one startup file telling one documented function vs one telling none (no check), median of 7 starts: warm 425 ms vs 227 ms, so about +200 ms (the program alone: 63 ms with a `::` example, 133 ms with a doctest block because import doctest is ~70 ms; ruff alone ~35 ms); cold (page cache dropped): 567 ms vs 308 ms, about +260 ms. Per file that tells something.

Not verified: scripts/linux-jail-check (the Docker daemon is not answering in this container: `Cannot connect to the Docker daemon`), darwin (seatbelt). AC #4 (scripts/check passes) is NOT ticked: the full scripts/check is the reviewer's. Typing (mypy) left to TASK-0109. A computed `__all__` (not a list/tuple literal) is read by the rule as none: its underscored names get no `example` finding (the live listing still tells them).

Reviewer: scripts/check (repo root, full) exit 0: format ok, lint ok, types ok (194 files), tests 3134 passed 31 skipped in 165s, gates ok, docs ok, tokens skipped (no bh-01 dist). Working tree clean after it.
<!-- SECTION:NOTES:END -->
