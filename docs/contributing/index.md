# Working on the code

This repository is one uv workspace: cordis, the libraries beside it, and the two programs built
on them. This page is how to find your way round it, set it up, and know when a change is done.

## The layout

| Path | What it is |
|---|---|
| `libs/cordis/` | the composition framework: components, effects, keys, fibers, rows, layers, the loader |
| `libs/cordis-helpers/` | small patterns on cordis with no domain in them: a broker's registry, a set of hooks, a row's own queue of work |
| `libs/host-paths/` | where the person's directories are, and every place reading a file goes through, for every package that trusts a file by where it is; standard library only |
| `libs/brig/` | a sandbox library that knows nothing of cordis or any app |
| `bh-02/app/` | the `bh-02` command (package `bh_02`): the shell that reads the layers and boots them |
| `bh-02/plugins/` | bh-02's plugins, one workspace member each, imported as `<name>_cordis_plugin` |
| `bh-02/CONTRACTS.md`, `bh-02/GLOSSARY.md` | the keys and shapes bh-02's plugins agree on, and its words |
| `examples/warden/` | a second program on cordis, a process supervisor: `app/` and `plugins/` |
| `pypeeker_rules/` | the architecture rules that span packages |
| `scripts/` | the repository's tools, `check` among them |
| `docs/`, `mkdocs.yml` | this site ([Building these docs](docs.md)) |

There is one `uv.lock` and one `.venv`, both at the root. The root `pyproject.toml` is not a
package: it lists the members by glob and configures ruff, mypy, pytest and the gates for all of
them. Every member has a `src/` layout and ships a `py.typed` marker, so mypy checks the imports
between members strictly.

A new member needs no registering: the member list, the test paths, the type-checked files and the
gates are all globs over the layout. Create its directory and run `uv sync --all-packages`.

## Setting up

You need [uv](https://docs.astral.sh/uv/). It fetches Python 3.15.

```sh
uv sync --all-packages
```

The code uses Python 3.15 on purpose: `except A, B:` without parentheses, annotations that refer
to names defined later, and the new builtins `frozendict` and `sentinel`. Leave these as they are.

## When a change is done

```sh
scripts/check
```

`scripts/check` is the one definition of green. It runs, in order: formatting (`ruff format
--check`), lint (`ruff check`), types (`mypy`, strict), the tests (`pytest`), the architecture
gates, the build of these docs, and, when bh-01 is checked out beside this repository, bh-02's
terminal theme against bh-01's tokens. Each step reports and the run goes on, so one pass shows
everything that is red; the exit code is non-zero if any step failed.

```sh
scripts/check bh-02/plugins/python-cordis-plugin   # the same for one member (the gates and docs still see everything)
scripts/check --no-gates --no-docs                  # skip the slower whole-workspace steps
```

The steps one at a time, from the repository's root:

```sh
uv run ruff format .                     # format
uv run ruff check .                      # lint; applies safe fixes (--no-fix only reports)
uv run mypy                              # types
uv run pytest -q                         # every member's tests
uv run pytest libs/cordis -q             # one member's
uv run pytest -m "not real_launch"       # skip the tests that start the real app in a terminal
scripts/arch-check                       # the architecture gates
```

Some tests need what a laptop may not have. The Linux jail's tests run in a container with
bubblewrap: `scripts/linux-jail-check` (Docker; CI runs it on every push). The tests against real
services (`pytest -m e2e`) need the Claude credential and skip without it.

## The architecture gates

The boundaries between packages are checked, not left to convention. `scripts/arch-check` runs
every [pypeeker](https://github.com/brukhabtu/pypeeker) gate: the root one, for what spans packages,
and one per library for its own layering. Among the rules: no package imports another (they agree
on keys and shapes in their CONTRACTS.md), only a plugin's `wiring.py` and the app's shell import
cordis, nothing reaches past cordis's public modules or into another module's `_private` names, a
package's `__init__.py` only re-exports, importing a module changes nothing, and functions are
pure unless a gate's budget names them. Run the gates through the script, never a bare `pypeeker
check`: the script builds the index first, and without one a check passes with nothing checked.
When a gate fails, its message says which rule and why; fix the code rather than widen the rule.

## Habits worth keeping

- **Error messages say what to do.** They are written for whoever meets them, and name the fix.
- **Prefer pure functions.** Work out a decision in a pure function, and apply it in a small one
  that does the I/O.
- **Tests import packages by name** and use fakes from a package's own `testing` module, never
  another package's tests. Give a test file a name no other member uses (`test_tui_render.py`, not
  `test_render.py`).
- **The Claude credential stays in `local.env`.** Never print, log or commit it, never copy it into
  a test or a command line, and never set `ANTHROPIC_API_KEY`. A test that needs it reads
  `local.env` and skips when it is absent.
