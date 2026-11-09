---
id: decision-0013
title: >-
  Trim cordis's authoring surface to four steps and the loader handle, with
  string keys, provides read from the body, and [[row]] tables
date: '2026-11-09 18:15'
status: accepted
---
## Context

cordis is to launch on its own, with docs for developers who have never met it. Writing those docs first (the draft is the artifact at https://claude.ai/artifact/WJfhEfnedKXDidAzJXGdaJ, which describes the names below ahead of the code) showed that the library's vocabulary was heavier than the idea it carries, and that several names were two words for one thing or the paper's word where a plain one exists. The owner worked through the vocabulary, the seven effects, and the two things an effect carries (a key and an undo) in conversation on 2026-11-09, against what the code in this repository actually does.

What the code says, counted on that date and excluding tests:

- `bind` is yielded 29 times, every key a string literal (82 of 82 `bind` keys across the family). `acquire` 40 times, calling 20 different methods on many objects, 23 of them literally named `register`, the rest hooks (`on_release`, `before_write`, `watch`, `add`). `enter` 8 times, every one something with a start and a stop (a subprocess, a worker, a model session, a transcript file, the history file, a running TUI app, the extensions worker), 7 of the 8 followed by a `bind` or `acquire` of the handle. `background` 3, `observe` 2 (both the TUI), `use` 1 (the extensions worker), `performer` 1 (sub-agents). No custom effect exists outside cordis.
- Nobody calls `Runtime.idle()`: bh-02 waits on the chat row's `done`, warden waits to be cancelled.
- Realms are used twice, both as a sealed subtree with its own loader (a sub-agent is `use(loader, expose=...)`, performed later from background work; the extensions worker mounts with `isolate` through the runtime it owns).
- The extensions worker reads `state` and `error` off the fiber `use` returns, to report a model-written row.
- 94 consumer Protocols across 29 plugin files, several shaping the same key independently (three `Queue`, three `Confirm`, two `Tools`); six copies of `_Registrar`. Five dependencies annotated `Any` (`tools` four times, `output` once).
- `provides=` is declared on 11 of the 12 files that bind; the one without is the extensions worker, which mounts model-written parts. `boot`'s pre-mount check reads declarations only, so a provider without the declaration makes its consumers reported as unsatisfiable although they will come up.

The paper cordis realises ("A Programming Paradigm for Spatiotemporal Composability", Shi, Zhang and Cui, arXiv:2608.25512) was read for its own names: its implementation (also called Cordis, the core of Koishi) has one primitive, `ctx.effect(callback)`, with `ctx.set(key, value)`, `ctx.get(key)`, `ctx.use(component, config)`, `ctx.isolate(key, realm)` and `ctx.intercept(key, metadata)` over it; the effect is the whole component body and each yield of the effect iterator hands back one inverse. Its section 6.6 names key collision and interface drift as open problems and lists three answers: key namespacing, peer dependencies (what Koishi does, with TypeScript module augmentation, so a consumer imports the provider's types), and structural compatibility, which is what this library does with consumer-owned `runtime_checkable` Protocols.

Alternatives considered and rejected, each with the reason:

- **Interfaces as keys.** The type object as the key makes provider and consumer import the same object, the coupling this family forbids between plugins. Resolution by shape alone loses the one thing strings give: a key a person can write in a layer file, read in `status()` and `explain()`, and a model can be told; and a `str` satisfies any Protocol that asks only for `__len__`.
- **A Protocol that carries the key** (`@contract("prices")` on the consumer's Protocol). Moves the string from the parameter name to a decorator, same count of strings, the signature stops saying what the part depends on, and a second rule is needed for an unannotated parameter.
- **A `provide=` keyword on `enter`.** It collapses the most common pair into one line and removes the leaked-pool footgun, but adds surface while the aim is to trim; the two-line form stays.
- **Every step carrying a key.** Natural for `provide`, `enter`, `mount`; a mere label for `register`, `observe`, `background`, which then means two things by one word, and the store fills with tasks nobody depends on.
- **Dotted keys replacing the broker** (`provide("tools.git_status", fn)`). Covers the 23 named-entry registrations and none of the 17 hooks, needs a second kind of dependency that does not reload on change, makes the runtime a provider of views, and pulls the paper's section 6.2 pattern into the core; it already lives in cordis-helpers as `Registry` and `Hooks`. Dotted keys stay as a naming convention for a generic provider (`git.client`), with no change in semantics.
- **Merging `enter` and `acquire`.** Either way costs more than the name: twenty methods returning context managers instead of removers, or an adapter that is `acquire` under another name.

## Decision

### Names

One word per idea, in code, layer files, `explain()` output, events and docs. A name an author types is a plain English word; the paper's words live in the design doc's correspondence table and the code comments.

| today | 0.2 | why |
|---|---|---|
| `bind` | `provide` | pairs with what the component declares; the paper never owned `bind` (its API is `set`, its lineage `provide/get`) |
| `unbind` event, `fiber.bound`, `Inspection.bindings`, `AlreadyBound` | `withdraw`, `fiber.provided`, `Inspection.provided`, `AlreadyProvided` | the same rename, carried through |
| `acquire` | `register` | what every one of its 40 uses does: add yourself to something you depend on; "register a callback" is programming English |
| `Effect`, `Effects`, `effect()`; the `Step` callable alias | `Step`, `Steps`, `step()`; `StepFunction` | the heaviest word in every author's first line, and closer to the paper, where the effect is the whole body and each yield one step of it |
| `use` (the effect) | removed from the author's surface; see children below | one real use; `use` is also a row field with another meaning |
| `observe` (the effect) | removed; `Loader.observe(fn)` returns its remover, reached with `register` | the loader is a component already provided under a key and the root row, so depending on it never reloads anything; the runtime still provides nothing |
| `performer` | internal to the loader | its one use outside the loader is "mount later", served by the group below |
| `[[plugin]]` table | `[[row]]` | a row is not a plugin; `parse_layer` refuses the old name with a message saying what to write |
| `component(..., provides=())` | removed; provides are read from the body | see below |
| `Runtime.idle()` | removed from the public API | unused; both apps have a better end condition |
| binding (noun), bootstrap, entry, coeffect | retired from docs | say what a key provides; your main function calls `boot`; a row; a dependency |
| `fiber`, `realm`, `Context`, `Inspection`, `reload`/`restart`, `component`, `key`, `contract`, `config` | kept | term-of-art words with no better plain equivalent, taught to the extender tier; `reload` and `restart` differ by cause |

### Keys

Keys stay strings. The parameter name is the key. A dependency's class annotation is the consumer's contract, a Protocol the consumer owns, checked structurally when the value is committed to it; the provider never imports it, so provider and consumer need no shared package. Dependencies are not read-only: a dependency is whatever its provider made, and the one rule is that a change to it that should vanish when the part leaves goes through a step. A registry is designed so that every changing method returns its undo, and `register` is how a consumer calls it.

### Provides

`@component` takes no `provides=`. At decoration, cordis reads every `provide("...")` in the function body; that set is `Component.provides`. The key given to `provide` must be a string literal there; a variable, an f-string or a constant is refused at import with a message saying so. Reading the source is exact for setup-time provides because an async generator cannot delegate: every step yielded during setup is lexically in the body. The activation check stays (a literal in a branch not taken is declared and never provided). The boot-time report, "no row provides it", becomes true for every row, model-written parts included. A key chosen by an operator (one database part mounted twice) is not a key but an entry in a registry. Source unavailable at decoration is an import error asking for the source (the extensions worker already writes model-written modules into `linecache`; a comment there says that is why).

### The author's four steps

A part is a list of changes to the world, each with its undo. There are four kinds of change an author can make, so four steps, every one with an undo and none expressible by another, because each exists to hand the runtime an undo that a dependency alone would leave with nobody:

| step | the change | the undo |
|---|---|---|
| `provide(key, value)` | share a value under a name, in the runtime's store | withdraw; dependents unload first |
| `register(fn, ...)` | put something of yours into a thing you depend on | what the call returned |
| `enter(cm)` | start something that must stop | its stop (`__aexit__`) |
| `background(coro)` | run work you own | cancel; a death is recorded on the part (`active, work failed`) |

`enter` decides only when the thing stops; who else may use it is the next line's job, by `provide` or `register`, and "nobody" is allowed. `with` is for what a consumer opens per use; `enter` is `with` for the lifetime of a part. The choice between `provide` and `register` is one question: should the parts using this restart when it changes?

Every step is described, in docstrings and docs, in two clauses: what happens now, and what happens when the part leaves. A small test in cordis's suite asserts that shape on the shipped steps.

### Children, lifecycle events and later composition live on the loader handle

Only loaders build the tree. `Loader` gains `mount(part, *, config=None, id=None, isolate=(), expose=None) -> remover` (performed through the loader's own performer; the child is a row, listed in `status()` and `explain()`), `group() -> AsyncContextManager[Group]` where `Group.mount(...)` has the same signature and everything mounted through a group is retired when the group exits, and `observe(fn) -> remover`. A row inside a sealed subtree depends on that subtree's own `loader`, so the tree still nests, built by loaders, and a child mounts in the realm of the loader its parent can see.

A child's lifetime is whose undo stack holds its retire, and the author chooses it by how they call:

| the child should die | write |
|---|---|
| when you leave, mounted during setup | `yield register(loader.mount, part, id=...)` |
| when you leave, mounted later from owned work | `mine = yield enter(loader.group())`, then `mine.mount(...)` from the task |
| with the program | `loader.mount(part, id=...)` as a plain call |

The default is the first two: a child dies with its part unless the author chose otherwise by calling `loader.mount` directly. That keeps today's behaviour for every existing use. The extensions worker reads a row's state from `status()`/`explain()` instead of holding a fiber. Sub-agents use a group, so they still end with the subagents row; a sub-agent that should outlive a reload of that row is a later decision, not a side effect of this one.

Checked in the runtime before accepting: `shutdown()` retires the loader, whose undos are its mounts in LIFO order, so anything mounted later through the loader is retired before the rows that were up at boot, including the part that asked for it; dependency draining still orders each retire after its dependents. Retire is idempotent, so a group's exit and the loader's own unwinding may both retire a child.

### Docs

The docs run ahead of the code and are the spec the renames are checked against: three tiers of vocabulary (author, operator, extender) with the paper's word beside each; the steps shown in parts taken from this repository with a trace of start and leave; a chapter-one program that runs end to end; the body-timing rules stated once. No analogy carries more than one chapter.

## Consequences

- Breaking for every layer file (`[[plugin]]` to `[[row]]`), for every plugin (`bind`, `acquire`, `use`, `Effects`, `provides=`, the TUI's `observe`, the sub-agents' `performer`), and for anything reading old `rows.jsonl` or trace output, which must accept both `bind`/`unbind` and `provide`/`withdraw`. bh-02 and warden are the only users, so this lands as one 0.2 series rather than a deprecation.
- Implementation, each its own task gated by `scripts/check` and `tests/test_invariants.py`, renames done with pypeeker or ast-grep and never by hand, docs after code so the page never names what does not exist, and the invariants test run after any change to `runtime.py`:
  1. `[[plugin]]` to `[[row]]`, with the refusal message.
  2. `bind` to `provide` family (events, `Fiber.provided`, `Inspection.provided`, `AlreadyProvided`, GLOSSARY and CONTRACTS).
  3. `acquire` to `register`.
  4. Provides read from the body; `provides=` removed from `component` and from the eleven files that declare it; the non-literal-key refusal; the `linecache` comment in the extensions worker.
  5. `Loader.mount`, `Loader.group`, `Loader.observe`; `use` and `observe` removed from the author's surface; `performer` internal; the extensions worker and the sub-agents row moved onto the handle; the TUI's two `observe` calls onto `register(loader.observe, ...)`.
  6. `Effect` to `Step` family, last, once the rename tooling has proven itself on the others.
  7. `Runtime.idle()` removed from the public API.
  8. The two-clause docstring test.
- Deferred, with the owner's "hold off": a shared `Registrar` Protocol in cordis-helpers for the six copies in the plugins.
- Left open: whether a sub-agent should outlive a reload of the subagents row (today and after this: no); an optional `name=` on `background` for `explain`, the one thing a trace cannot name.
- The README's design doc keeps the paper's words and gains a correspondence table (its own Table 2) from this library's names to the paper's; the launch docs use the plain words.
