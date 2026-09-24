# cordis

The composition framework. `README.md` here is the authoritative design doc (the concepts, the
authoring rule, the guarantees, the module list, and "What is not here", the known gaps, which
are unfinished work rather than bugs); read it before non-trivial changes. This file is what it
doesn't say: how the code is laid out to keep that design true.

## Layout

Two chains of modules, each with a pure bottom that `import-boundaries` proves imports nothing
that owns a task, and an imperative top that performs what the bottom decides:

```
effects <- component <- decisions <- runtime <- inspection      the runtime
composition <- loader                                            the composition
authoring (component, effects)   testing (effects)               on the side
```

- **Every rule in `decisions.py` has its imperative half in `runtime.py`**: `resolve_target` ->
  `_refresh`, `affected` -> `_notify`, `decide` -> `_apply_target`, `after_setup` and
  `after_unload` -> `_lifetime`, `check_contract` -> `bind_step`. They are tested with no runtime
  in `tests/test_decisions.py`; keep new rules in that shape.
- **Reactivity:** a fiber's target is `Resolved` when every dependency has an ACTIVE provider,
  else `Unsatisfied`. `_notify` -> `_refresh` -> `decide` -> `_apply_target`.
- **A fiber's whole loaded lifetime is one task** (`_live`) inside one `AsyncExitStack`.
  `_perform_all` is the paper's effect iterator: perform what the generator yields, push the
  undo, send the result back, stop at the next step boundary once the target changed. Inertial
  chaining means a target change during a transition reinstalls without a new task.
- `_drain` makes a provider wait for its dependents before its own undos run.
- `settle()` is exact: transitions are counted as they begin and end, so there is no polling.
- `idle()` waits for owned background work and **re-raises the first failure**, so a dead
  session reaches the bootstrap instead of becoming a never-retrieved exception.
- `shutdown(grace=1.0)` cancels lifecycle tasks still mid-step after the grace period: a running
  step can only be awaited, and shutdown must end.
- `Context` is an immutable record, built at mount and never written. A key is a name; a
  dependency's class annotation is its *consumer's* contract, checked structurally in
  `_check_contracts` when the value is committed, before the first effect (the paper's
  key-collision problem, 6.6, closed on the consumer's side). `bind` accepts anything.
- A module assembled at runtime must be in `sys.modules` before `scan` can match its components.
- A row whose module fails to import in any way (a SyntaxError in a model-written plugin, say) is
  `unresolved` and reported, never fatal to the loader. The loader reloads on a layer-file
  change, but Python's import cache means an edit to an *existing* plugin module is not seen
  until the process restarts; a new module is.
- A component never touches the runtime: if it needs something from it, that is a new effect,
  not a new `Context` method.

`uv run pytest libs/cordis/tests/test_invariants.py -q` checks the paper's theorems over random
histories; run it after any change to `runtime.py`.

3.15 specifics: `frozendict` backs `Fiber.committed` and `Context.isolate`; `sentinel` (PEP 661)
is `Unsatisfied`. Test it with `if target is Unsatisfied:` (mypy narrows the rest to
`Resolved`), never `case Unsatisfied:` in a `match`, where a bare name captures anything.

## Public API

The root `cordis` (its `__init__.py` and `__all__`: what an author and a bootstrap need) plus
three documented modules: `cordis.loader` and `cordis.composition` for an operator (rows,
layers, plans, `read_layer`, `resolve`, the `Loader` handle) and `cordis.testing` for tests
(`drive`). Code outside cordis imports only those (`cordis-public-api`, in the root gate).
cordis's own tests may import internals (`test_invariants.py` reaches for `Resolved` and
`Unsatisfied` from `cordis.decisions`).

## The gate

cordis has its own `[tool.pypeeker]` in `pyproject.toml` here, run by `scripts/arch-check`:

- **`import-boundaries`** (`root = "cordis"`, strict): the two chains above. The pure modules
  (`effects`, `component`, `decisions`, `composition`) have empty or effects-only rows, which is
  what makes their purity a checked property rather than a habit. A new module under
  `src/cordis/` must get a row in `[tool.pypeeker.import-boundaries.allow]`, or the gate fails.
  A `TYPE_CHECKING` import counts as an edge, which is why `Step` in `effects.py` is
  `Callable[..., ...]` rather than naming `Context`.
- **`no-impure-functions`**: the `exclude` list is cordis's purity budget. Prefer the `decide`
  split (a pure rule in `decisions.py`, its imperative half in `runtime.py`) over lengthening it.
- **`over-exposed-module-symbol`** allow list: the `*_step` functions are there because a step's
  `__name__` is what an `Effect` renders in `explain()` ("performed: bind(greet, greet)");
  demoting one puts `_bind` in front of a reader. `cordis.loader:loader` is named as a string in
  layer files. `cordis.authoring:component*` is there because `@overload` declarations read as
  unused symbols.
