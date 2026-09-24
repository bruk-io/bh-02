# cordis

Composition that can be added, replaced and removed while the program runs, with every
change undone in the right order when it is reversed. A Python realisation of "A Programming
Paradigm for Spatiotemporal Composability" (Shi, Zhang, Cui, arXiv:2608.25512), the model
under DeepSeek Harness.

cordis knows nothing about agents, models, tools or user interfaces. `bh-02` is one harness
built on it. This file is the design doc: the concepts, the one authoring rule, and how each
kind of author adds to a cordis program.

## The rule

A component is an async generator that yields effects. Keyword-only parameters are its
dependencies and `config` is its configuration. What it provides is what it binds; an
optional `@component(provides=("recent_prices",))` declares that up front and the runtime
checks it, failing the fiber at activation if it declared a key and did not bind it. The
runtime performs every effect and every undo; the author performs neither.

```python
@component
async def price_feed(*, feed: Feed) -> Effects:
    sub: Sub = yield subscribe(feed)  # a plugin's own effect
    buffer: list[float] = []
    yield background(pump(sub, buffer))  # a framework effect
    yield bind("recent_prices", lambda n=10: buffer[-n:])
```

`-> Effects` is how the shape is declared: it yields effects and receives their results.
A generator has one send type, so a result arrives as `Any`; annotate the target
(`sub: Sub = yield subscribe(feed)`) where the type matters.

## Concepts

**Runtime.** The one instance of the framework in a process. It owns the store and every live
fiber, and it is the only thing that performs effects and undos.

**Key.** A name: what a value is bound under, and what a dependency's parameter is called.
Two parties agree on a key by agreeing on a word, never by importing anything from each
other, which is what lets a provider and a consumer be written by people who have never met.

**Binding.** A value held under a key, owned by the fiber that bound it, removed when that
fiber unloads. What a component provides is exactly the set of keys it binds. A component
may declare that set with `provides=`, which is checked, not inferred: `check_provided`
fails a fiber at activation if it declared a key it never bound, and `unsatisfiable`, run
once by `boot` before it mounts anything, reports a row whose inject no other row's
declared `provides` covers. Neither infers a shape from what actually got bound; both read
only what a component's author claimed. A row's own `provides` never counts toward its own
`inject` — a fiber activates only once its dependencies are already bound, so a component
cannot supply itself.

**Realm.** A namespace for keys. `use(child, isolate={UI})` gives a subtree its own `UI`, so a
session's binding shadows the host's for its own consumers and nobody else's. `use(child,
expose={tools})` is the allowlist form, a sealed subtree: it sees only the exposed keys from
outside, and every other key it reads or binds is its own (nothing leaks in or out).

**Dependency.** A key a component needs, declared by a keyword-only parameter whose name is
the key. A component runs only while every dependency has a binding, and unloads before any
of them is unbound.

**Contract.** A dependency's class annotation, if it has one: the shape the consumer needs
the value to have, checked structurally where the value is committed to it, before the
component's first effect. A `runtime_checkable` Protocol is the form; nothing inherits from
it, and the provider never sees it. Two consumers may hold one provider to two contracts. A
mismatch fails the consumer with a message naming the key, the value's type and what it
lacks. `Any`, or no annotation, constrains nothing.

**Configuration.** A keyword-only parameter named `config`, built from its dataclass
annotation. A wrong or missing key is a TypeError naming the component, raised before any
effect is performed, so a component never starts half-configured.

**Effect.** A deferred step and its undo, as a value. A step is a plain function of the
fiber's context returning `(result, undo)`; `undo` is `None` when the step changes nothing
reversible. Effects are the only thing a component may yield and the only way it changes the
world.

```python
def subscribe_step(ctx: Context, feed: Feed) -> tuple[Sub, Undo | None]:
    sub = feed.subscribe()
    return sub, sub.unsubscribe


def subscribe(feed: Feed) -> Effect[Sub]:
    return effect(subscribe_step, feed)
```

The framework ships seven, written the same way: `bind` (put a value under a key), `enter`
(enter an async context manager; its `__aexit__` is the undo), `use` (mount a child),
`background` (run work this fiber owns), `acquire` (call a function whose return value is
its own undo: a registration that hands back its remover, the paper's revertible effect in
its purest form), `performer` (see below), `observe` (hear every lifecycle `Event` from now
on, the stream `--trace` prints; the undo stops hearing. A listener runs mid-transition, so
one that raises is taken off and its error kept on its fiber, never let through).

**Undo.** The inverse of one performed effect. Undos accumulate in order and run in reverse
when the fiber unloads. An effect that raises records no undo; the ones already recorded run,
and the fiber ends FAILED with nothing installed.

**Component.** A recipe: dependencies, a name, and the generator. Its identity persists across
versions and reloads. It has no state of its own and never touches the runtime.

**Fiber.** A component running: one per mounting, with a state (INACTIVE, LOADING, ACTIVE,
UNLOADING, FAILED), a target, a stack of undos, and a context. An ACTIVE fiber whose owned
background work died stays ACTIVE (it is not FAILED: its setup and its binds still stand),
but its `error` is set, and `Loader.describe`/`explain` say `active, work failed: ...`
instead of plain `active` for as long as that error stands. A fresh setup clears it, so it
does not outlive a later reload.

**Context.** A fiber's view of the runtime. Effects receive it; components do not.

**Performer.** The ability to perform effects on a fiber *after* its setup, for composition
that is not known then: a loader swapping one row, a session mounting what a model just wrote.
The undos it collects are still the fiber's, and it stops working when that fiber leaves.

**Scan.** `@component` attaches and returns the function unchanged, so importing a plugin has
no side effects and the decorated object is the plain function a test can drive.
`scan(package)` is what finds them, as a mapping from name to component.

**Row, layer, loader, plugin, bootstrap.** A row is `id`, `use`, `config`, `disabled`. Layers
apply in order: a new id inserts, an existing id replaces that row's fields. The loader is
itself a component whose children are the rows; `reload()` swaps only what changed, and the
loader calls it itself when a layer file changes on disk, so the layer files are the running
program's source of truth for whoever edits them: a person, a script, a model with a file
tool. A reload that fails is reported and changes nothing.
The loader binds its handle under `loader`, so a row can be an operator: `status()`,
`restart(*rows)` (a fresh fiber for each row; everything depending on them reloads, once
however many of them it depends on) and
`explain(row)`. One change at a time: a reload and a restart never interleave. A row whose
module fails to import in any way is `unresolved`, never fatal. A plugin
is a package that ships components and owns the keys they define, advertised by one
`cordis.plugins` entry point. The bootstrap is the only code that is not a component:

```python
booted = await boot([base_layer, user_patch])
await booted.runtime.idle()  # returns when no component owns running work
await booted.runtime.shutdown()
```

Not framework concepts, by design: tool, session, model, turn, prompt, agent, UI.

## Guarantees

A fiber activates only when every dependency is bound, and unloads before any of them is
unbound; during its own teardown its dependencies are still readable and its dependents are
already gone. Replacing a binding reloads exactly the fibers that depend on it. A failure
during setup reverts only what landed. Children, background work and entered context managers
are released with their owner, last acquired first. A consumer's contract refuses a value that
does not satisfy it before the consumer's first effect, not at call time. A FAILED fiber is
never retried; the fix is a new fiber.

`tests/test_invariants.py` asserts these as the paper's theorems over random operation
histories. **Run it after any change to `runtime.py`** - it has caught bugs the unit tests missed.

## How authors add

**A capability** is a name, a component that binds an implementation under it, and consumers
that declare it by that name. A consumer that needs a shape annotates the parameter with a
Protocol of its own; the provider imports nothing to satisfy it. Declaring `provides=`
makes the name a checked property of the component rather than something only `explain`
can diagnose after a fiber stalls waiting on it.

```python
@component(provides=("git",))
async def git(*, config: GitConfig, subprocess: Subprocess) -> Effects:
    client: GitClient = yield enter(GitClient(config.binary, subprocess))
    yield bind("git", client)
```

**A shared collection** is a broker (paper 6.2): one component binds the registry, and the
components that contribute depend on it by name and `acquire` a registration whose return
value is its remover. Nothing depends on a contributor, so contributors come and go without
reloading anyone; the registry's entries must each be their own (paper Def. 44), so any
subset can be withdrawn in any order.

```python
@component
async def git_tool(*, tools: ToolRegistry) -> Effects:
    yield acquire(tools.register, {"name": "git_status", ...}, git_status)
```

**A value is not a component.** A callable is a plain function, bound by a component that
supplies its dependencies, which is also how a family of callables gets one lifetime:

```python
@component
async def git_tools(*, git: GitClient) -> Effects:
    yield bind("git_status", partial(git_status, git=git))
    yield bind("git_diff", partial(git_diff, git=git))
```

**Testing** follows from decorators that attach rather than wrap: a callable is called with
fakes for its keyword arguments; a component is driven by hand, asserting on the effects it
yields; a step is a plain function called with a fake context.

```python
from cordis.testing import drive

effects = await drive(git_tools(git=GitClient("git", FakeSubprocess())))
assert [e.name for e in effects] == ["bind", "bind"]
assert effects[0].args[0] == "git_status"
```

`drive` runs the generator to the end, answering each yielded effect with the next item of
`replies` (or `None`), and performs nothing.

**Extending the framework** happens in one way: a new effect.

## Layout

Two chains, each with a pure bottom and an imperative top. The import-boundaries rule in
cordis's own `pyproject.toml` (`libs/cordis/pyproject.toml`) proves the bottoms import nothing that owns a task.

```
src/cordis/
  effects.py       values: Effect, effect(), Key, Undo, Effects; imports nothing from the rest
  component.py     pure: Component read out of a function's signature, configure
  decisions.py     pure: State, Resolved/Unsatisfied, and every rule the runtime acts on
  runtime.py       the shell: fibers, the store, the lifecycle, the seven effects, Performer
  inspection.py    Inspection(rt): the read-only view
  authoring.py     the @component decorator, scan, lookup
  composition.py   pure, imports nothing from cordis: Row, Entry, compose, parse_layer, plan
  loader.py        read_layer, resolve, the Loader handle, the loader component, boot
  testing.py       drive(): a component's effects, read off it without a runtime
tests/
  test_invariants.py  the paper's theorems over random histories
  test_decisions.py   the runtime's pure decisions, as functions
  test_effects.py     the value, the seven, and the performer's scope
  test_runtime.py     ordering, reactivity, realms, contracts, teardown robustness
  test_authoring.py   derivation, refusals, scanning, a plugin end to end
  test_loader.py      layers, plans, patches, reload, unresolvable rows
  test_testing.py     drive()
  test_cancellation.py  cancelling a waiter must not wedge the fiber it waits on
```

One runtime dependency, venusian, for attach-and-scan discovery. Python 3.15: the store's
committed views are `frozendict`, and `Unsatisfied` is a PEP 661 `sentinel` (test it with
`is`, never `case Unsatisfied:`).

## What is not here

A tool registry, model-facing projections, a compile step for model-written source, a session
log, an agent loop. Those are a harness's concerns (a plain chat needs none of them). Anything outside cordis
observes the runtime through `Inspection(rt)`; a component that wants the lifecycle stream
yields `observe`.

Not yet done, in rough order of value: a policy seam that sees each effect by name before the
runtime performs it; evicting a changed module from `sys.modules` on reload, so an edit to an
existing plugin's source takes effect (a new module already does); draining in-flight calls before a binding is
replaced; per-session realms wired into a harness (the primitive is `use(..., isolate={...})`,
proven in `tests/test_runtime.py`, but nothing composes a multi-session harness yet).
