---
id: decision-0008
title: >-
  Rebuild brig as a pure domain behind ports and adapters, with no backwards
  compatibility
date: '2026-10-17 14:57'
status: proposed
---
## Context

brig (libs/brig, about 15,000 lines, 63 modules, 127 test files, a 3,950-line SPEC) is layered by
stage: `core -> mech -> stack -> run -> probe`, with `runtime`, `proxy` and `trampoline` beside them.
The stages keep I/O out of `core`, `mech` and `stack`, but the rest mixes concerns:

- A jail type is spread over four packages: bwrap over `mech/bwrap.py`, `run/host.py` and
  `run/_supervised.py`; a container over `mech/oci.py` and three `runtime/` modules.
- Pure decisions sit inside the shell: grading in `run/jail.py`, the kill ladder's choices interleaved
  with signals and polls in `run/teardown.py`, verdicts beside the runner in `probe/`.
- Grades are stated by mechanisms and runtimes, then checked by batteries afterwards (law 10 by review,
  not by construction).
- The supervisor program is written to a 3.9 floor and kept out of strict mypy.
- One role has two names (`Supervisor` in code, "agent" in SPEC and the container modules); the layer
  table allows an `observe` layer that has no package; the trampoline was moved out of `mech` only to
  avoid `brig/mech/__init__.py`'s imports.
- The workspace's house rules (private by default, re-export-only `__init__`) do not apply to brig.

The owner, 2026-10-17: rebuild it with a focus on architecture, in the owner's Python dialect
(`philosophy:python-idioms`), with no backwards compatibility. Today's brig is frozen at
`archive/brig-v1/` as the reference; the live `libs/brig` keeps jailing bh-02 until the rebuilt one,
grown in its place, replaces it and the runner moves to its API. Already decided and carried in:
Python 3.15 everywhere, the supervisor included (decision-0007); the container is the jail
(brig decision-203); a root jail's supervisor holds no capability (brig decision-197); one name,
supervisor, never agent (TASK-0133).

What does not change: brig's ten laws (SPEC section 2). They are the security properties, not the
structure, and every rule below serves them. The measured facts in the archived SPEC's rulings (what
bwrap covers as root, why carve-outs need pins, the seal, `mount_too_revealing`, Docker's seccomp)
are evidence the rebuild reuses, cited by their old numbers.

## Decision

### The layout

```
libs/brig/src/brig/
  domain/            pure: imports the standard library's pure modules only
    spec.py          what a jail must enforce
    facts.py         what the host was observed to be, gathered before compile
    plan.py          a compiled jail as one value
    mechanisms/      bwrap, seatbelt, oci, rlimits, env_scrub, egress: Spec x Facts -> Step
    compose.py       the stack: fold steps into a plan; the compatibility matrix
    claims.py        what a plan claims, per axis and scope
    grade.py         claims x evidence -> report
    lifecycle.py     jail and process states, transitions as functions
    teardown.py      the verified kill ladder, as a generator of effects
    records.py       record shapes, identity checks before any action
    wire.py          the supervisor's messages, encoded and decoded
    effects.py       the effect values the generators yield
  ports.py           Protocols for what the domain needs done: Processes, Records, Containers, Clock
  adapters/
    host/            spawning, process identity, signals, the tether, records on disk
    bwrap/  seatbelt/  docker/
    supervisor/      the PID 1 program and the host's link to it
    drivers.py       run a generator of effects against a set of adapters; a dry-run driver
  probes/            batteries: plants with positive controls, run through adapters
  jail_types.py      bwrap, seatbelt, oci: each one value
  api.py             Jail, Process, the errors, to_dict and from_dict
  proxy/             the egress server: a standalone process
```

### The rules

Each rule is enforced by a gate or a test where one can enforce it; the enforcing check is named.

1. **Four rings.** `domain` imports nothing from brig; `ports` import `domain`; `adapters`, `probes`,
   `jail_types` and `drivers` import `ports` and `domain`; `api` imports all of them; nothing in brig
   imports `api`. `proxy` imports nothing from brig. (A pypeeker rule replacing `brig-layers`.)
2. **The domain does no I/O.** No import of `os`, `subprocess`, `socket`, `signal`, `select`, `time`,
   `threading`, `shutil` or `resource` under `domain/`; `pathlib` for `PurePath` only. Every fact enters
   as data (`Facts`, an effect's observation). (A pypeeker rule listing the modules, and
   `no-impure-functions` with an empty budget for `domain`.)
3. **Four uses of `class`.** A frozen dataclass for shape, a `Protocol` for a port, an `Enum` or
   `StrEnum` for a closed set, an `Exception` subclass for a failure. A class that holds changing
   state is allowed only in `adapters/`, with the invariant it guards in its docstring. No inheritance
   but from `Exception`, `Enum` and `Protocol`. (A pypeeker rule.)
4. **Data says what it is.** Tuples, never lists, in any domain type; `frozendict` for mappings;
   `StrEnum` for every value that is persisted or sent (grades, kinds, outcomes); a `TypedDict` with
   `closed=True` for every JSON shape (records, `jail.json`, wire messages); a `sentinel` where a fact
   is unknown, never `None` standing in for it. (mypy strict; a test that every JSON shape is closed.)
5. **What happens next is a value.** A function that decides returns an `Enum` member or a union of
   frozen dataclasses, and its caller ends its `match` with `assert_never`. Compile returns
   `Plan | Refused`; only `api` turns a refusal into an exception (laws 1 and 2 hold at the surface).
6. **Effects are yielded where decisions and I/O alternate.** Teardown and the lifecycle are
   generators of effect values; a driver per runtime performs them and sends back what it observed; a
   dry-run driver prints a plan. Elsewhere a decision returns one step. (Tests drive the generators
   by hand and pin the order of effects: verify before signalling, TERM before KILL, verify after.)
7. **Grades come only from evidence.** A mechanism produces claims, never grades; `grade(claims,
   evidence)` is the only producer of a report; evidence comes only from a battery that plants the
   violation with a positive control (law 10). (A test: every claim of every jail type has a battery,
   and a claim with no evidence grades `unenforced`.)
8. **A jail type is one value.** A frozen dataclass naming its mechanisms (a tuple), its runtime
   adapter, its supervisor adapter and its batteries; the registry is a `frozendict`. Adding a jail
   type is one entry and its adapters, and touches no other jail type. (A test that every entry is
   complete.)
9. **One word, one thing.** A glossary in brig's README names each term once: jail, jail type,
   instance, process, mechanism, step, plan, claim, evidence, grade, supervisor (never agent), driver,
   effect. Private by default; `__init__` re-exports only; `api.__all__` is the whole public surface.
   (The workspace's house rules applied to brig's gate: `init-reexport-only`, `under-exposed-access`,
   `over-exposed-module-symbol`.)
10. **Errors say what to do.** One `Exception` subclass per failure, every raise listed in its
    docstring (ruff DOC501 and DOC502, preview on), context attached with `add_note` at the adapter
    edge so the documented type is the one that crosses.
11. **Templates for anything spliced into another language.** The Seatbelt profile and the
    container's env file are rendered from t-strings; their renderers refuse a plain `str` by type.
12. **Python 3.15, every file.** The supervisor program included (decision-0007). No
    `from __future__ import annotations`; `lazy import` at entry points; generics in 3.12 syntax.
13. **The supervisor program is assembled, not copied.** It is stdlib-only; `domain/wire.py` is
    stdlib-only and pure; the file delivered into the jail is built from `wire.py` and
    `adapters/supervisor/program.py`, so the host and the program share one definition of every
    message. (A test that the delivered file is exactly those two, and that it imports nothing else.)
14. **Tests by what they prove.** `unit/` for the domain, no doubles; `functional/` with fakes only at
    the ports; `adapter/` for each adapter against the real thing (bwrap, Docker; Seatbelt on a Mac);
    `e2e/` for the batteries. One tier marker per test, enforced as today.
15. **SPEC follows the rings.** A new SPEC: the laws carried verbatim with their amendments folded in,
    then one section per ring; a behaviour change is still a SPEC change first, a dated ruling naming
    its task.

### The order

Each step is one task, sized when filed, behind today's API until the API step:

1. The domain's data and compile: spec, facts, plan, the mechanisms as functions, compose, claims.
2. Grading from evidence, and the batteries moved to `probes/`.
3. Teardown and the lifecycle as generators, with the host driver and a dry-run driver.
4. The host and bwrap adapters behind the ports; the supervisor program assembled, on 3.15.
5. `api.py`, and bh-02's runner moved to it (the one breaking change for the embedder).
6. The Docker and Seatbelt adapters; the old modules deleted; the gate's rules switched on in full.

## Consequences

- Every security decision is pure and reviewable in one ring; the real-jail suites shrink to adapter
  tests and the batteries.
- A jail type is one entry: a microVM or an ssh host is its adapters and a value, not four packages.
- A grade cannot be written without evidence; the honesty law is structural.
- bh-02's runner changes once, at step 5; until then it runs on the live brig unchanged.
- The rebuild is about as large as brig itself: six tasks at least, most size 3 to 5, Seatbelt's
  adapter waiting on a Mac.
- The archived SPEC's decision numbers stay valid as citations of measured facts; the new SPEC's
  rulings are numbered on from there (decision-204 on), so no number means two things.

## Open questions

- [ ] Does `proxy` (egress through an allowlisting proxy) come across in this rebuild, or after it?
- [ ] Do the batteries ship to embedders (`brig.probes` as API), or stay brig's own tests?
- [ ] Seatbelt: rebuild its adapter from the archive behind the port, unproven until a Mac run, or
  leave macOS on the archived brig until then?
- [ ] The new SPEC's numbering: on from decision-204 (proposed above), or a fresh series with the
  archive as history?

## Acceptance

Proposed 2026-10-17 by the orchestrator from the owner's calls in conversation (a rebuild focused on
architecture, the owner's Python dialect, no backwards compatibility, today's brig frozen at
archive/brig-v1). Awaiting the owner's acceptance.
