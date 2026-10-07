# cordis-helpers

Patterns built on cordis with no domain in them. `README.md` says what each one is; this file
is where things go and what the gate holds.

## Layout

- `src/cordis_helpers/registry.py`: `Registry[T]` and `Hooks[F]`. `__init__.py` only re-exports.
- `src/cordis_helpers/jobs.py`: `perform` and `Job`, a row's queue of its own work (bh-02's
  operator and `/compact` restart rows through one).
- `tests/test_helpers_registry.py`: tests through the public names; the one that runs a
  `Runtime` checks that contributors come and go as `acquire` undos without reloading the broker.
- `tests/test_helpers_jobs.py`: the queue, and the same on a `Runtime`: jobs one at a time, in
  order, and none after the row leaves.

## What belongs here

A pattern moves here once a second plugin needs it, and only if it names no domain: no keys,
no row ids, nothing about what the entries are. It depends on `cordis` alone. Anything that
knows about an app stays in that app's plugin; anything that is one of the paper's mechanisms
belongs in `cordis`.

## The gate

`pyproject.toml` here keeps its own `[tool.pypeeker]` gate, run by `scripts/arch-check` with the
rest. Everything under `cordis_helpers.*` is pure except the names in
`[tool.pypeeker.no-impure-functions].exclude`: the registrations and their removers, which
mutate their own registry by design. Adding a name there is a design decision; write the reason
next to it as the existing entries do.
