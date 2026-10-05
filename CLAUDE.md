# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository map

A uv workspace, arranged by ownership. The root `pyproject.toml` isn't a package: it lists the
members (as globs), holds the shared dev dependencies, and configures ruff, mypy and pytest for
every member (also globs). There's one `uv.lock` and one `.venv`, both at the root. Each area
has a CLAUDE.md of its own; read it before working there.

- `libs/`: libraries with no app in them, each gated on its own.
  - `libs/cordis/`: the composition framework - parts that can be added, replaced and removed while the program runs. Its `README.md` is the authoritative design doc; `libs/cordis/CLAUDE.md` is the code layout and its gate.
  - `libs/cordis-helpers/`: conveniences built on cordis with no domain in them: `Registry[T]` (the paper's broker, section 6.2, minus what the entries are) and `Hooks[F]` (a set of callables, order-free). cordis stays the paper's mechanisms; a pattern goes here once a second use shows up.
  - `libs/brig/`: a standalone sandbox library that knows nothing of cordis or any app (`libs/brig/CLAUDE.md`).
- `bh-02/`: the coding harness. `plugins/` is its plugin family (one member per plugin, import name `<name>_cordis_plugin`), `CONTRACTS.md` their keys and shapes, `GLOSSARY.md` every term a bh-02 user meets (cordis's and bh-02's, one line each), `bh-02/CLAUDE.md` how the family and the running harness work. `bh-02/app/` is the app (package `bh_02`, the `bh-02` command: a Textual TUI over a CodeAct composition); its `README.md` is how it runs and the map of the compositions, rows and plugins.
- `examples/warden/`: a second example app on cordis (a process supervisor), `app/` + `plugins/`, with its own README and CONTRACTS.md.
- `pypeeker_rules/apps.py`: the custom rules that span packages. `scripts/`: repo tools. `backlog/`: Backlog.md task data.

Every member uses a `src/` layout (`<pkg>/src/<pkg>/`) and ships a `py.typed` marker, so strict
mypy type-checks imports between members. A uv member can't be nested under another project
directory (uv resolves workspace sources against the nearest project), which is why an app is
`<app>/app` + `<app>/plugins/*` with no `pyproject.toml` at `<app>/`. A new member needs no
registration: members, testpaths, mypy files, ruff `src` and the gates' `src` are globs over the
layout. Then `uv sync --all-packages`.

## Commands (run from the repo root)

```
uv sync --all-packages
scripts/check                                             # the one definition of green: format, lint, types, tests, gates
scripts/check bh-02/plugins/kernel-cordis-plugin          # the same for one member (the gates always see everything)
uv run pytest -q                                          # every member
uv run pytest libs/cordis -q                              # one member
uv run pytest libs/cordis/tests/test_runtime.py::test_name -q
uv run ruff format .                                      # format
uv run ruff check .                                       # lint; applies safe fixes by default (fix = true), --no-fix to only report
uv run mypy                                               # strict; checked paths come from [tool.mypy] files
scripts/arch-check                                        # every pypeeker gate (root, then libs/*); applies autofixes first, --no-fix to only report
uv run pytest -m "not real_launch"                        # skip the tests that launch the real app in a pty
scripts/sync-tokens [--check] [--bh-01 PATH]              # bh-01's token CSS -> bh-02's Textual theme (reads ../bh-01)
scripts/model-friction [--examples N] [--json]            # where models trip in bh-02 sessions here: wrong tools, errors, lost output, nudges
uv run bh-02                                              # the harness: a CodeAct session in a TUI, Claude through Claude Code on the subscription
uv run bh-02 --resume [ID]                                # continue this directory's newest session (or ID: whole, its start, or its last part)
uv run bh-02 sessions                                     # this directory's sessions, newest first
uv run bh-02 --no-jail                                    # the kernel runs with your permissions; every cell asks
uv run bh-02 --model opus                                 # choose the model by name (sonnet, the default, opus, haiku, or yours in ~/.config/bh-02/models.toml; a session keeps it; /model lists and switches)
uv run bh-02 --patch mine.toml                            # a layer of your own over the shipped composition
uv run bh-02 update-layer mine.toml                       # rewrite a layer that names rows bh-02 renamed or dropped (keeps mine.toml.bak)
uv run bh-02 --trace FILE                                 # every row's lifecycle event, appended to FILE
uv run pytest -m e2e                                      # the tests against real services (Claude Code on the subscription): only when asked, skipped without the token
```

bh-02's Claude credential is `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token` makes one) in
`local.env` (git-ignored, at the repository root). The model row (`models:model`, its
claude-code provider) reads that file itself and hands the token only to the Claude Code CLI it
starts. Without it bh-02 still starts, and each message answers with an error saying where to
put one. An OpenAI-compatible model in the models file may name another line of `local.env` as
its `key`, which the row reads per request and sends only as that request's header.

Formatting and fixing happen by default. A `PostToolUse` hook in `.claude/settings.json` runs
`ruff format` and `ruff check --fix` on every `.py` file Claude writes or edits, so don't
hand-format. Files changed outside Claude Code still need `uv run ruff format . && uv run ruff check .`.

pytest runs with `asyncio_mode = "auto"`, so async tests need no marker. Tests import members by
package name with no `sys.path` changes (brig is the one exception; see its CLAUDE.md). pytest
uses `--import-mode=importlib`, so test modules are named from the repo root
(`libs.cordis.tests.test_runtime`; a row naming a test module's component uses `__name__`) and
pytest itself accepts the same test file name in two members. pypeeker names a test module by
its path under `tests/`, so two `tests/test_x.py` are one module there: `check` still reports
each file's findings at its own path, but the index merges them (`pypeeker tree test_x` lists
both files' names as one module's, `pypeeker symbol test_x:name` can't tell them apart), so
refs, renames and `demote` on them are ambiguous. Keep test file names unique across the
workspace, a member's own prefix on a common name (`test_tui_render.py`, `test_fs_wiring.py`);
`conftest.py` is the one name pytest fixes (its fixtures are in the gate's allow list). Don't remove
`consider_namespace_packages = true`, and don't add `__init__.py` to the `tests/` directories:
either makes same-named test files collide, or a source directory shadow an installed package.

Python 3.15. The code relies on newer syntax and builtins: unparenthesised `except A, B:` (PEP
758), unquoted forward references (PEP 649), and the 3.15 builtins `frozendict` and `sentinel`
(PEP 661). Don't "fix" these. Comments marked `# 3.15:` are 3.15 features not adopted yet, and
each one says what blocks it. mypy 2.3.1 can't type a sentinel, so the root dev dependency pins
mypy to a GitHub commit (2.4.0-dev, uncompiled, a few seconds per run). Once mypy 2.4 is on
PyPI, switch back to `"mypy>=2.4"`.

## The architecture gates

`scripts/arch-check` runs every pypeeker gate: the root one (`[tool.pypeeker]` in the root
`pyproject.toml`, rules from `pypeeker_rules/apps.py`: what spans packages) and one per library
that keeps its own (`libs/*/pyproject.toml`: internal layering and purity budgets). It writes
each gate's `[tool.pypeeker].src` from the globs in `[tool.arch-check].src`, indexes every path,
then runs `check --strict`. **Always use the script, not a bare `pypeeker check`**: `check`
doesn't build the index, and against a missing index it passes silently.

Root-gate rules that apply everywhere (area-specific ones are in the area CLAUDE.md files):
- **`cordis-public-api`**: outside cordis, import from `cordis`, `cordis.loader`, `cordis.composition` or `cordis.testing`, never deeper.
- **`plugin-layering`**: a gate's units are every package under its `src/` paths; none may import another; `cordis` and `cordis_helpers` are what all may import. A package's own `__init__` re-export is fine; another package's tests are not (fakes live in a package's own `testing` module).
- **`init-reexport-only`**: a package `__init__.py` defines nothing; it re-exports.
- **`import-time-side-effects`** and **`no-hidden-global-mutation`**: importing a module builds and mutates nothing (each app's `__main__` and the kernel worker are allowed, listed by name in the rule's `allow`), and no function mutates module-level state.
- **`under-exposed-access`**: no reaching into another module's `_names`, and that includes tests. Test through the public API, or add what's missing to it.
- **`over-exposed-module-symbol`**: a public name used only inside its own module should be `_private`. A name that is public on purpose but unused in-repo (a component a layer names as a string, a click command, a console script) goes in that rule's `allow` list. Test patterns are there because pypeeker names a test module by its path under `tests/`.

Operational facts:
- **Privacy is by symbol name.** pypeeker decides it from the symbol's own name only, so an underscore *module* name doesn't make its contents private.
- **Rename with pypeeker, not by hand.** `uv run pypeeker demote <module:Symbol>` rewrites every reference. `uv run pypeeker privatize --rule over-exposed-module-symbol` does it in bulk but skips symbols in modules that use `getattr`. Every change is a transaction (`pypeeker rollback <tx_id>`).
- **pypeeker is pinned** to a `main` commit in the root dev dependencies. It's pre-1.0, so bump the pin deliberately.

## Conventions

- Error messages are part of the product: they're written for whoever wrote the component and should say what to do (e.g. `a component's parameters must be keyword-only (after \`*\`) ... bind it from one with \`yield bind(name, partial(fn, **deps))\``). Match that style when adding errors.
- **Prefer pure functions.** Everything gated is pure unless it is named in its gate's `[tool.pypeeker.no-impure-functions].exclude`, which is the budget. Adding a name is a design decision, not a formality. Before you add one, try the `decide` split - compute the decision in a pure function, apply it in a named imperative one - or move the work into an effect, which is what keeps most components pure. A method that mutates its own instance is fine by convention; the analysis still counts it. The analysis is a heuristic (it sees `print`, `open` and a stdlib denylist, not asyncio or importlib). Don't quote a count; `scripts/arch-check` is the source.
- **Which shape, when.** Yield a value and let a driver perform it when the sequence of effects is itself what needs testing, printing, replaying or undoing: more than one driver (runtime, test, dry run), or uniform treatment the caller cannot know about (undo order, a plan). That is why components yield and why the loader has `plan`. Call a `Protocol` and fake it in tests when the seam is a stateful capability with one driver and non-revertible effects (a terminal, an SDK session); in a composition the fake is a replacement row. Split a pure decision out of a loop when the loop carries state across iterations or has three or more branches; a loop with fewer decisions than that is the shell, and the shell is allowed to be a loop.
- **When a class earns its place.** A class is right when it is a value (a dataclass), when it holds state its own methods mutate (`Fiber`, `Runtime`, `Loader`), or when it is the shape a Protocol asks for. A method that mutates something other than `self` is a function that has been given the wrong first argument. A class whose methods only read through one stored reference is a namespace, which is what a module is for; the two deliberate exceptions are cordis's `Performer` (a component annotates it) and `Inspection` (a held view that keeps reading live state is the point of it).
- **The Claude credential lives only in `local.env`** (git-ignored, mode 600) as `CLAUDE_CODE_OAUTH_TOKEN`. The claude-code provider reads that file itself and passes the token only to the Claude Code CLI it starts (never into bh-02's own environment, never to a kernel or jail). Never print, log, echo or commit it, never copy it into another file, test fixture or command line, and never write `ANTHROPIC_API_KEY`. A test that needs it reads `local.env` the same way and skips when it is absent.

<!-- BACKLOG.MD MCP GUIDELINES START -->

<CRITICAL_INSTRUCTION>

## BACKLOG WORKFLOW INSTRUCTIONS

This project uses Backlog.md MCP for all task and project management activities.

**CRITICAL GUIDANCE**

- If your client supports MCP resources, read `backlog://workflow/overview` to understand when and how to use Backlog for this project.
- If your client only supports tools or the above request fails, call `backlog.get_workflow_overview()` tool to load the tool-oriented overview (it lists the matching guide tools).

- **First time working here?** Read the overview resource IMMEDIATELY to learn the workflow
- **Already familiar?** You should have the overview cached ("## Backlog.md Overview (MCP)")
- **When to read it**: BEFORE creating tasks, or when you're unsure whether to track work

These guides cover:
- Decision framework for when to create tasks
- Search-first workflow to avoid duplicates
- Links to detailed guides for task creation, execution, and completion
- MCP tools reference

You MUST read the overview resource to understand the complete workflow. The information is NOT summarized here.

</CRITICAL_INSTRUCTION>

<!-- BACKLOG.MD MCP GUIDELINES END -->
