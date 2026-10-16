---
id: TASK-0109
title: Type-check startup files with mypy --strict at each REPL start (decision-0006)
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-16 02:51'
updated_date: '2026-10-16 05:00'
labels:
  - python
  - size-3
dependencies:
  - TASK-0106
  - TASK-0108
references:
  - >-
    backlog/decisions/decision-0006 -
    Tell-the-model-of-the-functions-the-startup-files-define-by-progressive-disclosure-with-no-decorator.md
priority: medium
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Build decision-0006 point 7's typing half: mypy --strict, bh-02's flags and no project config, run in the jail over each startup file at REPL start; mypy becomes a dependency of the python plugin. Waits for TASK-0106 (acceptance) and TASK-0108 (it builds the REPL-start checks and their aside, which this adds a second tool to). Measured 2026-10-16: an untyped parameter and a wrong operand are caught; 5.3 s cold, 0.2 s warm on the uncompiled mypy pin; a bare annotation (tools: Any) satisfies mypy and keeps the REPL's binding; a __builtins__.pyi stub on MYPYPATH does not work. Open for the plan: where the cache lives among the jail's writable roots, and which paths mypy searches so it finds what the REPL can import.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Confined, at each REPL start, mypy --strict with no project config checks each startup file in the jail, and the aside names each told function with an error and its error codes, never mypy's messages; tests cover an untyped function, a type error, an unfound import and a clean file
- [x] #2 A startup file that declares a name the REPL provides with a bare annotation (tools: Any) passes mypy and keeps the REPL's binding, and the python section tells the model to declare such names so
- [x] #3 The mypy line for CI and a pre-commit hook is documented, and mypy's cold and warm cost at REPL start on the shipped mypy is measured and recorded on this task
- [ ] #4 scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
### Shape (extends TASK-0108's, re-opens none of it)
`--mypy` and `--cache-dir=DIR` on the same program, startup_check.py (stdlib only, run by path under `python -I`, never imported in the jail). The host's `_check_input` adds `--mypy --cache-dir=...` to the one command it already runs; the program prints the same `{"misses": [[name, [code, ...]], ...]}` line, mypy's codes beside ruff's and bh-02's; `_missed` and `startup_checked` word the aside. One command, one line, one aside per file: `PATH findings: a D103, example, no-untyped-def; b doctest; elsewhere in the file: import-not-found`. A check that did not run is `PATH docstrings and types could not be checked` (any tool failing fails the file's check, as ruff did). Rejected: a second program/input (a second input per file doubles the round trips and the asides cost more tokens per session).

### Measured before planning (pinned mypy 2.4.0+dev.539f6e6, uncompiled, this container)
- `mypy --output json` gives file/line/code/severity per error: no message parsing; only `severity == error` counts, codes only reach the host.
- `--config-file=` (empty) reads no config: a planted mypy.ini plugin in cwd, ~/.mypy.ini and $XDG_CONFIG_HOME/mypy/config each ran without it and did not with it. But main.py lets `MYPY_CACHE_DIR` override `--cache-dir` and mypy reads `MYPYPATH`/`MYPY_NUM_WORKERS` from the environment: the program runs mypy with every `MYPY*` variable removed from its environment (a startup file runs in the REPL process, so it can set them before the check input).
- Search paths. The REPL is `python -I`: its sys.path is the stdlib and site-packages (+ the editable .pth src dirs), never cwd or the script's directory. mypy adds cwd and the checked file's directory to what it searches, so a `helper.py` beside `.bh-02/startup.py` or in the project root would resolve for mypy and not in the REPL. Fix: the program copies the text into a fresh directory under `tempfile` (the jail's scratch, `$TMPDIR`; removed after) as `bh_startup.py`, runs mypy there with cwd = that directory and `python -I -m mypy` (same interpreter, same `-I` => pyinfo sees the REPL's sys.path), so what mypy can import is exactly what the REPL can: bh-02's environment and nothing in the project. Tested with real mypy and the real worker (a sibling module: mypy `import-not-found`, REPL ModuleNotFoundError; an installed workspace package: both find it). A `sys.path.insert` in the file is invisible to mypy (documented: `# type: ignore[import-not-found]`); `import-untyped` (an installed package without types) is a strict finding too, documented.
- File vs `-c`: `-c` works (same findings, `<string>` as the name, no file, and a stable cache key) but passes the whole file as one argv word (Linux: 128 KiB limit => E2BIG). The brief asks for a file in scratch: file it is. The cache warms across different scratch paths (0.175 s on a new directory).
- The cache. Writable roots of a jail are the project, `$TMPDIR` (a new directory per jail start: `bh-j-*/tmp`, so cold at every REPL start) and the model's auto-memory directory (the model's notes: not for a cache). So it must be in the project: `<root>/.bh-02/mypy_cache` (new `PythonProcessConfig.mypy_cache`, relative to root; also what tests redirect to a shared warm directory). mypy writes `.gitignore` (`*`) and `CACHEDIR.TAG` into its cache directory itself (seen), so git ignores it with no entry in the project's own .gitignore. Not `.mypy_cache`: that is the project's own mypy's, written with other options. The cache is sqlite shards (`cache.N.db`) in 2.4-dev: 4 concurrent cold runs on one cache all pass (tested); a corrupted file or an unwritable directory makes mypy exit 2 with INTERNAL ERROR (seen) => the program retries once with `--cache-dir=/dev/null` (cold, correct), never deletes anything. Documented: delete `.bh-02/mypy_cache` if it keeps happening.
- Timeouts: a startup file importing textual/cordis is 12.7 s cold, 0.29 s warm; mypy gets 90 s, the check input 120 s (a partial run still warms the cache). Ctrl-C cancels as for any startup input.

### Mapping to names (pure)
`mypy_findings(source, report, file)`: JSON lines -> `Finding`. An error belongs to the told definition (same `_told` as ruff/example: point 1 from the syntax) whose span (decorators to end_lineno) holds its line; a method's to its class. An error outside every told definition (an import, module-level code, a private function) is `elsewhere in the file` (name `<file>`, a reserved name no function can have), so `import-not-found` on a top-level import is not lost. Codes: a closed tuple `MYPY_CODES` (mypy's 78 today, a test compares it to `mypy.errorcodes.error_codes` so a mypy bump that adds one fails there), anything else (or no code) is `mypy`, so the host's closed-set rule holds and a new code never makes the whole line unreadable. `CODES = (*RUFF, example, doctest, *MYPY_CODES, mypy)`.

### Order of work
1. pyproject: mypy a dependency of the python plugin (same git rev as the root; `uv lock`; `uv tree --package bh-02 --no-dev` shows it); note on the task: move both to `mypy>=2.4` from PyPI together.
2. Tests first, seen failing: pure `mypy_findings` (canned reports: decorated def, method, private function, module-level, unknown/no code, note, other file, malformed); the program on real mypy (untyped def, type error, unfound import, `tools: Any` + `tools.x()`, clean file, sibling module not found, env MYPYPATH/MYPY_CACHE_DIR scrubbed, user config ignored, cache used + gitignored, unwritable cache falls back, program exit codes); aside wording (`startup_checked`, `_missed` rejects codes outside the set); the real worker: `tools: Any` keeps the REPL's `tools` (bound object identical before/after) and a strict file's aside; python section sentences; a real bubblewrap jail (Linux) over the person's text and the project's file, cold then warm.
3. startup_check.py (`MYPY_FLAGS`, `MYPY_CODES`, `ELSEWHERE`, `mypy_findings`, `_mypied`, `--mypy`/`--cache-dir`), client.py (`mypy_cache` config, `_check_input`, `_missed`, `startup_checked`, timeouts), python.py (the sentences; confined/unconfined), existing exact-aside tests (`_bare` gains `no-untyped-def`).
4. Docs: README (python plugin), docs/bh-02/how-it-works/python-tool.md, GLOSSARY, CONTRACTS.md config line if it lists keys; the mypy line for CI and a pre-commit hook beside TASK-0108's ruff line and command.
5. Tests share a warm cache (conftest session fixture) so ~50 startup tests don't each pay a cold mypy.

### Risks
(1) 40+ existing tests assert exact asides (functions untyped): by design they change (`no-untyped-def`). (2) Cold mypy per test: shared cache above. (3) Jail: mypy must read its package, typeshed and sys.path in bubblewrap's allowlist: tested for real. (4) The 128 KiB argv limit does not apply (file). (5) `import-untyped` and `no-any-return` (returning `tools.x()` typed Any) are strict findings the model will see; documented, not hidden.

### Proof
Plants (each seen failing, restored): drop `--strict` (untyped-function test), drop `--config-file=` (user-config test), stop scrubbing MYPY* env (env test), search the file's own directory instead of a scratch copy (sibling-module test), `mypy` not in the closed set (host test). Then `scripts/check bh-02/plugins/python-cordis-plugin`, `scripts/check bh-02/app --no-gates --no-docs`, `scripts/arch-check`; tester+tini run of the touched tests; cold/warm timings in a real bwrap jail at REPL start recorded on the task. Full `scripts/check` is the reviewer's (AC #4 stays unticked).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built decision-0006 point 7, the typing half, on TASK-0108's shape (re-opened none of it): `startup_check.py` (stdlib only, run by path under `python -I`) gains `--mypy` and `--cache-dir=DIR`; the host's one check input (`_check_input`) passes `--ruff --mypy --cache-dir=... --json`; the one `{"misses": ...}` line now carries mypy's codes beside ruff's and bh-02's; the aside is one line per file: `PATH findings: a D103, example, no-untyped-def; b doctest; elsewhere in the file: import-not-found` (was `docstring findings:`; a check that did not run is `PATH docstrings and types could not be checked`).

Files: python-cordis-plugin startup_check.py, client.py, python.py, pyproject.toml (mypy dependency), README.md, tests (test_python_startup_types.py new; test_python_tool.py, test_python_startup_check.py, conftest.py); bh-02/app cli.py (check-examples help names the mypy line), bh-02.toml comment, tests/test_python_repl.py; root pyproject.toml (purity budget: `_mypied`), uv.lock; docs python-tool.md, command-line.md; GLOSSARY.md.

Decisions (measured, in the plan): (1) mypy `--output json`, errors given to the told function/class by line (decorators and methods included), the rest of the file (an import, a statement, a private function) to `ELSEWHERE` = `<file>`, so a top-level `import-not-found` is not lost; codes from a closed tuple `MYPY_CODES` (mypy's 78, compared with `mypy.errorcodes.error_codes` by a test so a mypy bump that adds one fails there), anything else or no code = `mypy`; the host's closed-set rule is unchanged. (2) Paths: the REPL is `python -I`, mypy also adds cwd and the checked file's directory to what it searches, so the program copies the text to `bh_startup.py` alone in a directory under `$TMPDIR` (the jail's scratch, removed after), runs `python -I -m mypy --strict --config-file= --output json` there, so what mypy finds is what the REPL can import (tested against the real REPL: a module beside the startup file or in the project is `import-not-found` for both). A file, not `-c`: `-c` works but is one argv word (128 KiB on Linux). (3) Cache: a jail's scratch is new at every start (cold every time) and the other writable roots are the project and the model's memory, so it is `<root>/.bh-02/mypy_cache` (new `PythonProcessConfig.mypy_cache`, from root or absolute); mypy writes `.gitignore` `*` and `CACHEDIR.TAG` in it itself (tested with git status), and `.mypy_cache` (the project's own mypy's) is left alone. (4) Found while measuring: main.py lets `MYPY_CACHE_DIR` override `--cache-dir` and mypy reads `MYPYPATH`, `MYPY_NUM_WORKERS`: a startup file runs in the check's parent, so the program strips every `MYPY*` variable. A damaged cache or an unwritable directory makes mypy exit 2 (INTERNAL ERROR, seen): the program retries with `--cache-dir=/dev/null`, never deletes. Cold mypy for a file importing textual is 13 s: mypy gets 90 s, the check input 120 s (was 40). (5) Each file is checked alone, so a name an earlier startup file made is `name-defined` like `tools`: declare it with a bare annotation (documented). `import-untyped` (installed, no types) and `no-any-return` (returning `json.loads(...)`) are strict findings the model will see; documented, not hidden.

mypy dependency: python-cordis-plugin depends on `mypy>=2.4.0.dev0` with `[tool.uv.sources] mypy = { git ..., rev = 539f6e6 }`, the root's own pin; `uv lock` (not by hand) changed uv.lock by two lines and still holds one mypy; `uv tree --package bh-02 --no-dev` lists mypy v2.4.0+dev.539f6e6 and `uv tool install ./bh-02/app` (into a scratch UV_TOOL_DIR) installed it. FOLLOW-UP: this git pin moves to `mypy>=2.4` from PyPI together with the root dev pin once mypy 2.4 is released (drop the plugin's source entry; comments in both pyproject.toml say so).

AC3 measured (this container, pinned uncompiled mypy 2.4.0-dev, a real bubblewrap jail via BrigJail, the whole first input of a new REPL: startup file + ruff + example rule + mypy, one project file with three typed functions, median of 5 REPL starts each, scratch script): no startup file 0.00 s; cold (empty `.bh-02/mypy_cache`) 3.27 s (3.16-3.43); warm 0.32 s (0.32-0.36). A project file that also does `import textual.app`: cold 13.46 s, warm 0.69 s (3 starts). mypy alone outside the jail on the same file: cold 3.06 s, warm 0.21 s (the brief's 5.3 s was a slower run; same order). The mypy line for CI and a pre-commit hook (`mypy --strict --config-file= .bh-02/startup.py`) is in python-tool.md, the plugin README and the `check-examples --help` text, beside the ruff line and `bh-02 check-examples`; a pre-commit hook `startup-mypy` and a CI step with all three lines.

Tests (all new fail without the code): test_python_startup_types.py (pure mapping with canned reports; closed set vs `mypy.errorcodes`; real mypy through the program: untyped def, type error, unfound import at top level and in a function, clean file, `tools: Any` declared / undeclared, sibling module and cwd module not found, config in cwd/HOME/XDG ignored with a planted plugin that did not run, MYPY* env scrubbed, copy under TMPDIR and removed, text on stdin, cache dir created with `.gitignore` and `git status` clean, unusable/damaged cache falls back, no cache dir keeps none, human output); test_python_tool.py (real worker, unjailed `Confined`: strict aside with all kinds, `import-not-found` to mypy and `ModuleNotFoundError` to the REPL, `tools: Any` keeps the REPL's `_Offered` and `echo` calls through it, undeclared is `name-defined`, default cache in the project, config key validation, python section sentences and size); test_python_repl.py (real bubblewrap: both files checked in the jail, the model's own mypy/ruff/rule commands run in it, cache `.gitignore`; a second start in a new jail reuses the cache: asserts warm < 0.7 x cold). Existing exact-aside tests updated by design (`_bare` now says `no-untyped-def`; a few files declare `show: Any` for a name an earlier file made).

Planted violations, each seen failing and restored: drop `--strict` from MYPY_FLAGS (28 failed, among them test_an_untyped_function_has_no_untyped_def); drop `--config-file=` (test_no_configuration_the_project_or_the_person_holds_loosens_it); do not strip MYPY* (test_a_startup_file_can_not_steer_mypy_through_the_environment); copy made and mypy run in the program's cwd (test_what_mypy_can_import_is_what_the_repl_can: {} != import-not-found); host accepts any code (test_a_code_outside_the_closed_set_..., test_the_aside_never_says_what_a_tool_wrote); no retry without cache (test_a_cache_mypy_can_not_use_...).

Proof (root unless noted): scripts/check bh-02/plugins/python-cordis-plugin exit 0 (format, lint, types, 173 tests, gates, docs; tokens skipped: no bh-01 dist). scripts/check bh-02/app --no-gates --no-docs exit 0 (210 passed, 1 skipped). scripts/arch-check exit 0 (needed `_mypied` in the purity budget, with its reason). su tester -c 'tini -s -- .venv/bin/python -m pytest -q -p no:cacheprovider -n 4 --dist loadgroup bh-02/plugins/python-cordis-plugin bh-02/app/tests/test_python_repl.py bh-02/app/tests/test_command_check_examples.py': 221 passed, 1 skipped (seatbelt). Not verified: scripts/linux-jail-check (the Docker daemon is not answering in this container: `Cannot connect to the Docker daemon`), darwin (seatbelt). AC #4 (scripts/check passes) is NOT ticked: the full scripts/check is the reviewer's.
<!-- SECTION:NOTES:END -->
