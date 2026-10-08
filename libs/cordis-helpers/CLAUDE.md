# cordis-helpers

Patterns built on cordis with no domain in them, and the few plain functions every package of a
family must agree on exactly. `README.md` says what each one is; this file is where things go
and what the gate holds.

## Layout

- `src/cordis_helpers/registry.py`: `Registry[T]` and `Hooks[F]`. `__init__.py` only re-exports.
- `src/cordis_helpers/jobs.py`: `perform` and `Job`, a row's queue of its own work (bh-02's
  operator and `/compact` restart rows through one).
- `src/cordis_helpers/paths.py`: `config_home` and `walked` (and `MOST_LINKS`): where the
  person's configuration lives, and every place reading a path goes through. bh-02's kernel,
  models and context plugins hold the files they trust to the walk, and they and the app find
  the person's configuration directory with `config_home`.
- `tests/test_helpers_registry.py`: tests through the public names; the one that runs a
  `Runtime` checks that contributors come and go as `acquire` undos without reloading the broker.
- `tests/test_helpers_jobs.py`: the queue, and the same on a `Runtime`: jobs one at a time, in
  order, and none after the row leaves.
- `tests/test_helpers_paths.py`: `config_home`'s cases, and the walk over a table of links in a
  temporary directory (absolute, relative, the file itself, `..` after a link, a dangling one,
  a missing place) and a loop of links, which ends after `MOST_LINKS`.

## What belongs here

A pattern moves here once a second plugin needs it, and only if it names no domain: no keys,
no row ids, nothing about what the entries are. It depends on `cordis` alone. Anything that
knows about an app stays in that app's plugin; anything that is one of the paper's mechanisms
belongs in `cordis`. A plain function with no cordis in it belongs here only when packages that
may not import each other must compute the same thing exactly, and it too names no domain
(`paths`: the XDG configuration home, a link walk; never `bh-02`'s directory or file names).

## The gate

`pyproject.toml` here keeps its own `[tool.pypeeker]` gate, run by `scripts/arch-check` with the
rest. Everything under `cordis_helpers.*` is pure except the names in
`[tool.pypeeker.no-impure-functions].exclude`: the registrations and their removers, which
mutate their own registry by design, and `paths.walked`, which reads links (the analysis does not
see `os.readlink`, so the entry is the budget's honesty, not the gate's demand). Adding a name
there is a design decision; write the reason next to it as the existing entries do.
