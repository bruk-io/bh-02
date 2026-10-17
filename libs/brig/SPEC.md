# brig — a sandbox composition library

Status: specification. Nothing below is implemented until a milestone says it
is. The name is a working name (a brig is a ship's jail).

brig runs untrusted processes inside composable, honestly-graded jails. It is
architecturally independent of any host project: it knows nothing about
sessions, agents, grants, stores, or logs. An embedder compiles its own policy
into a `Spec`, picks or composes a `Stack`, launches through a `Launcher`, and
gets back a serializable `Handle` and an `EnforcementReport` it can trust —
because every claim in the report is graded against what the mechanism can
actually deliver, and verified by probes rather than asserted.

## 1. Purpose and non-goals

**Purpose.** One contract over many sandboxing technologies — Seatbelt,
bubblewrap, Docker/OCI, Nix-provisioned closures, cgroup scopes, egress
proxies, plain POSIX rlimits — such that:

- Technologies compose (bwrap + nix closure + cgroup scope is one jail).
- Enforcement is reported per axis, graded, never rounded up.
- "No jail" is the empty composition, not a special case: the same `Spec` is
  always expressible and partial enforcement is always available.
- Jails are observable (console, events, state) without observation ever
  weakening or entering the security claim.
- Communication into and out of a jail happens only over declared, enumerated
  channels.

**Non-goals.** brig has no policy engine, no grant model, no notion of who is
allowed to ask for what — that is the embedder's trusted code. brig has no
resident daemon: nothing runs when no jail is running except helpers whose
lifetimes are tied to a jail. brig does not schedule, queue, or supervise
fleets of jails; it runs one at a time and hands the embedder a handle.

## 2. Laws

These are binding on every mechanism, launcher, and future contribution. A
change that violates one is a spec change first, code second.

1. **Honesty over strength.** A weak jail honestly reported beats a strong
   claim untested. Every axis of every report carries a grade; `detail` names
   the known gaps in prose. A mechanism that cannot deliver what the spec asks
   refuses (raises) — it never silently downgrades.
2. **Refuse, never downgrade.** Asking for a mechanism/stack/launcher by name
   gets that thing or an error. There is no fallback the caller did not write.
3. **The Spec is constant; only delivery varies.** Policy (denies, allows,
   limits, channels) is expressed identically whether it lands on a kernel
   jail or on nothing. What varies per stack is the grade each field earns.
4. **Observation is read-only or it is not observation.** Anything that can
   inject into the jail (a read-write attach, stdin) is a channel, declared in
   the Spec, subject to policy. Observation never appears in the enforcement
   report and never alters enforcement.
5. **Authority never travels inbound as data.** A message into a jail is only
   ever content. Everything a jailed process *does* with it exits back through
   declared channels where the embedder's policy applies. Corollary: a jail
   dialing or replaying its own inbound traffic gains nothing.
6. **Provenance is stamped by the deliverer.** Origin labels on inbound
   messages are written by trusted code at delivery time, never taken from the
   sender's claim.
7. **Control must not require cooperation.** Interrupt and kill are delivered
   by mechanism-level means that work when the jail is spinning, wedged, or
   hostile. Teardown reaches everything the jail contains (process group, tree,
   namespace, container), never a single process, and is verified; its
   deliverability is itself graded in the report, per scope: the jail's, and
   one process's. (Ruled 2026-10-15, decision-189, TASK-0079.06: the
   "namespace" case is a supervised bwrap jail, whose instance is a pid
   namespace that ends with its PID 1, §8; the grade at the process scope is
   TASK-0079.08's, and until a battery proves one no grade above `unenforced`
   is claimed. *Amended 2026-10-16, decision-196, TASK-0079.07:* each `Process` carries
   its `control` grade, `cooperative` at most, until the battery.)
8. **Events are evidence, never the boundary.** Telemetry is best-effort by
   nature. No security claim may rest on an event having been emitted.
9. **Nothing crosses the boundary anonymously.** The exclusivity claim —
   "these declared channels and enumerated shared media are the only ways in
   or out" — is a reportable axis with a grade, like any other. **Argv is one of
   the enumerated shared media.** Anything a mechanism transits through the
   child's command line is visible in `ps` to every user who can see the process,
   for as long as it runs; §5's `EnvPolicy.set` is the first case brig ships. It
   is counted in the enumeration and covered by the `channel_exclusivity` grade,
   never excused from it because the exposure is the host's rather than the
   jail's. (Ruled 2026-08-23, decision-093, P-13.)
10. **Prove gates by planting violations.** A probe or test that observes a
    clean run proves nothing. Every enforcement claim has a probe that
    attempts the violation and a positive control that proves the probe
    mechanism itself works.

## 3. The model

Six nouns. Everything in brig is one of these.

```
Spec ──compile──▶ Stack(Mechanisms) ──▶ Step ──create──▶ Runtime ──▶ Handle
                        │                                              │
                        └────────── EnforcementReport ◀── probe() ─────┘
```

- **Spec** — the provider-independent description of a jail: what it may
  touch, reach, consume, and how it communicates. Pure data with a subset
  algebra.
- **Mechanism** — compiles a slice of a Spec into real enforcement. Claims
  one or more axes; produces a `Step`; declares its denial signatures.
- **Step** — a mechanism's compiled output: an argv transformer, env
  additions, staged files, helper processes with declared lifetimes, launch
  feature requirements, and per-axis grades.
- **Stack** — an ordered composition of mechanisms. Validates coverage and
  compatibility, composes argv wrappers, aggregates the report. The empty
  stack is valid and grades every axis `unenforced`.
- **Runtime** — creates a jail's instance and controls it: `create`,
  `alive`, `destroy` (verified) and `supervisor`, the part inside the instance
  that starts, signals, waits for and stops its processes. Declares its kind
  and capabilities; refuses stacks whose requirements it cannot honor.
  `HostRuntime` (`brig/run/host.py`) is today's: host process groups, the
  exit wrapper, the tether, a sibling per exec. The `subprocess` launcher
  (§8) is the embedder's door to it. For a bwrap jail `create` starts brig's
  supervisor as the jail's PID 1 and every process is a request to it
  (decision-190, decision-191, decision-192).
- **Handle** — the running jail as the embedder holds it: serializable,
  rehydratable in a later process, owner of teardown, the anchor for
  observation and communication.

**The runtime replaces the launcher noun (2026-10-12, decision-178).**
Everything after compile had one implementation, hardwired to host process
groups, with no seam a container, a VM or a remote sandbox could fill
(decision-0001 in the workspace's backlog, its migration step 1). `run` now
names that seam as two protocols (`brig/run/runtime.py`): `Runtime`, the
instance (`kind`, `capabilities`, `create`, `alive`, `destroy -> KillReport`,
`supervisor -> Supervisor | None`, `None` meaning the jail can only be destroyed), and
`Supervisor`, inside it (`start -> ProcessRecord`, `signal -> bool`,
`wait -> int | None`, `None` at the deadline, `stop -> KillReport`). Their
records, `JailRecord` and `ProcessRecord`, are frozen data; `RuntimeKind`,
`Capability` and `Scope` are enums in `core` (`brig/core/runtime.py`; not in
`brig.core`'s exports until a caller outside brig needs one). Until a bwrap jail can hold an
instance with nothing in it (its supervisor, decision-0001 step 4), `create`
is launch-shaped: it takes the first process's argv and its record carries
that process. `HostRuntime` holds what the launcher, teardown, exec and the
tether did, unchanged; `SubprocessLauncher.launch` is its capability check,
`create` and a `Handle`; `Handle` keeps its fields and serialization
(`HANDLE_VERSION` unchanged) and delegates `alive`, `interrupt`, `wait`,
`kill` and `exec` to its runtime, a field `to_dict` does not carry (a
rehydrated handle gets `HostRuntime`). `brig.runtime.fake` is the second
implementation, pure, which drives `Handle` in the unit tier; it is the
first module of the `runtime` layer (§13), which nothing in brig may import,
and the layer-set pins (`test_m4_shape`, `test_m5_shape`, `test_m6_shape`)
record that layer as they recorded `proxy` (decision-133). No behaviour
changes: every other existing test asserts what it asserted. `Mechanism.runtime`
and the runtime kind in `CompiledJail` are step 2 (TASK-0079.03); `Jail`
and `Process` in place of `Handle` are step 3 (TASK-0079.04). Implementing
task: TASK-0079.02. (Ruled 2026-10-12, decision-178.)

**The part inside a jail is the Supervisor (2026-10-12, decision-180).**
decision-0001 and decision-178 named the protocol that starts, signals, waits
for and stops processes inside a jail `Agent`, after the agent of Kata and
other sandboxes. In a library whose first line says it knows nothing of
agents, the word reads as a dependency on one kind of embedder, and the part
is what a supervisor is: the process that holds the others. brig names it
`Supervisor` (`run.runtime`); `HostSupervisor`, `NoSupervisor` and
`FakeSupervisor` follow, `Runtime.agent` is `Runtime.supervisor`, and the fake
runtime's `has_agent` is `has_supervisor`. The same ruling keeps brig's code,
SPEC and README free of an embedder's concepts: an application (an AI agent,
its sessions, its configuration files) is named only as an example of a class
or as where a finding came from, never as something brig's behaviour depends
on. The threat tuples in `core.threats` that list a coding tool's files stay
data an embedder folds in, not a default of any preset. No behaviour changes:
tests change by names. Implementing task: TASK-0079.24. (Ruled 2026-10-12,
decision-180.)

**A Jail and its Processes replace the Handle (2026-10-12, decision-181).**
decision-0001's migration step 3a. The last noun becomes **Jail** (with its
processes): the running instance as the embedder holds it, and each process
in it a **Process**. Today's launch is `Jail.create` then `jail.start`;
today's exec sibling is a second `start`, the same call, recorded the same
way. brig keeps six nouns:

```
Spec ──compile──▶ Stack(Mechanisms) ──▶ Step ──create──▶ Runtime ──▶ Jail ──start──▶ Process
```

The ruling has three parts, one per section: the runtime's `create` holds no
process and every process is a `start` (§8); each process has a record and an
exit record of its own, out of every grant, and a jail is rehydrated with the
embedder's runtimes (§9); and the order in which `Handle` is retired, below.
Each part names its implementing task.

**The order `Handle` goes in.** Every step leaves brig's tiers, bh-02's
runner and `scripts/check` green:

1. TASK-0079.25: the records (§9) and `create` with no process (§8) under
   `HostRuntime`, the compile refusal that keeps every grant off the records,
   and the fake's own kind. `Handle` stays, as an adapter over them.
2. TASK-0079.26: `Jail` and `Process` in brig's public surface beside
   `Handle`, rehydration with the embedder's runtimes, `HANDLE_VERSION` 6,
   probes through `jail.start`.
3. TASK-0079.27: bh-02's runner moves to `Jail` and `Process`, still a jail
   per program (a jail per session is TASK-0074).
4. TASK-0079.28: `Handle`, `ExecHandle`, `SubprocessLauncher`, `kill_jail`,
   the launch-shaped `create`, `<jail_dir>/execs/` and `<jail_dir>/exit` are
   deleted, brig's remaining tests move, and the code blocks of §8 and §9
   are replaced by the shape in §9's ruling. No name is kept for
   compatibility. Until then those blocks, and every paragraph that says
   `Handle`, describe the code as it stands.

(Ruled 2026-10-12, decision-181.)

**`Handle` is gone (2026-10-12, decision-183).** Step 4 of the order above,
done. `Handle`, its `JailStat` and `stat()`, `ExecHandle`, `ExecRefused` and
`exec_in_jail`, `SubprocessLauncher` and its `launch`, `kill_jail`, and the
records helper that named a `Handle`'s first process from its stdio path are
deleted, and no code writes, reads or refuses `<jail_dir>/execs/` or
`<jail_dir>/exit` (the records refusal covers `procs/` alone, §9). What an
embedder calls instead: `Jail.create(compiled, runtime=HostRuntime(), ...)`
then `jail.start(argv)` for a launch, a second `start` for an exec, `destroy`
for `kill`, `Process.wait`/`interrupt`/`exit_events` for the first process's,
`Jail.from_dict(d, runtimes=...)` for `Handle.from_dict`. Three things the
launcher did now belong to the embedder, and the ruling says so rather than
hiding them in a helper brig keeps: a launch whose first `start` is refused
leaves a jail the caller destroys (bh-02's runner does, and so does brig's
own test helper), the capability refusal is `HostRuntime.create`'s
(`LaunchRefused`, unchanged), and the first process's stdio is that
`Process`'s. The dict's version constant is renamed `JAIL_VERSION`, since it
versions the jail's dict; its value stays 6, so the `version` a dict carries
is unchanged and nothing persisted needs a bump (the rulings above that say
`HANDLE_VERSION` are records of the name it had). Every exception
`Jail.create` and `Jail.start` document is re-exported by `brig.run`
(`LaunchRefused`, `JailDirInUse`, `HelperFailed`, `ExecWrapNotAPrefix`,
`TetherClosed`, `WorkloadSpawnFailed`, `NoSupervisor`, beside
`ExitStatusUnobservable`), so an embedder names them from the public surface,
never from a private module. brig's tests assert through `Jail` and `Process`
what they asserted through `Handle`; a test whose subject was `Handle` itself
now holds `Jail` to the same property. Implementing task: TASK-0079.28.
(Ruled 2026-10-12, decision-183.)

## 4. Axes and grades

The report's fixed vocabulary. Axes:

| axis | meaning |
|---|---|
| `fs_read` | what the process can read |
| `fs_write` | what the process can write |
| `network` | what the process can reach |
| `limits` | resource caps (cpu, memory, tasks, wall, output) |
| `env` | what environment the process receives |
| `channel_exclusivity` | declared channels + enumerated shared media are the only ways in/out |
| `control` | interrupt/kill deliverability without the jail's cooperation |

Grades, ordered:

| grade | meaning |
|---|---|
| `enforced` | resists a hostile process |
| `best_effort` | resists a hostile process, with a named gap in `detail` |
| `cooperative` | filters a compliant process only; a hostile one opts out |
| `unenforced` | nothing |

`cooperative` exists so the no-jail degraded mode (env scrubbing + rlimits +
proxy-via-env-vars) is expressible without lying, and so a report can never
conflate "kernel enforcement with an SNI gap" with "the process can ignore
this entirely." Field evidence (pyact's removed path guard, bypassed via `~`
expansion, `file://`, and prior-command symlinks) says cooperative *filesystem*
guarding fails reliably; brig does not offer a cooperative fs mechanism.

**Grades and axes are a plain `Enum`, never a `StrEnum`.** The order above is
semantic, not lexical — lexically `"best_effort" < "cooperative"` is true and
means the opposite of what the table says. Comparison goes through an explicit
rank (`Grade.is_at_least`); `<` between grades is deliberately a `TypeError`
rather than a wrong answer a type checker would accept.

**`best_effort` is defined by its named gap**, so a `Graded` carrying that grade
with an empty (or whitespace-only) `detail` does not construct. The other three
grades accept an empty `detail`. A mechanism that cannot name its gap grades
`cooperative` or refuses (law 1) — it does not claim `best_effort` silently.

**Floors.** A caller states minimums: `require(fs_read=ENFORCED, ...)`. A
stack whose aggregate report misses a floor is refused at compile time. Refuse
is the default posture; warn-and-continue is an embedder choice made by
lowering floors, never a brig fallback.

## 5. The Spec

```python
Spec(
    fs=FsPolicy(
        write_allows=(...,),      # roots the process may write under
        write_denies=(...,),      # carve-outs INSIDE write_allows
        read_model=DENY_LIST | ALLOW_LIST,
        read_denies=(...,),       # DENY_LIST: the policy; ALLOW_LIST: carve-outs
        read_allows=(...,),       # ALLOW_LIST mode
    ),
    network=NetworkPolicy(allowed_domains=(...,)),   # empty = deny all
    limits=Limits(wall_seconds, cpu_seconds, memory_bytes, max_tasks,
                  max_output_bytes),                  # 0 = uncapped
    env=EnvPolicy(mode=SCRUB | PASS, allow_names=(...,), set=(...,)),
    channels=(Channel(name, kind), ...),   # sockets: the runtime's channel directory (§10)
    shared_media=(...,),          # derived + declared; see §10
    provisioning=Provisioning(files=((path, digest), ...),
                              closures=(...,), env=(...,)),
)
```

Notes:

- **`write_denies` is new relative to prior art in the parent project** and
  exists for the self-escalation threat: a jail that can write `.git/hooks`,
  `.envrc`, or a tool's config file inside its granted workspace executes code
  *outside* the jail later. Every mechanism must compile carve-outs
  (deny-over-allow precedence, mount ordering, submounts).
- **Two read models, declared not layered.** Denylist (Seatbelt-native) and
  allowlist (container/bwrap/nix-native) are different shapes. A mechanism
  declares which model(s) it implements; compiling the other model through it
  is a refusal or an honest downgrade in the report, never silent.
- **Under an allowlist, `read_denies` is the carve-outs** — the read twin of
  `write_denies`, deny-over-allow. An allowlist denies by absence, but a secret
  can sit *inside* an allowed root: a credential file at the top of a
  workspace the jail may write, which is the ordinary shape for an embedder
  that jails a program working in its own repository. Until this ruling that
  secret had no spelling in an allowlist `Spec` at all (the field was refused
  as inactive), so the only allowlist jail over such a workspace was one that
  could read it. A mechanism compiles each carve-out against the trees it
  actually mounts: outside every one it is inert (absent is already denied);
  inside one it is masked; and where a mask cannot be made (for `bwrap`, a
  path that does not exist yet, §6) the `fs_read` grade drops and names it.
  The algebra is unchanged in shape: read denies union in the meet and grow
  in the denies clause under both models, and the two models stay
  incomparable. (Ruled 2026-09-28, decision-164. First embedder: a
  jailed Python process on Linux, whose project root is a write root and whose
  `local.env` is the credential it must not read.)
- **Threat lists ship as data, not defaults.** brig provides curated,
  documented tuples the embedder folds in explicitly:
  - `CREDENTIAL_READ_DENIES_HOME_RELATIVE` — `.ssh`, `.aws`, `.gnupg`,
    `.netrc`, `.config/gh`, `.docker`, `.kube`, `.npmrc`, `.git-credentials`,
    `.config/gcloud`, `.claude`, `.claude.json` (the two a coding tool keeps its
    credentials in, as examples of a class), …
  - `SELF_MODIFY_WORKSPACE_RELATIVE` — `.git/hooks`, `.git/config`,
    `.bashrc`, `.zshrc`, `.profile`, `.envrc`, `.vscode`, `.idea`, a tool's
    config files that later run code (`AGENTS.md`, `CLAUDE.md`, `.claude`: examples of a class), …
  - `BARE_REPO_TOPLEVEL` — `HEAD`, `objects`, `refs` (creating these at the
    workspace root turns it into a bare git repository, silently changing
    what every later git command means).
- **`EnvPolicy.set` is host-observable, and must not carry secrets.** The values
  in `set` reach the child through the **argv** of the compiled wrapper, so they
  are visible in `ps` to every user who can see the process, for as long as it
  runs. brig **declares** this rather than hiding it or silently repairing it:
  it is the embedder's contract, and it is the same posture as the parent
  project's law that credentials never enter a jail — a value the embedder
  cannot let the host see does not belong in `set`. The disclosure is owed here,
  in the Spec where an embedder reads it, and not only in a mechanism's module
  docstring, because the exposure is real and **brig is its cause** rather than
  an environmental hazard brig inherits. Law 9 counts it: argv transit is one of
  the enumerated shared media, so `channel_exclusivity` grading covers it. A
  **staged-file delivery** for sensitive values — written into `jail_dir` and
  read by the wrapper, never placed in argv — is a named future mechanism,
  deferred until a consumer exists (§15); it is deferred, not silently absent.
  (Ruled 2026-08-23, decision-093, P-13. **No code change**: the declaration is
  the deliverable, and `env_scrub`'s argv transit is what this bullet describes,
  not a defect it charters.)
- **Subset algebra.** `spec.is_subset_of(other)` and `spec.narrowed_to(other)`
  cover every axis at once: write allows shrink, write/read denies grow,
  domains shrink, limits tighten pointwise, env allow-names shrink, channels
  shrink (a child cannot declare a channel its parent's spec does not confer).
  Provisioning is outside the comparison (it is placement, not reach).
- **Six clauses, exactly** — one per dimension named in the sentence above, and
  `is_subset_of` is their conjunction, so "remove one clause" is a well-defined
  edit and each dimension is independently able to break subset-ness. Two
  sub-claims live inside a clause rather than beside it: read-model *equality*
  belongs to the denies clause, and `shared_media` shrinking belongs to the
  channels clause, because law 9 makes declared channels and enumerated shared
  media one claim. `EnvPolicy.set` participates in no clause — like
  `Provisioning`, it is placement, not reach.
- **A `PASS` env policy's reach is the top element of the comparison.** The env
  clause is not a plain allow-name subset, because `allow_names` is inert under
  `PASS` — a `PASS` policy already confers every variable, so a list beside it
  narrows nothing. Three cases, exactly: a **`PASS` parent admits any child**; a
  **`SCRUB` parent never admits a `PASS` child** (it cannot confer `PASS`); and
  **two `SCRUB` policies compare by allow-name subset**. Comparing `allow_names`
  unconditionally is what made a `PASS` parent with an empty list refuse a
  strictly narrower `SCRUB` child that named some. The env dimension keeps its
  independent ability to break subset-ness (see the clause above) through the
  `SCRUB`/`SCRUB` case, which is where it now lives. (Ruled 2026-08-23,
  decision-064, discharging decision-010 and decision-057.)
- **The two read models are incomparable, never converted.** A denylist spec and
  an allowlist spec are subsets of each other in neither direction, and
  `narrowed_to` refuses the pair (`IncomparableSpecs`) rather than translating
  between the shapes — that translation is the silent conversion this section
  already forbids.
- **`narrowed_to` is the pointwise meet**: the **greatest lower bound** — the
  most permissive spec that is still a subset of both operands, never the
  vacuously strongest one. Allows intersect, denies union, domains intersect,
  each limit takes the pointwise minimum with `0` read as uncapped, channels and
  shared media intersect; `env.set` and `provisioning` are carried from the
  receiver unchanged. It refuses (`IncomparableSpecs`) on differing read models,
  and on nothing else: a channel names no host path (decision-186, §10), so one
  name in both operands declares the same channel and the meet keeps it. (It
  also refused one channel name bound to a different endpoint in each operand
  until decision-186 took the endpoint away.) Every one of those per-axis formulas already *is* the greatest lower
  bound — an intersection, not an emptying; a minimum, not a `1` — which is why
  the earlier wording ("the strongest spec that is a subset of both") was a
  defect in the sentence and not in the algebra.
- **An allow entry is a subtree, and the allow axes compare that way.** A path
  in `write_allows`/`read_allows` confers the tree beneath it — that is what
  every mechanism already compiles it to (seatbelt's `(subpath …)`, bwrap's
  bind-mounted tree) — so comparing the two allow tuples as opaque sets of
  strings contradicted the mechanisms downstream of them. **The allow clause is
  reach containment**: a child allow is admitted when it is *at or under* some
  parent allow, so `/w/sub` narrows onto a parent allowing `/w` without the
  parent having to list `/w/sub` first. **The allow meet is the pointwise
  intersection of those trees**: for each pair of entries, the one nested inside
  the other survives and a disjoint pair contributes nothing — still the
  greatest lower bound, now computed over reach rather than over spelling.
  **Allow tuples are canonicalized to an antichain at construction**: an entry
  covered by another in the same tuple is dropped (`("/w", "/w/sub")` builds as
  `("/w",)`), because the two spell one reach and the order would otherwise stop
  being antisymmetric — `A ⊆ B and B ⊆ A` must still mean `A == B` on every
  compared field. Only the two allow axes change. **Denies are still compared as
  plain sets** (union for the meet, superset for the clause): union is already a
  correct lower bound whatever the nesting, and a set comparison on denies is
  *conservative* — it can only refuse a child a reach-aware comparison would
  admit, never admit one it would refuse. Making denies reach-aware is a
  separate, unforced change and is deliberately not made here. Nothing about the
  read models changes: an allowlist and a denylist spec remain incomparable, and
  no path is ever translated between them. (Ruled 2026-09-08, decision-160.
  Closes the gap recorded against `narrowed_to` since M1: narrowing to a subtree
  used to work only when the parent already named that exact subtree.)
- **The env meet, three cases, exactly.** **`PASS` is the identity**:
  `meet(PASS, X)` is `X`, in either operand position. That is a *consequence* of
  the bullet above rather than a separate rule — every env policy is a subset of
  `PASS` (the bullet on `PASS`-is-top, above), so `PASS` is the top element, and
  the greatest lower bound of the top element with anything is that thing. Two
  **`SCRUB` policies meet by allow-name intersection**. And **`SCRUB` absorbs
  `PASS`**: the meet of a `PASS` operand with a `SCRUB` operand is that `SCRUB`
  operand, **its allow-names carried through unchanged** — `meet(PASS,
  SCRUB{A,B})` is `SCRUB{A,B}`. The resulting mode is `SCRUB` if either operand
  is. **`SCRUB{}` is _a_ lower bound of every env pair; it is never _the_
  meet** — that collapse is what the word "strongest" used to license, and it is
  what this bullet exists to forbid. (Ruled 2026-08-23, decision-080,
  discharging decision-064's residual and, with it, decision-010's debt.)
- **A Spec is canonical and validated at construction.** Path tuples, domains,
  names and pair tuples are normalized when the object is built, so "equal up to
  normalization" is plain `==` and the algebra never renormalizes. Construction
  raises on a negative or non-integer limit, a duplicate channel name, an empty
  path or name, and on the *inactive* read-model field being populated
  (denylist mode with `read_allows`; allowlist mode with `read_denies` was the
  other half until decision-164 made that field the allowlist's carve-outs) —
  ignoring that field silently is the same refusal-not-downgrade posture as
  law 1. **The same refusal covers `EnvPolicy`'s inactive field**, the other one
  whose meaning depends on a mode: `EnvPolicy(mode=PASS, allow_names=(...))`
  raises, naming the field and the mode. That is what makes "`PASS`'s
  `allow_names` is inert" a fact rather than a convention, and it is why the
  bullet above can state the comparison in three cases without a fourth for a
  policy that cannot exist. (Ruled 2026-08-23, decision-064.)
- **`Channel.kind` is `LISTEN`, and nothing else** — §10's one *declared*
  inbound kind. §10's control kind is out-of-band and is not a declared channel;
  shared media has its own field above. There is no `DIAL` kind: the jail
  LISTENs and the trusted side dials (§10.1). **`MAILBOX` was deleted
  2026-09-08, decision-153**, with §10.2's whole primitive — see there. The
  field survives its own one-member enum deliberately: `kind` is already in
  every serialized `Spec` and `Handle`, so a second kind can arrive later
  without a `SPEC_VERSION` bump, and a one-member enum says "one kind" where
  removing the field would say "kinds are not a thing". What the deletion *did*
  remove is every branch that could only be taken by the other kind:
  `wait_ready`'s wrong-kind refusal (`NotAListenChannel`), seatbelt's
  LISTEN-only filter on `network-bind`, and the kind half of `narrowed_to`'s
  conflicting-binding refusal. A branch nothing can reach is not a safety net;
  it is a claim the code cannot honour. (Implementing task: this phase.)
- **`shared_media` is declared, not derived, in `core`.** The annotation above
  says "derived + declared"; the derivation (from `write_allows`, from a live
  pty) belongs to the layer that knows about mounts and ptys. `core` is pure and
  cannot compute it.
- **No shared `/tmp` by default.** A writable path shared between two jails is
  an unaccounted jail-to-jail channel. Temp space is per-jail, inside
  `write_allows`.
- **No write root grants the jail directory (2026-10-11, decision-173).** The
  `jail_dir` is brig's control state, not the workload's: the exec
  registrations teardown signals by (`execs/`, §9), the exit record `wait()`
  answers from (`exit`, §8), the stdio and helper logs, and the staged files an
  exec sibling is confined by again (seatbelt's profile). A write root is a
  subtree, so one AT or ABOVE the jail directory (a workspace that is `/tmp`,
  an embedder run from `/`) used to hand all of that to the workload: an embedder run
  with its working directory at `/tmp` let a jailed input write
  `<jail_dir>/execs/1.json`, `<jail_dir>/exit` and `<jail_dir>/x`, all seen on
  the host, and a malformed registration made the jail's own `kill()` raise
  (found by TASK-0078). So every mechanism that compiles `fs_write` takes the
  jail directory back out of whatever write root reaches it, and grants inside
  it exactly two things: **`<jail_dir>/tmp`, the jail's scratch** (an embedder
  points `TMPDIR` there, and allow tuples are an antichain, so a `Spec` with a
  write root above the jail directory cannot name a write root inside it: the
  scratch has to be brig's own name), and **a declared LISTEN channel's own
  grant**, unchanged (bwrap's endpoint directory, seatbelt's socket literal;
  §6). bwrap compiles it as mounts after the write roots (§6's stage list);
  seatbelt as `(deny file-write* (subpath JAIL_DIR))` after the write roots'
  allows, then `(allow file-write* (subpath JAIL_DIR/tmp))`, both before the
  carve-outs, since a later rule wins in either direction (the parent's probed
  order that `write_denies` already relies on). The rule is the mechanism's,
  not the `Spec`'s: `write_allows` keeps its
  meaning, the algebra is untouched, and the jail directory is never a `Spec`
  path. A write root strictly inside the jail directory, with none above it,
  is untouched: nothing reaches the control state through it. What this
  left open, and decision-174 closed: an endpoint whose directory IS the jail
  directory made that directory writable on bwrap, because that is the
  smallest grant a bind mount can make for a socket (§6). `fs_write` grades
  are unchanged: the rule takes writes away and claims nothing new. Implementing task:
  TASK-0079.13. (Ruled 2026-10-11, decision-173.)
- **A bwrap channel's endpoint is never directly in the jail directory
  (2026-10-11, decision-174).** bwrap grants a LISTEN channel its endpoint's
  DIRECTORY, bound read-write (§6), so an endpoint like `<jail_dir>/ctl.sock`
  made the whole jail directory writable from inside the jail: the exec
  registrations teardown signals by, the exit record `wait()` answers from and
  the logs, which decision-173 seals against every write root but could not
  against this grant. The compile now refuses that layout
  (`brig.mech.bwrap.ChannelInsideJailDir`, a `ValueError` propagated by `Stack`
  as the other bwrap refusals are), naming the resolved endpoint and the jail
  directory and saying to put the endpoint in a subdirectory of it. An endpoint
  in a subdirectory (`<jail_dir>/chan/ctl.sock`) needs nothing more: its
  directory is bound read-write, decision-173's seal keeps the rest of the jail
  directory read-only, and brig's own layout (`exit`, `execs/`, the logs) does
  not move. An endpoint elsewhere is unchanged (an embedder's own is in a directory of its
  own). seatbelt does not refuse it: its channel grant is the socket's own path
  (`(allow file-write* (literal ...))`), which opens nothing else in the jail
  directory, so the hole is bwrap's alone and a refusal there would reject a
  layout that is safe. The cost is a layout that compiles on darwin and is
  refused on Linux; an embedder that wants one layout puts the endpoint in a
  subdirectory everywhere, as brig's own journey does. Grades: unchanged (a
  refusal grades nothing). Decision-172's forged-record residual no longer
  stands for this arrangement. Implementing task: TASK-0079.16. (Ruled
  2026-10-11, decision-174.)
  Amended 2026-10-12 (TASK-0079.17, no new ruling): the refusal tests the
  endpoint's lexical parent as well as its resolved one, because bwrap binds
  the resolved directory writable at the lexical parent: `<jail_dir>/ctl.sock`
  as a symlink to a socket elsewhere would otherwise lay that directory over the
  jail directory's place in the jail. The message names both paths.
  Widened by decision-181 (§9, 2026-10-12): every mechanism that compiles a
  LISTEN channel refuses an endpoint at or under brig's records
  (`<jail_dir>/procs`, and `<jail_dir>/execs` while it exists).
  Amended by decision-184 (§10, 2026-10-12): when the Spec declares a channel,
  the seal keeps a third thing writable inside the jail directory, the
  runtime's channel directory `<jail_dir>/chan` (bwrap binds it, seatbelt
  grants its subpath), and a `write_denies` entry at or above it is refused.
  Restated by decision-186 (§10, 2026-10-13): a channel has no endpoint, and
  its one grant is the channel directory, a subdirectory brig names inside the
  jail directory, so no channel grant is the jail directory or reaches
  `procs/`, and `ChannelInsideJailDir` and `ChannelOnRecords` are gone.
- Serialization: `to_dict`/`from_dict`, versioned, round-trip stable.
- **The version is `SPEC_VERSION = 2`, and an unknown key at any level is a
  refusal.** (It was 1 until decision-186, §10, took the channel's `endpoint`
  away; a version-1 dict is refused like any other version.) There is no migration framework and no tolerated extra field: a
  dict brig cannot account for is rejected, not partially understood.
  `from_dict` re-runs construction validation, so serialization cannot smuggle
  in a Spec that could not have been constructed directly.

## 6. Mechanisms

```python
class Mechanism(Protocol):
    name: str
    axes: frozenset[Axis]                 # what it claims
    runtime: RuntimeKind | None           # the one runtime kind it needs, or None
    def compile(self, spec: Spec, ctx: CompileCtx) -> Step: ...

@dataclass(frozen=True)
class Step:
    wrap: ArgvTransformer                 # argv -> argv
    env: Mapping[str, str]
    staged: tuple[StagedFile, ...]        # profiles, scripts — written pre-launch
    helpers: tuple[Helper, ...]           # e.g. egress proxy; declared lifetime
    requires: frozenset[Capability]       # e.g. NEW_PROCESS_GROUP
    grades: Mapping[Axis, Graded]         # grade + detail per claimed axis
    denial_signatures: tuple[Pattern, ...]  # what this mechanism's denials look like
    events: EventSource | None            # optional sensor feed (§11)
```

**A mechanism names the runtime it needs; `LaunchFeature` is the runtime's
`Capability` (2026-10-12, decision-179).** decision-0001 (the workspace's
backlog, migration step 2) separates a jail's runtime from its confinement, and
composition has to know which runtime a stack needs before anything can grade
what that runtime alone decides. So `Mechanism` gains `runtime`: the one
`RuntimeKind` (`core`, §3) the mechanism's enforcement depends on, or `None`
for one that works under any. `bwrap` and `seatbelt` name `HOST`: each wraps
the workload's argv in a host process (`bwrap`'s namespaces, `sandbox-exec`'s
profile) that lives and dies with the host process group brig starts.
`env_scrub`, `rlimits` and `connect_proxy` name `None`; their wraps are execs
any runtime can run. A mechanism names at most one kind; a second runtime is a
second mechanism, and §7 refuses a stack whose mechanisms name two.
`LaunchFeature` is retired, as decision-0001 rules ("`LaunchFeature` becomes the
runtime's capabilities"): `Step.requires` is a `frozenset[Capability]`, the
same three members by value (`NEW_PROCESS_GROUP`, `PTY`, `DETACH`), so a
mechanism states its requirements in the runtime's own vocabulary and a runtime
checks them without translating. `brig.mech` no longer exports `LaunchFeature`
or its three module-level aliases; `Capability` is imported from
`brig.core.runtime`. The roster's axes, every mechanism's grades and every
compiled argv are unchanged. Implementing task: TASK-0079.03. (Ruled
2026-10-12, decision-179.)

**`CompileCtx`** is the context `compile` is handed, and nothing more: a frozen
dataclass carrying `jail_dir: str` (where staged files land),
`platform: str` (`sys.platform` as passed in), and
`resolved_paths: Mapping[str, str]` (below, defaulted to the empty mapping).
It is *data given to* a mechanism, never something a mechanism goes and finds —
`mech` performs no I/O of its own during compile, which is what keeps
`Mechanism.compile` a pure function of `(spec, ctx)` and therefore
unit-testable per §14. (Folded from the built shape by decision-044,
discharging decision-038's A3; the third field added 2026-08-24 by
decision-115.)

**Some kernels match paths after symlink resolution, and a mechanism may not go
and resolve them.** Seatbelt is the first: it matches *realpath'd* paths, so an
SBPL rule written against darwin's `/tmp/bgNNN` — itself a symlink to
`/private/tmp/bgNNN` — **silently matches nothing**. A rule that is present and
matches nothing is the exact failure this library exists to refuse, and it is
the parent project's own documented lesson. But `realpath` is I/O, and a
`compile` that performs it is a function of `(spec, ctx, filesystem)` whose
render golden becomes filesystem-dependent — which is the weaker-than-it-reads
shape arriving inside the pure functions §14 relies on. Both halves of the
resolution therefore live in `CompileCtx`, and the resolving is `run`'s:

- **`resolved_paths` is a `Mapping[str, str]` from a `Spec` path to its
  resolved form**, built by a `run`-layer helper — `run` being the layer
  permitted to touch a filesystem — and defaulted to the empty mapping so a
  spec needing no resolution constructs a context unchanged. A mechanism that
  needs a path **absent** from the map **refuses**, naming the path; it never
  falls back to the lexical form. **Refusal, not fallback**, is law 2's posture
  and the whole point: a missing rule is loud, a present rule that matches
  nothing is silent.
- **`jail_dir` arrives already resolved.** It is not a `Spec` path, so the
  mapping cannot cover it — yet the staged profile and the channel directory
  (§10) live under it, which would put the same bug in the one path the
  first half misses. The invariant is the same `run`-layer helper's to
  establish, and it is stated here because a caller constructing a
  `CompileCtx` by hand needs to know it.
- **What the render itself can check is lexical, and is named as lexical.** A
  pure function cannot *prove* a path is resolved — that needs an `lstat`. So
  the render's own guard refuses a `jail_dir` whose leading component is one of
  darwin's known symlinked roots (`/tmp`, `/var`, `/etc`). That is a guard
  against the documented trap, **not** a proof of resolution, and this sentence
  says so rather than letting a reader infer a stronger check than the code can
  perform.

The discriminating question for the whole arrangement, and the one the unit
tier asks: **can a mechanism's render golden run with no filesystem?** If it
cannot, the resolution leaked back into `compile`. (Ruled 2026-08-24,
decision-115, from `doc-017` §3's ambiguity A1. Implementing tasks:
**task-058** for the render's side and the lexical guard, **task-059** for the
`run`-layer helper's product and the refusal.)

**A second fact a mechanism may not go and get: whether a path EXISTS
(2026-09-08, decision-159).** `CompileCtx` gains `path_exists: Mapping[str,
bool]`, keyed exactly as `resolved_paths` is, built by the same `run`-layer
helper, defaulted to the empty mapping, and **refused** rather than defaulted
when a mechanism needs a key it does not carry. It is decision-115's shape
applied to a second question, and it is here because a mount-based mechanism
cannot express one policy in one primitive: a bind mount needs a source that
exists, and a tmpfs mount needs a mount point it may create. `bwrap`'s
`write_denies` is the case that forced it, and each of the three alternatives
was rejected for a reason worth recording, because each *reads* fine:

- bind only — fails the launch for every denied path that is not there yet,
  which is most of a fresh workspace's `.envrc`, `.git/hooks`, `CLAUDE.md`;
- bind-if-present (`--ro-bind-try`) — **silently skips** those, leaving the
  jail free to *create* the file it was denied, which is the self-escalation
  threat `write_denies` exists for (§5), reopened by a flag that reads like a
  convenience;
- tmpfs only — fails for a denied path that exists as a regular file, which
  is most of that same list once a workspace is a few days old.

So the mechanism branches, both branches enforce, and the compile-to-launch
window is a **refusal on both sides rather than a hole**: a denied path
created in it makes the tmpfs mount fail, one deleted in it makes the bind
fail, and a mount that fails is a jail that does not start. What a mechanism
may **not** do with this field is treat a missing key as "absent" — that would
put a guess exactly where law 2 forbids one. (Implementing task: this phase.)

**A mechanism claims an axis only when the spec gives it work to do on that
axis.** `axes` above is what a mechanism *may* claim; what it *does* claim for a
given `Spec` is the key set of its compiled `Step.grades`, and the two need not
be equal. `enforced` is reserved for a mechanism actually restricting something:
where the spec asks for nothing on an axis there is no policy to enforce, so
there is nothing to grade, and the axis falls through to §7's coverage fill as
`unenforced` exactly like an axis no mechanism declared. `env_scrub` under
`EnvPolicy(mode=PASS)` is the first case — it forwards the parent environment
untouched, which is byte-identical to what the empty stack does, and a grade
four ranks apart from identical observed behaviour is precisely the
grade-against-a-mechanism's-own-claim defect §4's "never grade up" exists to
forbid. Two constraints keep this from becoming a licence to under-report:
a `Step` may **not** grade an axis outside its mechanism's declared `axes` (the
declaration is a ceiling, not a hint), and §7's claim-conflict check still runs
**before** `compile`, off the static declaration — so two mechanisms declaring
one axis is refused even when one of them would have claimed nothing for this
particular spec. That is deliberately conservative: a refusal the embedder can
avoid by writing a different stack is law 2's posture, and a silently-resolved
double claim is not. (Ruled 2026-08-23, decision-092, P-12. Implementing task:
**task-044**.)

**`EventSource` lives in `mech`, and it is pure.** `Event` itself is data and
lives in `core` (§13) — a `ts` is a *field*, so nothing about the type reads a
clock. `EventSource` is the sensor feed a mechanism exposes, and it is a
`Protocol` in `mech` parameterized over `core`'s `Event`: it may not live in
`core`, because a live feed is not pure data, and it may not live in `run`,
because `mech` may import only `core`. Pure means what §13's `core` row means:
an `EventSource` never opens, writes, reads a clock or spawns — its methods
return payloads as data, and **`run` performs every write**, stamping `ts` and
`jail_id` as it appends. (Ruled 2026-08-23, decision-060, confirming
decision-052's guidance and closing decision-037's deferral. The Protocol's
method surface is implementation-defined in M3 and folded here retroactively at
the M3 closeout, on decision-044's precedent — decision-069.)

**`EventSource`'s method surface** — folded retroactively here at the M3
closeout, discharging decision-069, on decision-044's precedent. It is a
`@runtime_checkable` `Protocol` in `mech` over `core.Event`, with **two
methods**, one for each of the two shapes a mechanism's sensor can know:

- **`known_at_compile() -> tuple[EventPayload, ...]`** — zero or more facts
  already available the instant `Mechanism.compile()` returns, before the
  workload is launched. `env_scrub`'s scrubbed-name list is the motivating
  case. The **empty tuple** is the normal answer for a mechanism with nothing
  to report and is *not* a gap — `rlimits` returns it, for the same reason
  `env_scrub` declares the empty `denial_signatures` tuple above.
- **`classify_exit(outcome: ExitOutcome) -> EventPayload | None`** — given how
  the workload ended, what this mechanism's sensor makes of that ending, or
  `None` if it has nothing to say about *this* ending. `rlimits` recognizing a
  `SIGXCPU` termination as its own cpu limit tripping is the motivating case;
  `env_scrub` returns `None` for every ending, because scrubbing is a
  compile-time decision that no exit status reveals. `ExitOutcome` carries
  `returncode` in Python's own subprocess encoding — non-negative is an exit
  code, negative is `-signal_number` — so the classifier needs no I/O to
  obtain it.

**`EventPayload` is `(kind: EventKind, data: Mapping[str, DataValue])` and
nothing else.** `ts` and `jail_id` are `run`'s to stamp and never a mechanism's
to guess: a payload whose `data` carries either key **refuses at construction**,
rather than being silently overwritten downstream or silently trusted. `data` is
defensively copied at construction, the same posture as `Step.env` and
`core.Event.data`.

**`run` is the only layer permitted to stamp.** Wherever these methods are
called, the caller is `run`: it stamps `ts` and `jail_id` on each returned
payload. That is decision-069's second binding constraint, and it is what keeps
`mech` pure while every record still carries a real clock reading. (It said
"permitted to write" until decision-152 deleted the writing; the constraint is
unchanged, only its verb — §11.)

**The wiring, and where it finally landed (2026-09-08, decision-152).** For
three milestones this section carried a paragraph saying the opposite of a
wiring claim: M3 shipped both sensors and **no `run`-layer caller**, so the
text above was "a permission and a constraint on who may call — not a
description of an existing call site", and it said so out loud rather than
specifying from the design. decision-102 corrected the forecast once (the
wiring arrives with the first sensor mechanism, not with the probe engine) and
the wiring still did not arrive, because nothing was reading what it would have
produced.

It arrives now, and the reason it can is that the *destination* changed.
`Stack.compile` carries every non-`None` `Step.events` onto
`CompiledJail.sensors` — until now it assembled them and dropped them on the
floor, the declared-but-never-used shape this library refuses, hiding inside
the library's own composition step. `SubprocessLauncher.launch` calls
`known_at_compile()` on each, stamps `ts` and `jail_id`, and puts the result
on `Handle.compile_events`; the exit waiter calls `classify_exit()` when the
workload ends and `Handle.exit_events()` returns the stamped result. **`run`
is still the only layer that stamps, and it no longer writes anything at
all** — see §11. (Implementing task: this phase.)

**`connect_proxy` grades `cooperative`, always — never `best_effort` from
its own compile.** The roster row above offers `best_effort` "when paired
with an enforced transport confinement", and a `compile()` is a pure
function of one `Spec`: it cannot see the rest of the stack, so it cannot
know whether such a pairing exists. Grading from a hope about composition is
the "never grade up" law broken. Any upgrade belongs to whatever can OBSERVE
the pairing, and must still name the SNI gap that keeps it off `enforced`.
`NO_PROXY` is set to nothing, not even loopback: channels are UNIX sockets
that no proxy variable affects, so a loopback exemption protects nothing
while putting everything reachable on the host outside the allow list.
A spec that needs loopback egress names it in `allowed_domains` like any
other destination. And a `LAUNCH_SCOPED` helper's wait is BOUNDED — a
mechanism that declares a long-running process with the wrong lifetime gets
a named failure, never the silent wedge that shape produced before it was
bounded. (Ruled 2026-08-29, decision-134.)

*Amended 2026-10-11 (implementing task: TASK-0076).* "Set to nothing" means
SET, empty: the launcher passes the launching environment through, so a mechanism
that leaves `NO_PROXY` unset lets an inherited one (a host exempting loopback or
a cloud metadata range) reach the workload and put those destinations outside
the allow list. `connect_proxy`'s step therefore carries `NO_PROXY=` and
`no_proxy=`, both empty, which the launcher overlays on whatever it inherited.
(Ruled 2026-10-11, decision-170.)

**The egress filter is a standalone process, outside the layer DAG.**
`connect_proxy` is the only mechanism whose enforcement is a process rather
than a kernel configuration, and that process runs trusted-side, outside the
jail it filters for, spawned per jail as a `JAIL_LIFETIME` helper. It lives in
`brig/proxy/` with an EMPTY row in the `brig-layers` allow table: it may import
nothing from the library, and the gate enforces that. The reason is not tidiness
— this is what a possibly hostile workload talks to on every connection it
makes, so its import graph is both its startup cost (per jail) and part of its
surface. Anything it shares with the library crosses as argv or as a line in a
file, never as a shared object; its allow/deny decisions are appended as JSONL
to a path the proxy alone writes and a `run`-layer reader may fold in, which
§11's "events are evidence, not the boundary" makes safe to lose. (That file is
the PROXY's own, not brig's per-jail stream — the stream is gone,
decision-152, and this one is a helper process's stdout by another name.) (Ruled 2026-08-29,
decision-133.)

**Denial signatures** are part of the contract because probes and event
classification need to distinguish "denied by policy" from "failed for an
unrelated reason" (a probe that can't tell is vacuous). Each mechanism knows
its own: Seatbelt "Operation not permitted", bwrap "Read-only file system",
proxy "403", cgroup OOM exit 137.

**What a signature is matched against — the classification subject.** A
signature is a `Pattern`, and some denials are not text: `SIGXCPU` and the
"cgroup OOM exit 137" example just given are statuses, not stdout. So the
subject is neither raw stderr nor an exit code, but a **normalized denial
string** the probe engine builds per attempt: the workload's **stderr**,
followed by a **canonical termination summary line** carrying tokens of the form
`signal:SIGXCPU` and `exit:137`. Every signature therefore stays a regex, §6's
own example becomes expressible, and §14's both-directions unit rule stays
testable — a signature must match the real token and must **not** match a
generic failure ("command not found", "No such file"). A mechanism that has no
honest signature declares the **empty tuple** rather than a generic pattern;
`env_scrub` is the first such mechanism, because scrubbing produces absence, not
denial, and a generic pattern there would convert §12's `VACUOUS` outcomes into
false passes. (Ruled 2026-08-23, decision-068 and decision-067. `mech` declares
data in this shape; M4's probe engine builds the subject.)

**Helper lifetimes** are declared, not improvised: `JAIL_LIFETIME` (dies when
the jailed tree dies — implemented by pipe-EOF or pid-watch, the mechanism
chooses), `LAUNCH_SCOPED` (gone before the workload runs).

Planned roster (platforms in parentheses; grades are the *ceiling* each can
honestly earn):

| mechanism | axes | platform | notes |
|---|---|---|---|
| `env_scrub` | env | all | `enforced` — the child never receives scrubbed vars |
| `rlimits` | limits (cpu) | posix | exec-trampoline, no preexec_fn; `SIGXCPU` is real |
| `connect_proxy` | network | all | standalone HTTP(S) CONNECT filter; `best_effort` when paired with an enforced transport confinement, `cooperative` when only env-vars route to it; SNI-co-hosting gap named in detail |
| `seatbelt` | fs_read (denylist), fs_write, network (deny-all), channel binds | darwin | SBPL; empirical dialect knowledge carried as tested facts |
| `bwrap` | fs (allowlist-capable), network (netns) | linux | mount-order semantics; pairs with `connect_proxy` in-netns or `pasta` |
| `systemd_scope` | limits (memory, tasks, cpu quota) | linux | cgroups per-tree; closes what rlimits cannot; `--collect` |
| `oci_container` | fs (allowlist), limits, network | docker/podman | relay for channels; largest mechanism, lands late |
| `nix_closure` | provisioning | nix hosts | curated toolset as a store closure; isolation comes from whatever it is stacked with |
| `pasta` / `slirp4netns` | network | linux | filtered user-mode networking inside an unshared netns (closes bwrap's granted-domains gap) |

**The roster's second column is prose about a mechanism's job, and a job is not
always a claim.** `seatbelt`'s row reads "…, channel binds", which names *work*
the mechanism does — compiling the SBPL rules that let the jail bind a socket
in its channel directory (§10) — and **not** an axis it claims. Its declared `axes`
are **`{fs_read, fs_write, network}`**; `channel_exclusivity` is §4's axis
about declared channels and enumerated shared media being the only ways in and
out, and an SBPL profile does not establish that. So `channel_exclusivity`
falls through to §7's coverage fill as `unenforced` on a seatbelt stack —
unclaimed and ungraded, which is the honest reading, where declaring the axis
would oblige a grade and any grade would be a grade-up. Read every other row
the same way: `axes` is the mechanism's own declaration, in code and shipped as
data, and this table is its description. (Ruled 2026-08-24, decision-118, from
`doc-017` §3's ambiguity A5. Implementing task: **task-059**.)

**`rlimits`' hard limit sits one second above its soft limit (2026-09-08,
decision-161).** The roster row above says "`SIGXCPU` is real", and until this
ruling that was a claim about darwin only. The trampoline set
`RLIMIT_CPU` to `(N, N)`; **Linux checks the HARD limit first**, so a workload
that burned its `N` seconds there was `SIGKILL`ed, never signalled — and with
no `SIGXCPU` there is no `signal:SIGXCPU` for the mechanism's denial signature
to match, no `LIMIT_TRIP` event for `classify_exit` to emit, and §12's limits
battery reads `VACUOUS` where it should read `CONSISTENT`. Darwin raises
`SIGXCPU` at the soft limit whether or not the hard limit equals it, which is
why the pair survived every run this project had made: the whole suite had only
ever run on darwin. The trampoline now sets `(N, N + 1)`. `SIGXCPU` is the
observed ending on both kernels, `SIGKILL` one CPU-second later is still the
backstop against a workload that catches `SIGXCPU` and refuses to die, and the
cap the Spec asked for is still the soft one — `N` is what bounds the workload,
the extra second only exists so the signal can be delivered before the kill.
The grade does not move: `limits` stays `best_effort` (decision-061), for the
same cpu-only reason as before. (Found by running brig's integration tier on
Linux for the first time, in a container: an embedder's Linux check
script.)

**`bwrap`, as built (2026-09-08, decision-159).** The roster row above is the
plan; this is the shape, written from the built mechanism on decision-069's
discipline. It is an argv prefix and nothing else — no staged file, no helper,
no launch feature, no sensor (what it knows at compile time is its own argv,
which the `Handle` already carries verbatim, and a payload restating it would
be the copy decision-152 deleted the event stream for).

- **Allowlist, and only allowlist.** §5 says the two read models are declared,
  not layered; `bwrap` is the allowlist half exactly as `seatbelt` is the
  denylist half, and it **refuses** `DENY_LIST` (`ReadModelUnsupported`). The
  emulation was rejected on the merits: a denylist under bwrap means binding
  the host root read-only and masking each `read_denies` entry with a mount,
  and *a mount cannot mask a path that is not there* — so an entry naming a
  path the operator has not created yet would compile to nothing, silently, in
  exactly the credential directories that list exists for.
- **The mount order IS the policy**, because bwrap applies operations in the
  order they appear and a later mount stacks over an earlier one. One rule —
  later wins — with the stages ordered so that later means more specific:
  (1) `--unshare-all --as-pid-1 --cap-drop ALL --chdir /` (decision-190 and
  decision-177, below); (2) the jail's
  own furniture, `--proc /proc`, `/proc/sys` bound read-only over it
  (decision-177; for uid 0 or an unknown user only, decision-194) and `--dev /dev`, first among the mounts so every
  spec-derived mount stacks on top of it; (3) `read_allows` as `--ro-bind`; (4) the channel directory
  `<jail_dir>/chan` as `--bind` when the Spec declares a channel (decision-184,
  §10; each declared endpoint's directory too until decision-186);
  (5) `write_allows` as `--bind`;
  (5a) the pins (decision-168, below), but those in a sealed jail directory;
  (5b) when a write root or a channel directory is at or above the jail
  directory, the SEAL (decision-173, §5): the jail directory `--ro-bind` at
  every place a writable tree shows it, then its scratch `--bind-try` (a
  scratch that does not exist is left unwritable, failing closed), each
  channel directory inside it again, and the pins inside those; a pin or
  carve-out in the sealed part is not mounted, since a pin would undo the
  seal and a tmpfs mount point cannot be made on a read-only mount;
  (6) `write_denies` as submounts *after* the write roots — which is what
  makes deny-over-allow true here, and only the ones a writable tree (a write
  root or channel directory) reaches: one outside is unwritable already, and
  its `--ro-bind` would put into the jail a path the allowlist left out, a
  read grant made by a deny (2026-09-28, decision-165); (7) the `read_denies` carve-outs that exist
  inside a mounted tree (decision-164, below); (7a) `--perms 0444
  --ro-bind-data 0 /.brig-supervisor.py`, the supervisor's own program, after
  every mount (decision-190, below); (8) `--remount-ro /`, the
  jail's own root tmpfs made read-only, last of all (decision-166, below); (9)
  `--`, then the argv of the jail's PID 1, brig's supervisor, never a
  workload's (decision-190).
- **The jail's root is read-only (2026-09-28, decision-166), and until it was,
  "a write outside every write root is denied" was false.** bwrap builds the
  jail on a fresh tmpfs and makes every directory a mount hangs on (`/tmp`
  above a workspace, a workspace's parents) in it, and that tmpfs was
  writable: a write to a path no `write_allows` entry named, under such a
  directory or at `/`, landed in it and succeeded. It never reached the host,
  so it was not an escape, but it was a denial the `fs_write` grade claimed
  and the jail did not make, and a cell told "denied" by the policy was told
  "wrote" by the kernel. `--remount-ro /` after every mount fixes it; the
  mounts keep their own flags. (Found by the tests of an embedder's jailed Python process, the
  first to write outside the workspace at a path whose parent the jail had
  made: `tests/integration/test_bwrap_fs.py` pins it now.)
- **A jail started as root holds no capabilities, and its `/proc/sys` is
  read-only (2026-10-12, decision-177); until then, run as root, `fs_write`'s
  `enforced` was void.** bwrap run as root maps the jail's uid 0 to the
  host's uid 0 (`uid_map` `0 0 1`) and, unless told otherwise, leaves the
  workload every capability (CapEff and CapBnd full) over its own user and
  mount namespaces. So every read-only bind was a suggestion: the workload
  remounted one read-write (`mount -o remount,bind,rw`) and wrote through it
  to the host (TASK-0079.01's review did it on the host's `/etc`), and
  CAP_DAC_OVERRIDE read any root-owned file the jail could see, whatever its
  mode. Stage 1 now emits `--cap-drop ALL`: bwrap makes its mounts and then
  empties the workload's effective, permitted, inheritable, ambient and
  bounding sets, and it sets no_new_privs as it always does, so an `exec` as
  uid 0 gains nothing back and a setuid binary gains nothing. Dropping the
  capabilities is not the whole of it: the workload is still the host's uid
  0, and a sysctl's write check is its mode bits alone (the owner's, for the
  host's root), while bwrap 0.9 leaves `/proc/sys` uncovered (it covers what
  it can write to, and the `/proc/sys` directory itself is `r-xr-xr-x`). A
  capability-less root wrote `kernel.hostname` (measured, in the jail's own
  UTS namespace), and `kernel.core_pattern` or `kernel.modprobe` take the same
  check and run a program as the host's root. So stage 2 binds `/proc/sys`
  read-only over the jail's own proc (`--ro-bind /proc/sys /proc/sys`: bwrap's
  bind sources are the host's, and `--remount-ro` refuses a path that is not
  a mount point; the tree is the same either way, and `/proc/sys/net` answers
  for the reader's own network namespace). Measured after: CapEff and CapBnd
  empty, the remount `EPERM`, the write `EROFS`, a root-owned mode-000 file
  `EACCES`, the sysctl write `EROFS`, and an unmapped nested user namespace
  can't unlock a bind either (mapping uid 0 needs CAP_SETFCAP). The masks
  hold without CAP_DAC_OVERRIDE: the mode-0000 tmpfs and the `/dev/null`
  binds (`nodev`) refuse uid 0 like anyone, and the seal is a read-only
  mount. Considered and not taken: an unprivileged `--uid`/`--gid` inside.
  bwrap maps it to the host's uid 0 all the same, so the sysctl check is
  unchanged, and the workload would see its own files owned by a stranger.
  Both flags are emitted whoever runs bwrap, so the render stays pure (no
  uid on `CompileCtx`); for an unprivileged user they change nothing (no
  capabilities to drop, and a mapped uid that is not the host's root).
  *Amended 2026-10-16 (decision-194, TASK-0079.07): `CompileCtx` has a `euid` now,
  and the `/proc/sys` cover is emitted only for uid 0 or an unknown user.* No
  grade moves: the change makes `enforced` true as root, where it had been
  claimed and void. A host with no `/proc/sys` fails the launch, closed.
  Seatbelt has nothing to drop: its profile is mandatory access control the
  kernel applies to root too, and capabilities are a Linux notion; whether
  root under its `(deny default)` profile can remount or change a sysctl is
  unmeasured (no Mac in reach) and is carried to TASK-0079.15. Implementing
  task: TASK-0079.20; `tests/integration/test_bwrap_root_confined.py` plants
  the remount, the host write, the mode-000 read and the sysctl write as
  root. What a root jail can still write by its mode bits, listed from
  inside one by TASK-0079.20's review (`access(W_OK)` only, nothing opened):
  `/proc/mtrr` (its write needs CAP_SYS_ADMIN), `/proc/pressure/*` (a write
  sets a monitor on that open file and changes nothing on the host), the
  jail's own `/proc/<pid>` files (its own pid namespace) and bwrap's own
  `/dev` tmpfs (TASK-0079.22); `/proc/sysrq-trigger` is absent and
  `/proc/irq` and `/proc/bus` are read-only. (Ruled 2026-10-12,
  decision-177.)
- **Read carve-outs: masked where they exist, graded where they do not
  (2026-09-28, decision-164).** Each `read_denies` entry is compared, resolved,
  against every tree the render mounts (read allows, channel directories,
  write roots; at, under, or an ancestor of one). Outside all of them it
  compiles to nothing, because nothing is there. Inside one and existing, it is
  masked at stage 7: a file by `--ro-bind /dev/null` (bwrap binds `nodev`, so
  the open fails with EACCES rather than reading empty), a directory by
  `--perms 0000 --tmpfs … --remount-ro` (listing, reading beneath, writing and
  `chmod` all refused; measured). The kind comes from `CompileCtx.path_is_dir`,
  the third fact `run` observes for `mech`, and a missing answer is
  `UnknownPathKind`, never a guess. Inside one and **absent**, it is not
  mounted, and `fs_read` grades `best_effort` naming the path: a mask needs a
  mount point, and the mount point would be created on the host (next bullet),
  a `local.env/` directory where the person's credential file should go. That
  is the objection that rejected the denylist emulation above, met in the open:
  a file the host creates at that path after launch is readable, and the grade
  says so.
- **An absent `write_denies` path is created ON THE HOST, and it outlives the
  jail (measured 2026-09-28, decision-164).** The tmpfs form's mount point is
  made inside the write root's bind of the host directory, missing parents
  included: denying `.envrc` leaves an empty `.envrc/` in the host workspace,
  and denying `.git/hooks` in a directory that is not a repository leaves
  `.git/hooks/`. brig's own text had said "inside the jail". Two consequences
  are the embedder's: removing them after teardown, and never while the jail
  lives — a mount point removed on the host is detached inside the jail, and
  the jail then writes the very path it was denied (measured: `rmdir` of the
  host's `.envrc/` mid-run, then a write at `.envrc` from inside succeeded).
- **Every directory between a write root and a carve-out is pinned
  (2026-10-01, decision-168), and until it was, the workload could put a
  carve-out out of the way itself.** A carve-out's own mount can't be renamed
  or removed, but the directory it is in is writable: renaming `.git` to
  `.git-moved` took the `.git/config` and `.git/hooks` mounts with it, and the
  workload then made a new `.git/config` of its own where the host's next
  `git` reads it (`core.hooksPath`: code run on the host; measured by an embedder).
  Each such directory that exists is now bound over itself, read-write, before
  the carve-outs (stage 5a): a mount point, so it can't be renamed or removed,
  and as writable as before (a jailed `git commit` still works). The cost: a
  rename between a pinned directory and the rest of its write root crosses a
  mount and fails with `EXDEV` (`mv` copies instead; `os.rename` does not). An
  absent directory there is not pinned: bwrap makes it, as the mount point's
  parent, on the host (above), and the embedder that cares holds the topmost
  absent one instead. `pins` names them lexically and `run`'s
  `build_compile_ctx` observes whether each exists; a pin with no answer is
  `UnknownPathExistence`, never a guess. darwin's seatbelt needs no pin: it
  denies the path, whatever directory ends up there.
- **The channel directory is mounted BEFORE the write roots (2026-09-08,
  decision-163), and until it was, a `write_denies` carve-out inside a jail
  directory was compiled and then silently unmade.** The endpoint's directory
  is the one mount whose path policy does not choose — an embedder puts the
  socket in a subdirectory of the jail directory (directly in it is refused,
  decision-174, §5), and a jail directory that also HOLDS the
  workspace is the ordinary arrangement — so it is the one mount that can turn
  out to be an ANCESTOR of a write root or a carve-out. Emitted last it stacked
  read-write over both, and the jail could write the exact path `write_denies`
  named: mounted, then unmounted by the next line, with nothing anywhere saying
  so. Emitted at stage 4 it can only be stacked ON, which is what "later means
  more specific" asks for in the first place. What keeps the socket's own path
  safe from the carve-outs that now come after it is not order but the refusal
  below: an endpoint under a `write_denies` subpath is `ChannelInsideWriteDeny`,
  never ordered around — which makes that refusal load-bearing rather than
  defensive. (Found by running the e2e tier on Linux for the first time, in a
  container: an embedder's Linux check script, and
  `tests/e2e/test_strict_linux_journey.py` is where it showed.)
- **Source resolved, destination as the Spec wrote it.** Every mount names its
  source by the realpath'd form (so a symlinked path mounts the tree it
  actually points at) and its destination by the `Spec`'s own path (so the
  workload's view matches the policy that was written — a jail where `/bin/sh`
  is missing because `/bin` was normalised into `/usr/bin` is a jail that
  cannot start).
- **The LISTEN channel costs a writable DIRECTORY, where seatbelt's costs a
  path.** *Since decision-186 (§10) both grant the runtime's channel directory,
  and the per-endpoint grant this bullet describes is gone; the refusal at its
  end stands for a `write_denies` entry at or above the channel directory.* §10.1 makes each mechanism compile the crossing; seatbelt can name
  the socket's exact path because SBPL matches paths, but a bind mount needs an
  object that already exists and the socket does not exist until the jail binds
  it. So the smallest grant bwrap can make is the endpoint's directory, bound
  read-write — one path writable that no `write_allows` entry named. It is
  named in the `fs_write` grade's own detail, not only here, and a channel
  whose endpoint falls under a `write_denies` subpath is **refused**
  (`ChannelInsideWriteDeny`) rather than being ordered around: the carve-outs
  are mounted after the channel directory (decision-163), so a socket under one
  would be read-only, and the honest answer to that spec is a refusal.
- **Grades**: `fs_read`, `fs_write` and `network` all `enforced`, and nothing
  else claimed — `limits`, `env`, `channel_exclusivity` and `control` fall to
  §7's coverage fill unless another mechanism in the stack claims them.
  **`enforced` is against the workload, not the host (2026-09-30).** Every
  carve-out is a mount on the host's directory entry, and the kernel detaches a
  mount inside the jail when the host replaces or removes that entry. So two
  things done on the host lift a `write_denies` carve-out for the rest of that
  jail's life: renaming a file over a denied path (a host `git config` writes
  `.git/config` by rename; editors save by rename), and removing the empty
  directory an absent one is held by (the bullet on absent `write_denies`
  above). The workload can then write that path (measured by an embedder, before its
  tripwire). A new jail holds it again. The same is true of a masked
  `read_denies` file, which is why an embedder that holds secrets that way may
  grade `fs_read` lower; nothing in this mechanism can see the host
  do it, and the grade is not lowered for it: what it grades is whether the
  workload can get past a carve-out by itself, and it can't. Seeing it is the
  embedder's: an embedder can watch each carve-out's directory with inotify and
  end the jail at the first such change (the window that leaves is the
  embedder's to document). The mount can't be put back from
  outside: the host can't enter the jail's mount namespace (`EPERM`, measured;
  bwrap nests it in a user namespace of its own).
  `network` is deny-**all**: the netns is the whole enforcement, so a spec
  granting `allowed_domains` is refused (`NetworkUnsupported`) rather than run
  under a claim this mechanism cannot make. Per-domain egress needs
  `connect_proxy` *plus* a mechanism that puts networking back inside the
  namespace (`pasta`, `slirp4netns`), which is what the roster row's "in-netns
  or `pasta`" already says.
- **Denial signatures: `Read-only file system` and `Network is unreachable`,
  and deliberately no `fs_read` signature at all.** An allowlist denies by
  ABSENCE, so a read of an unmounted path fails with "No such file or
  directory" — precisely the generic text a signature may not match. Per §12
  that is a routing fact, not a gap: `fs_read` here is proved by an `ABSENCE`
  probe plus the battery's positive control, the same shape `env_scrub`
  already has. The `write_denies` tmpfs form has the same property for the
  same reason — an empty tmpfs is a *directory*, so a write AT a denied path
  is refused as "Is a directory" rather than with the read-only text; the
  write is denied either way, and the mechanism does not add a generic
  pattern to make the probe read better than it is.
- **Two flags not emitted, each for a reason that would otherwise be
  rediscovered.** `--new-session` calls `setsid()`, which would put the
  workload in a process group outside the one `Handle.kill`'s ladder and
  `Handle.interrupt` signal — law 7's "control must not require cooperation",
  broken by a hardening flag whose own benefit (no TIOCSTI on an inherited
  terminal) buys nothing against an `IoPolicy` that gives the workload
  `/dev/null` and no controlling terminal. `--die-with-parent` would be a
  second, mechanism-owned control path that no grade covers and no teardown
  rung accounts for, and it would not do what its name suggests: bwrap's
  parent is the launcher's exit wrapper, which is detached and outlives the
  embedder. A jail that should end with its embedder is a tethered launch
  (§8, decision-167), which every stack gets, not a bwrap flag. And no `--tmpfs /tmp`: §5 puts temp space inside
  `write_allows`, and handing the jail writable space nothing granted would
  make the `fs_write` claim false by exactly one directory.

(Implementing task: this phase.)

**bwrap's jail is made around brig's supervisor, and the mechanism says what
it runs (2026-10-15, decision-190).** decision-0001's migration step 4a, the
mechanism's half; §8 is the runtime's. Until now a bwrap jail was one `bwrap`
around one workload, so an instance held one process and a second one meant a
second `bwrap`, every namespace and mount again (`EQUIVALENT_PROFILE`, §9). A
jail that holds several processes in one instance needs something inside it to
start them, and what ends a jail at the process scope has to survive what the
workloads do. So the command `bwrap` runs is no workload but **brig's own
supervisor**, PID 1 of the jail's pid namespace, and a workload is a request to
it. Ruled:

- **The mechanism hands the runtime a plan.** `Bwrap.compile` returns a `Step`
  whose `supervisor` is a `SupervisorPlan` (`core.runtime`) naming the interpreter
  the supervisor runs under, and `Stack.compile` carries the one plan into
  `CompiledJail.supervisor` (two mechanisms declaring one is `SupervisorConflict`,
  law 2; seatbelt and every other mechanism declare none and compile exactly as
  before). The stack's whole composed wrap (the `rlimits` trampoline outermost,
  `bwrap`, `env_scrub` innermost) is applied once, to the supervisor's argv; a
  workload is never wrapped again, so the scrubbed environment and `RLIMIT_CPU` reach
  it by inheritance from the supervisor, as the decision says. The supervisor's own
  CPU time is bounded only by that same per-process limit, never by the sum over the
  jail: the gap the report's `control` detail names.
- **`--as-pid-1`, so the kernel drops every `SIGKILL` and `SIGSTOP` a process
  of the jail sends it** (measured by TASK-0079.01 with a bare PID 1, and again
  with the real supervisor, `tests/e2e/test_supervised_jail.py`), while a `SIGKILL`
  from the host still lands: the pid namespace ends with its init, and a `setsid()`
  child ends with it. `--chdir /` puts the supervisor in a directory the jail can't
  write: stage 8 makes the jail's root read-only.
- **The interpreter is `Bwrap(interpreter=...)`, `/usr/bin/python3` by default,
  `strict_linux(python=...)` through the preset, and a `Spec` that does not mount
  it is refused** (`InterpreterNotMounted`, naming the interpreter, the roots and
  what to change): the allowlist denies by absence, and a jail whose PID 1 cannot
  start is no jail. "Mounts it" is lexical, a read or write root at or above the path;
  a link inside the root that leads outside it (Debian's `/usr/bin/python3` is one,
  into `/etc/alternatives`) is the `Spec` author's to mount, and the supervisor's
  failure to start is reported with its stderr (`SupervisorFailed`, §8). The
  supervisor runs `python -I`: no working or script directory on its import path, no
  `PYTHON*` variable, no user site directory, as decision-169 holds every
  interpreter brig starts on the host to, and any Python 3.9 or later with `pidfd_open`
  (Linux 5.3) will do (tested here on 3.11, 3.12, 3.13 and 3.15).
- **Its program is delivered by `--ro-bind-data`, from the host's memory.** The
  runtime opens the source as an anonymous memory file and hands it to the jail's
  spawn as stdin; `bwrap` reads descriptor 0 to the end and binds a read-only copy
  at `/.brig-supervisor.py`, mode 0444, after every mount (stage 7a) so none stacks
  over it and before the root goes read-only (its mount point is a file in the
  jail's own tmpfs). Nothing on the host's disk is the source, so nothing a jail can
  write is, and `jail_dir`, which the allowlist hides, stages nothing. A `Spec` that
  names a path at or above that one (`/`, say) is refused (`SupervisorSourceCovered`):
  a bind of the host's root would make `bwrap` create the file in it. bwrap closes
  descriptor 0 when it has read it, so the supervisor's first act is to reopen
  `/dev/null` there, before anything else could take the number.
- **Grades don't move.** `fs_read`, `fs_write` and `network` are `enforced` as
  before (the `fs_read` detail now names the supervisor's program among what the
  jail holds), and `control` and `channel_exclusivity` stay `unenforced`, the
  `HOST` runtime's static grades, until a battery that plants survivors proves a
  higher one (TASK-0079.08, law 10). Seatbelt has no PID 1 to be and no
  namespace to end a process by; it keeps `EQUIVALENT_PROFILE` and a group-shaped
  stop, unchanged and untested here.

`render_bwrap_prefix` takes the interpreter as a required keyword and refuses
last among its own refusals (an unmountable `Spec` still reports a
`ChannelInsideWriteDeny` first). The preset's `python` parameter is the one
`confined_egress_darwin(python)` has. Implementing task: TASK-0079.06. (Ruled
2026-10-15, decision-190.)

**The `/proc/sys` cover is for a workload that can be the host's uid 0
(2026-10-16, decision-194).** decision-0001's migration step 4b, the mechanism's
half; §8 (decision-195) is the runtime's. decision-177 bound the host's
`/proc/sys` read-only over the jail's own proc for every user, because the
render stayed pure with no uid on `CompileCtx`. A process of a supervised jail
that has a pid namespace of its own needs a `/proc` for it, and the kernel will
not mount a fresh one in a mount namespace made by an unprivileged user
namespace while the jail's own proc has a mount over any of its directories
(`mount_too_revealing`: it wants one existing proc mount that hides nothing, and
a mount over `/proc/sys` hides the sysctls). Measured here, TASK-0079.07: with
decision-177's cover a nested `mount -t proc` is `EPERM` as an unprivileged user,
and without it works; a non-recursive bind of the covered proc is `EINVAL` too
(`has_locked_children`), so there is no way round it from inside. The cover guards
a workload that is the host's uid 0, whose sysctl writes the mode bits alone allow.
For any other user the files are root's and mode 0644 and there is nothing to
guard. Ruled:

- **`CompileCtx.euid`** is the effective user id of the process creating the jail,
  `None` when unknown (the default, so every hand-built context compiles as it
  did). `run.build_compile_ctx` sets it to `os.geteuid()`, the fact `mech` may not
  go and get (§6, decision-115). `render_bwrap_prefix(euid=...)` emits
  `--ro-bind /proc/sys /proc/sys` unless `euid` is known and not 0: an unknown user
  is covered, never guessed weaker.
- **As root nothing changes, and the per-process `/proc` is out of reach there.**
  bwrap run as root covers `/proc/irq` and `/proc/bus` itself (it covers each of
  `sys`, `sysrq-trigger`, `irq` and `bus` it can write to, with no flag to refuse
  it), and the jail's `--cap-drop ALL` leaves no process able to unmount them. So
  a jail run as uid 0 has no fresh `/proc` for a nested pid namespace, and its
  processes get the graded fallback (§8, decision-195). Making root work needs
  the supervisor to hold `CAP_SYS_ADMIN` at its start, long enough to unmount the
  covers and then drop it: capabilities in the jail's PID 1, which is a design
  question this ruling does not take. *Taken 2026-10-17, decision-197: not made.*
- **Grades don't move.** For an unprivileged user the cover guarded nothing, so
  `fs_write` is as `enforced` as it was, and its detail still names the cover
  where it is emitted. decision-177's "emitted whoever runs bwrap" is amended by
  this ruling; the rest of it stands.

Implementing task: TASK-0079.07. (Ruled 2026-10-16, decision-194.)

**A jail run as uid 0 gets no per-process namespaces, and its supervisor holds no
capability to make them (2026-10-17, decision-197).** The question decision-194
left: whether the supervisor of a jail run as root should keep `CAP_SYS_ADMIN`
to unmount bwrap's `/proc` covers and mount each process a fresh `/proc`. Not
made. A jail run as root has no user namespace around it, so that capability is
the host's own, not a namespace's; and since every start mounts a `/proc`, the
supervisor would keep it for the jail's life, not only at its start. Each fresh
`/proc` would also have to be covered again before the process runs, or uid 0
writes `kernel.core_pattern` (decision-177). A fault in a privileged PID 1 inside
every root jail would be a host escape, against a gain only a jail run as root
sees (a container or CI, where the container is usually the outer boundary).
Ruled:

- A jail run as uid 0 keeps decision-195's fallback: its processes share the
  jail's namespaces, the process scope is graded `cooperative` and the reason
  says so (decision-196). Its co-tenant rows (decision-0001's table) are shared
  media, named in each process's `channel_exclusivity` detail.
- What the fallback costs in practice is a stop that a child outside the
  process group survives (`setsid`, a daemon). That is closed without privilege,
  by a subreaper per process: TASK-0130, which rules on it.
- Running a root jail as an unprivileged host uid instead (a user namespace
  mapping onto a non-root uid) was weighed and not taken: files the workload
  writes would be owned by that uid, and a root-owned project would not be
  writable at all, decision-177's objection to `--uid`.

Decided by the owner in conversation, 2026-10-17. (Ruled 2026-10-17, decision-197.)

Deliberately absent: a cooperative filesystem guard (see §4), and `ulimit -u`
/ `RLIMIT_NPROC` anywhere (per-user on darwin and commonly on linux; capping
it strangles the operator's desktop and masquerades as a policy denial — a
finding both parent projects hit independently).

## 7. Stacks

`Stack(mechanisms).compile(spec, floors) -> CompiledJail`

**`CompiledJail`** is a frozen dataclass carrying `spec`, `report`, `wrap`,
`env`, `staged`, `helpers`, `requires`, `mechanism_names`, `matrix_version`
(and, besides, `signatures`, `sensors` and `runtime`, the last below).
The first seven are this section's composition outputs, in the shape §6's
`Step` produces them. The last two are what make a compiled jail *auditable
after the fact*: which mechanisms produced it, and under which version of the
compatibility matrix — a jail that cannot say what compiled it cannot have its
grades re-derived. (Folded from the built shape by decision-044, discharging
decision-038's A4.)

Validation, in order:

1. **Claims** — every axis claimed by at most one mechanism. Overlap is a
   compile error, not a grading question.
2. **Coverage** — every axis either claimed or entering the aggregate report
   as `unenforced`. No silent gaps.
3. **Compatibility & ordering** — a literal, versioned matrix of (mechanism,
   mechanism) pairs with an *ordering rationale* string per pair. Ordering is
   a security decision: the limiter wraps outermost so it also bounds the
   other mechanisms' helper processes; namespace creators nest in documented
   order; Seatbelt does not nest. Unknown pairs are refused.
4. **Floors** — aggregate grades meet the caller's `require(...)` or the
   compile refuses, naming the axis and the shortfall.

**The runtime, and the axes it grades (2026-10-12, decision-179).** A
compiled jail runs in exactly one runtime, so `Stack.compile` resolves exactly
one `RuntimeKind` from its mechanisms' `runtime` (§6): the kind they name, or
`HOST` when none names one (the empty stack included). Two mechanisms naming
different kinds are refused (`RuntimeConflict`, naming both mechanisms and both
kinds), after rule 3 and before any mechanism compiles: law 2, since no jail
can be two runtimes and picking one would be a fallback the caller did not
write. The kind travels on `CompiledJail.runtime`. Two axes depend on the
runtime rather than on any mechanism: `control`, at the jail scope (whether
the jail and everything in it can be ended without cooperation; decision-0001's
process scope travels on each process, not in this report), and
`channel_exclusivity` (whether declared channels and enumerated shared media are
the only ways in or out, which a relay or an exec's stdio decides). A runtime's
grades are static per kind (`brig.core.runtime.runtime_grades`), so the
coverage fill takes those two axes from the kind's grades instead of from
`unenforced_report()`, and rule 4 checks a floor on them at compile like any
other: `require(control=...)` above what the kind grades is refused at compile,
with a note naming the runtime kind. A mechanism that declares one of the two
axes still overlays its own grade, as on any axis; none does today
(`tests/unit/test_stack_runtime.py` pins that), and whether one may is the
first such mechanism's ruling. **`HOST` grades both `unenforced`, which is what
every report said before this ruling**: a jail is ended by signalling the
process groups brig started, and nothing yet proves that reaches everything in
the jail (a `setsid()` child leaves its group), and nothing establishes channel
exclusivity. No grade above that ships without decision-0001's control battery
(TASK-0079.08: planted survivors driven from the host, and a positive control,
law 10). What changes in a report is the two axes' `detail`, which now names
the runtime and the gap. The matrix keeps every row and its order, and
`MATRIX_VERSION` stays 5. Implementing task: TASK-0079.03. (Ruled 2026-10-12,
decision-179.)

**Coverage is a construction-time invariant, not a step anyone can forget.** An
`EnforcementReport` carries a `Graded` for all seven axes of §4; constructing one
with an axis missing raises, naming that axis. So rule 2 above cannot be skipped
by a mechanism, a stack, or a future aggregation path, and a floors check can
never pass merely because an axis was absent from the report.

Composition: argv wrappers compose inside-out per the matrix ordering; env
merges with later-wins declared conflicts as errors; helpers and staged files
union; `requires` union.

**Presets** are named stacks shipped as data, e.g.
`strict()` → darwin `[seatbelt, connect_proxy, rlimits]`,
linux `[bwrap, systemd_scope, pasta]`;
`degraded()` → `[env_scrub, rlimits, connect_proxy(env-routed)]` — the
no-jail-tech jail, honestly graded;
`scratch_darwin()` → darwin `[rlimits, seatbelt, env_scrub]` — a
kernel-enforced scratch jail on darwin, the smallest stack that reaches
`enforced` on `fs_read`, `fs_write`, `network` and `env` while `limits` stays
`best_effort`. **A preset's list is a MEMBERSHIP set, never a composition
order** — the Composition paragraph above is explicit that argv wrappers
compose inside-out *per the matrix ordering*, so no preset's bracket order,
here or above, may be read as declaring which mechanism wraps which. For this
preset the matrix composes **outermost→innermost as `rlimits`, `seatbelt`,
`env_scrub`**, which is rule 3's security decision and is fixed rather than
incidental: the limiter outermost so it bounds the
other mechanisms' helper processes, `seatbelt` next so the `/bin/sh` and
`/usr/bin/env` that `env_scrub`'s wrap spawns run *inside* the profile, and
`env_scrub` innermost so its `env -i` reaches the workload with nothing between
them to re-add what it removed. `channel_exclusivity` is unclaimed here and
grades `unenforced` (§6's roster note; since decision-179, by `HOST`'s static
grade). (Ruled 2026-08-24, decision-118 for the
preset and decision-119 for the ordering, from `doc-017` §3's ambiguity A4.
Implementing task: **task-064**, with **task-059** owning the two matrix rows
that carry the ordering rationale and **task-060** observing the ordering's
consequence from inside the jail.)

**`strict_linux()` → `[bwrap, rlimits, env_scrub]` (2026-09-08,
decision-159)** — a kernel-enforced jail on linux, the smallest stack that
reaches `enforced` on `fs_read`, `fs_write` and `network` there, and the linux
sibling of `scratch_darwin()`. **It is not `strict()`**, and the name says so
deliberately: `strict()` is defined above as linux `[bwrap, systemd_scope,
pasta]`, neither of which exists, and shipping a three-mechanism stack under
that name would be the silent substitution law 2 forbids. What it gives up
against `strict()` is exactly those two mechanisms' axes — `limits` stays
`best_effort` (`rlimits` reaches cpu only) and `network` is deny-all rather
than filtered. `channel_exclusivity` and `control` are unclaimed and grade
`unenforced` (since decision-179, by `HOST`'s static grades).

Membership, never composition order, like every preset here: the matrix
composes it **outermost→innermost as `rlimits`, `bwrap`, `env_scrub`** —
`rlimits` outermost so its cpu cap bounds bwrap's own namespace and mount
setup (a real process doing real work before the workload exists), `bwrap`
next so the `/bin/sh` and `/usr/bin/env` that `env_scrub`'s wrap spawns run
*inside* the jail rather than unconfined on the host, and `env_scrub`
innermost so its `env -i` reaches the workload. That middle ordering carries a
**precondition the preset does not enforce and will not hide**: under an
allowlist read model those two images have to be mounted, so a Spec granting a
workspace and nothing else compiles cleanly and produces a jail whose workload
cannot start. The preset does not fabricate mounts nobody asked for to paper
over that; it is stated in its docstring and here.

bwrap's four matrix rows arrive with it, two of them recording a pairing no
stack can compose — `{bwrap, seatbelt}` and `{bwrap, connect_proxy}` both
claim `network` twice, so rule 1 refuses them before rule 3 is consulted. They
are written anyway, because rule 3 refuses an **unknown** pair and "unknown"
is not the same claim as "impossible": a total matrix is what makes the
difference legible. (Implementing task: this phase.)

Presets keep CLI ergonomics and give
embedders a strength vocabulary; strength comparison between arbitrary stacks
is report dominance per axis, not a total order.

## 8. Runtimes (launchers until decision-183)

```python
class Runtime(Protocol):
    kind: RuntimeKind                        # HOST, FAKE, ... (§3)
    capabilities: frozenset[Capability]      # NEW_PROCESS_GROUP, PTY, DETACH, ... (decision-179)
    def create(self, jail: CompiledJail, *, cwd, jail_id, jail_dir,
               tether: int | None) -> JailRecord: ...   # holds no process
    def alive(self, jail: JailRecord) -> bool: ...
    def processes(self, jail: JailRecord) -> tuple[ProcessRecord, ...]: ...
    def process_alive(self, jail: JailRecord, process: ProcessRecord) -> bool: ...
    def tethered(self, jail: JailRecord) -> bool | None: ...
    def destroy(self, jail: JailRecord, *, grace: float = 2.0) -> KillReport: ...  # decision-193
    def supervisor(self, jail: JailRecord) -> Supervisor | None: ...
    def reserve(self, jail: JailRecord, channel: str) -> Reservation: ...      # decision-184
    def endpoint(self, jail: JailRecord, process: ProcessRecord) -> str | None: ...
    def ready(self, jail: JailRecord, process: ProcessRecord) -> bool: ...  # a connect
    def connect(self, jail: JailRecord, process: ProcessRecord) -> socket: ...  # decision-185

class Supervisor(Protocol):
    def start(self, argv, *, cwd, io: IoPolicy,
              channel: Reservation | None) -> ProcessRecord: ...  # every process
    def signal(self, process: ProcessRecord, sig: Signals) -> bool: ...
    def wait(self, process: ProcessRecord, timeout: float | None) -> int | None: ...
    def stop(self, process: ProcessRecord) -> KillReport: ...
```

- `HostRuntime` — host process groups: each start detached, in a new process
  group, stdio to files. (The `subprocess` launcher until decision-183.) In a
  jail whose stack declares a supervisor (bwrap's) only the first of those is
  host-started: the supervisor, PID 1 of the jail, and every other process is a
  request to it (decision-191).

**One launcher, and the roster is exactly what exists (2026-09-08,
decision-158).** This list held three entries at various times and never held
three implementations. A `tmux` launcher — a pane on a dedicated, named tmux
socket, "the rich console" — came off it at decision-154, because its whole
value was observation and the embedder owns that: brig hands back records and
a handle, and what a human watches is the embedder's surface, not a second one
brig maintains. `subprocess_pty` — "same, but under a pty teed to a ring/file"
— stayed, on the argument that it kept the capability underneath tmux without
the dependency. **It has never been written either, and a roster is not a
plan.** This document is the contract for the built shape (decision-069), and a
launcher named here that no caller can select is precisely the raising-stub
dishonesty §9's own law forbids one level up: `SubprocessLauncher.capabilities`
deliberately excludes `PTY` because claiming a capability it cannot deliver
would be law 1's grading dishonesty, and listing a launcher that does not exist
is the same lie at the roster level. So the roster is now the one launcher this
library ships. Nothing about the design changes: the launcher/enforcement split
is still the point — mechanisms are argv wrappers and rlimits ride a trampoline
rather than `preexec_fn`, so "watchable" and "jailed" remain independent axes,
and a pty launcher can be added by anyone who needs one without touching a
mechanism. What goes with `subprocess_pty` is only its entry here; `interactive
exec` (§9) and `console()` (§11) already state that they refuse or are absent
for want of the `PTY` launch feature, which remains exactly true.
(Implementing task: this phase — documentation only; no `tmux` or pty launcher
was ever written, and this deletes a plan, not code.)

**What the one launcher spawns is not quite the compiled argv (2026-09-08,
decision-156).** `SubprocessLauncher` runs the jail's argv under a tiny exit
wrapper of its own — see §9 — which spawns that argv unchanged as its own
child and records the status it ends with. The wrapper prepends nothing to the
compiled argv and applies no policy: `wrap_prefix` is still derived against
the stack's own `wrap`, `Handle.argv` still reports what the jail runs, and
the confinement the mechanisms compiled is applied to exactly the process it
was compiled for.

**A launch clears the exit record it is about to overwrite (2026-09-08,
decision-162).** `<jail_dir>/exit` is a fact about ONE launch, and `Handle.wait`
prefers it over any live observation (§9). So a second jail launched into a
directory that still holds the first jail's record answered with that record
*immediately* — before its own workload had run, which also meant its caller
read the empty stdio of a workload it had not waited for. `SubprocessLauncher`
now unlinks `exit` and `exit.partial` after creating the jail directory and
before staging or spawning anything. Nothing about the file's meaning changes:
absent still means "nothing recorded", never zero, and a record that survives a
launch is a record of that launch. This was found the first time brig's
integration tier ran on Linux — by `tests/integration/test_bwrap_fs.py`, whose
allowlist control is the only test that launches twice into one directory — but
the defect was never platform-specific, and its regression test
(`test_a_second_launch_in_one_jail_dir_does_not_read_the_first_status`) runs on
the empty stack, everywhere. *Settled 2026-10-12 by decision-181
(TASK-0079.25):* each process writes its own exit record under a fresh id
(`<jail_dir>/procs/<id>/exit`), so there is no shared record to clear; `create`
removes an earlier jail's records, once they are gone, as §9's records ruling
says, and the regression test still runs.

**A launch may be tethered to the process that made it (2026-09-30,
decision-167).** `launch(..., tether=fd)` takes the read end of a pipe whose
write end the embedder keeps and nothing else holds. The exit wrapper starts a
watcher before the workload, in the workload's own process group, that blocks
on that fd; once every write end is closed — the embedder closed it after
`kill`, or the kernel closed it because the embedder died, `SIGKILL` included
— the watcher sends `SIGKILL` to its group. The rung is the ladder's last one,
taken because nobody is left to run the others or read a `KillReport`. It
exists because a detached jail (`start_new_session=True`, the launcher's whole
shape) outlives an embedder that dies without calling `kill`, and a program the
workload left running in the background kept its grants with nobody holding
the handle (measured by an embedder: a killed host process's background program kept
writing the project). Five things about it are constraints, not description:

- **It is a pipe, not `PR_SET_PDEATHSIG`.** bwrap's `--die-with-parent` is
  still not emitted (§6): bwrap's parent is the exit wrapper, which is detached
  and survives the embedder, and a death signal follows the *thread* that
  forked, which in an embedder calling `launch` from a worker thread is not the
  embedder's life. A pipe's write end belongs to the process.
- **The watcher is a member of the group it ends**, so the group's number can't
  be handed to a stranger while it waits, and it outlives the wrapper: on darwin
  the workload is the wrapper's direct child and may exit by itself the moment
  its embedder goes, leaving a background program in a leaderless group. Since
  decision-181 every start has a group and a watcher of its own, each a member
  of the group it ends.
- **It ignores `SIGINT` and nothing else.** `interrupt` is for the workload;
  `SIGTERM` keeps its default, so `kill`'s first rung ends the watcher like any
  member and the verification rung still sees the group empty.
- **It reaches the workload group, nothing else.** Under bwrap that is
  everything: the namespace's init is in the group, and when it dies the kernel
  ends every process in the namespace, one that called `setsid()` included.
  Under seatbelt, which has no namespace, a process that left the group (a
  `setsid()`, a double-fork daemon) is out of reach — of `kill`'s ladder too,
  which is group-shaped. `JAIL_LIFETIME` helpers are groups of their own and
  are not tethered. *Amended 2026-10-12 (decision-181, TASK-0079.25):* exec
  siblings are tethered: every start's exit wrapper starts a watcher of its
  own on the jail's tether, so no process of a tethered jail runs untethered.
- **It does not serialize.** An fd can't cross `to_dict`; a rehydrated `Handle`
  has no tether and needs none, since the process that held the write end is
  the one whose death it watched. `tether=None`, the default, launches exactly
  as before.

*Amended 2026-10-12 (decision-183, TASK-0079.28):* the tether is
`Jail.create(..., tether=fd)`'s, held by the jail in memory, and every
`jail.start` is tethered to it; what this paragraph calls `launch` is
`create` plus a first `start`, `kill` is `Jail.destroy`, and the rehydrated
`Handle` is a rehydrated `Jail`, which has no `start` when it was created
tethered (§9). Each process's group has its watcher, and its exit wrapper
writes the process's own exit record, `<jail_dir>/procs/<id>/exit`.

**Every interpreter brig starts on the host runs isolated (2026-10-11,
decision-169).** brig starts four Python programs of its own outside any jail:
the exit wrapper (`python -c`), the tether's watcher the wrapper starts
(`python -c`), the `rlimits` trampoline (`python -m brig.mech.trampoline`,
outermost in every stack that has it, so on the host) and `connect_proxy`'s
egress proxy (`python -m brig.proxy`, a `JAIL_LIFETIME` helper). Each runs in
the workload's working directory, and `-c` and `-m` both put that directory
first on the import path — a directory the workload can write. Until this
ruling a `subprocess.py` the workload left there ran inside the next launch's
exit wrapper, unconfined (reproduced 2026-10-10 on the empty stack), and a
`signal.py` or a `brig/` package would have run in the watcher, the trampoline
or the proxy. So all four run with `-I`: no working or script directory on the
path, no `PYTHON*` variable from the environment the jail hands them, no user
site directory. Two constraints follow. **brig must be importable from the
interpreter's own `site-packages`** (an installed or editable install, whose
`.pth` `-I` still reads), never from `PYTHONPATH` or a working directory; that
is how every embedder already gets it. **A new host-side interpreter is added
with `-I` and to the list `tests/unit/test_host_interpreters.py` keeps**, which
finds every `sys.executable`/`python` argv in brig's source and fails on one it
does not name. Workloads, a probe's `python3 -c` among them, are the jail's
argv and are not brig's to isolate. (Implementing task: TASK-0075.)

A launcher refuses a `CompiledJail` whose `requires` exceed its
`capabilities`. Refusal names the missing feature.

**`IoPolicy`** starts at the honest minimum and widens only when a launcher can
deliver more: stdout and stderr to files under the jail directory (the
filenames are configurable, the content mode is not), stdin from `/dev/null`
(fixed). Pipes and ring buffers arrive with a pty launcher, if one is ever
written — until such a launcher exists, a wider `IoPolicy` would be a
capability claim with nothing behind it, which law 2 forbids. (Folded from the built shape by decision-044,
discharging decision-038's A8.)

**`create` holds no process, and every process is a `start` (2026-10-12,
decision-181).** decision-178 left `Runtime.create` launch-shaped, because a
bwrap jail cannot hold an instance with nothing in it until its supervisor
(decision-0001 step 4). A `HOST` jail can: its instance is what `create`
makes before the first spawn. So:

- `Runtime.create(jail, *, cwd, jail_id, jail_dir, tether) -> JailRecord`
  takes no argv and no `IoPolicy`. `HostRuntime.create` checks capabilities
  (`LaunchRefused`, unchanged), makes `jail_dir`, clears what an earlier jail
  there left (§9's records ruling: refused while any of it runs), writes the
  staged files, runs `LAUNCH_SCOPED` helpers to completion and starts
  `JAIL_LIFETIME` ones, and derives `wrap_prefix` once, from the compiled
  `wrap` applied to a fixed sentinel argv, verified as a pure prefix as today
  (`None`: every `start` refuses). A start in the process that created the
  jail, which still holds the compiled `wrap`, also checks that `wrap` of its
  own argv is that prefix followed by the argv, and refuses on a mismatch
  (`ExecWrapNotAPrefix`); a rehydrated jail has only the prefix, as an exec
  has today. It spawns no workload. `JailRecord.first` goes.
- `Supervisor.start(argv, *, cwd, io) -> ProcessRecord` is the only way a
  process enters a jail, the first included. Each start spawns
  `(*wrap_prefix, *argv)` under **its own exit wrapper** (decision-156's
  program, unchanged but for where it writes, §9), detached in a new process
  group, stdio per `io` under the process's own records directory, env
  `{**os.environ, **jail_env}`. So `Process.pid` names the wrapper for every
  process, as it named it for the first one before, and an exec sibling
  gains what only the first process had: an exact exit status readable from
  another process. Fidelity is unchanged: `EQUIVALENT_PROFILE` for a
  non-empty prefix, `PLAIN` for an empty one, decided per jail, never per
  start.
- **Every start is tethered when the jail is.** The tether's read end is
  held by the jail in memory (never in a record: an fd does not serialize),
  and each start's wrapper starts a watcher of its own on it, in that
  process's group, before the workload, as decision-167's watcher does for
  the first process today. So no process of a tethered jail runs untethered,
  siblings included (decision-167's "exec siblings are groups of their own
  and are not tethered" is superseded). `JAIL_LIFETIME` helpers stay
  untethered, as decision-167 states; tethering them is decision-0001's
  ("Helpers with `JAIL_LIFETIME`"), not this step's.
- **Which process is the jail's "workload".** None is special to the
  runtime. A `KillReport` keeps its vocabulary: the first process started is
  reported as `workload_group` and every later one as `exec_sibling`, in
  start order, so a report for today's shapes reads as it does now.
- `Runtime.alive(jail)` is true while any recorded process's leader holds
  its identity (decision-155, zombies gone, decision-171) or any
  `JAIL_LIFETIME` helper does; a jail created with nothing started and no
  helper reads gone.

`SubprocessLauncher` stays, as `create` plus a first `start` returning a
`Handle`, until TASK-0079.28 deletes it. Implementing task: TASK-0079.25.
(Ruled 2026-10-12, decision-181.) *(It is deleted: decision-183, §3.)*

**A supervised jail: `create` starts the supervisor, and every process after
it is a request (2026-10-15, decision-191).** decision-0001's migration step 4a,
the runtime's half; §6 (decision-190) is the mechanism's and §9 (decision-192)
the embedder's. When the compiled jail declares a supervisor, `HostRuntime.create`
does what it did, then starts one process, brig's supervisor, under the whole
composed wrap, and returns once it has said it is ready. Ruled:

- **How it starts.** `(*wrap_prefix, interpreter, "-I", "/.brig-supervisor.py",
  <fd>)` under the same exit wrapper as any start, detached in a process group of
  its own, tethered when the jail is (decision-167), its stdout and stderr files in
  `<jail_dir>/supervisor/`, host-opened and sealed from the jail as the rest of the
  jail directory is (decision-173). Its stdin is its own source (§6), and `<fd>` is
  its end of a `SOCK_SEQPACKET` socketpair the host made first: the exit wrapper
  gained an argument naming descriptors it and its child keep (`subprocess` closes
  every other), and nothing else holds that end. The supervisor makes it
  close-on-exec and each process it starts closes every descriptor above 2 before its
  exec, so the socket is passed to nothing the supervisor starts. A wrap that is not a
  pure prefix refuses the create (`ExecWrapNotAPrefix`), as it refused every start.
  The group the exit wrapper leads is **the instance**: `SupervisorRecord`, its pid
  and start stamp, is what `destroy` and `alive` identify it by (decision-155), and
  ending it ends the namespace.
- **The program (`brig/run/_supervisor_program.py`) is the standard library and
  nothing else**, in the syntax of the oldest Python it supports, kept as text for
  that reason. It imports every module it needs, `array` (which `socket.send_fds`
  imports late on newer Pythons) and `warnings` (which `os.execvpe` imports late, found
  by running the bwrap tiers in `scripts/linux-jail-check`'s Ubuntu container, where
  starting `bash` by name was refused) included, **before it says it is ready, and
  then refuses every import** with a finder first on `sys.meta_path`: "every import done
  before any process starts" is a promise that fails loudly where it is broken. A
  rehearsal first does each kind of thing it will ever do once (a search of the path
  for a program, a socket pass, a start, a wait, a signal, a stop), so whatever an
  interpreter loads late for them is loaded in the process every other is forked from
  and not in a child that is gone with it. It
  makes itself undumpable (`prctl(PR_SET_DUMPABLE, 0)`, refusing to start if it cannot),
  installs a handler for `SIGCHLD` and for no other signal (the handler does nothing;
  the wake-up descriptor does the work), checks it is PID 1, and fails closed: an
  exception it cannot handle ends it, and with it, by the kernel's rule for a pid
  namespace's init, everything in the jail.
- **The wire.** One JSON object per message, a request `{"id": n, "op": ...}` and
  its reply `{"id": n, "ok": ...}`, descriptors by `SCM_RIGHTS`, a message at most
  1 MiB; the supervisor sends `{"hello": 1, "protocol": 1, "python": ...}` once,
  when it is ready, and the host refuses another protocol. Five ops. `start` carries
  the process's id (brig's 16 hex, the same as its records directory), argv and
  cwd and three descriptors, stdin, stdout and stderr, which the host opened (so the
  jail needs no writable directory for `IoPolicy`); the supervisor forks, makes the
  child leader of a process group of its own (the parent does it too, so the group
  exists before the reply), holds it at a gate, and replies with its pid in the jail
  and a pidfd. `go` opens the gate: the child takes its three descriptors as 0, 1 and
  2, closes the rest, restores the signal dispositions CPython changed (`SIGPIPE`,
  `SIGXFSZ`) and execs with the environment the supervisor was started with, read
  from the kernel's copy (`/proc/self/environ`) so a variable CPython set on itself
  (`LC_CTYPE`) is not inherited by every process of the jail; the reply to `go` says the
  exec happened or why it did not, which is `WorkloadSpawnFailed`. `signal` is `killpg`
  of the process's group by its id, `wait` is an answer when the process has ended or a
  deadline in the request passes (several outstanding at once, none blocking another),
  `stop` is `SIGTERM`, a grace period, `SIGKILL`, a grace period, verified by the
  supervisor and again by the host. A process is always named by its id, never a
  number the jail could influence. Requests from several threads are in flight at once
  and a reply finds its caller by id (`brig/run/_supervisor_link.py`).
- **A request has a host-side deadline, and a missed one ends the jail.** A start's
  two requests and a signal have 30 s, a wait's chunk (at most 5 s, asked again for
  a longer one) 10 s more than itself, a stop twice its grace and 10 s: a supervisor that
  does not answer is spinning, wedged or hostile, and law 7 is that control does not
  wait on it. A miss ends the instance's group at once (`SIGKILL`, no `SIGTERM` first, and no
  grace for a workload that is starving the supervisor to act in: decision-193; the
  host's `SIGKILL` lands on a `SIGSTOP`ped init), closes the socket and raises
  `SupervisorUnresponsive` to the caller; a closed socket is `SupervisorGone`; a start
  that never says it is ready within 60 s, or whose socket closes first (a mount `bwrap`
  refused, an interpreter that is not there), ends the instance and raises
  `SupervisorFailed` carrying what the supervisor's stderr said.
- **End-of-file on the socket ends everything.** The supervisor reads it as the host
  being gone and exits at once; the kernel ends everything in its pid namespace with it,
  a `setsid()` child included. That is what the host's death does (the kernel closes its
  end, `SIGKILL` included), what `destroy` does just before the instance's ladder
  (below, §9), and what collecting a `Jail` nobody holds does: a supervised jail lives as
  long as the object holding its end, tether or none. The tether still runs, outside
  everything, for a supervisor that does not read it.
- **What a process of the jail could do to the supervisor, and why it can't.** It
  signals it: `SIGKILL`, `SIGSTOP` and every signal without a handler are dropped by
  the kernel for a namespace's init, and `SIGCHLD`'s handler only wakes it (observed:
  `kill -9`, `-STOP`, `-TERM`, `-INT`, `-USR1` all return 0 and the supervisor stays
  `S` and answers). It reads or changes it through `/proc`, `ptrace` or `pidfd_getfd`:
  undumpable, so `environ`, `mem`, `maps` and `fd/*` are `EACCES` and attach and
  `pidfd_getfd` `EPERM` for a caller without `CAP_SYS_PTRACE`, which `--cap-drop ALL`
  leaves none (observed; `cmdline` and `stat` stay readable and hold the control
  descriptor's number and the program's path, nothing else). It reaches the control
  socket: no process holds it, and a socket cannot be opened through `/proc`. It writes
  its program: read-only, from memory. It overruns the supervisor's input: the
  supervisor's input is the host's. What it can still do is starve it (a fork bomb, a
  full descriptor table, memory), which is a missed deadline, which ends the jail:
  failing closed, and `destroy` never needs the supervisor to answer.
- **Unchanged.** The tether (decision-167), the channel directory and the verified dial
  (decisions 184-186), `JAIL_LIFETIME` helpers, `LAUNCH_SCOPED` ones, the exit wrapper's
  own record of how the supervisor ended (`<jail_dir>/supervisor/exit`, read by nothing).

Implementing task: TASK-0079.06. (Ruled 2026-10-15, decision-191.)

**A supervised jail starts each process in namespaces of its own where the host
lets it (2026-10-16, decision-195).** decision-0001's migration step 4b, the
runtime's half; §6 (decision-194) is the mechanism's and §9 (decision-196) the
embedder's. Until now every process of a supervised jail stood in the jail's one
pid, mount, network and IPC namespace (decision-192): a child that left its group
with `setsid()` outlived `stop`, a process could see, signal and read a sibling,
and every socket in the channel directory, abstract socket and System V object was
every process's to reach (decision-184's residual). Ruled:

- **Found out before the supervisor says it is ready, by doing it.** After its
  rehearsal the supervisor does once what a start does: forks, leaves for new user,
  mount, pid, network and IPC namespaces, forks the PID 1 of the new pid namespace,
  makes its mounts private, mounts a fresh `/proc`, brings the loopback up and drops its
  capabilities, then ends it. The answer is in the hello,
  `{"namespaces": {"held": true|false, "reason": "..."}}` (`PROTOCOL` 2), and
  `JailRecord.namespaces` carries it in the process that created the jail. A host that
  restricts nested user namespaces fails some step, and `reason` is the failing call's own
  error: `bwrap --disable-userns` (the block the tests plant), a low
  `user.max_user_namespaces` and a seccomp filter each refuse `unshare` here (TASK-0079.01),
  and an AppArmor profile for unprivileged user namespaces, which could not be tried, would
  refuse the mounts after it. A
  jail run as uid 0 is not tried: bwrap covers its `/proc/irq` and `/proc/bus`, the kernel
  then refuses a fresh `/proc` to any namespace made inside it (§6, decision-194), and the
  reason says so. No start falls back later:
  a jail that held its namespaces at create starts every process in them or fails that
  start (law 2), and one that did not starts every process as decision-191 ruled,
  graded `cooperative` and saying why (decision-196).
- **What a start does when they are held.** The `start` request is as decision-191
  ruled, with `chan` (the jail's channel directory and the name of the socket this
  process will bind there, if it has one) and `scratch` (the jail's scratch directory,
  `<jail_dir>/tmp`, decision-173). The supervisor makes a directory of its own for
  the process in each that the jail can write (`<chan>/<name>`, `<chan>/<process id>`
  for a process with no socket, `<tmp>/<process id>`; mode 0700), then forks: the child
  leaves for the namespaces, forks the process, which is **PID 1 of its pid namespace**
  and leads a process group of its own in it (so the host reads, through the pidfd, the
  host pid, start time and group every record has), tells the supervisor which it is
  and ends. The user namespace maps the process's own uid and gid to themselves and
  denies `setgroups`, the one mapping an unprivileged process may write, so its files
  stay its own and `getuid()` is what it was. The gate and `go` are as before; after
  `go` and before the program's descriptors the process makes its mounts private,
  mounts a fresh `/proc` for its pid namespace, binds its directories over the channel
  directory and the scratch directory (each sees one directory it alone can write and
  no sibling's socket or file), brings the loopback up (bwrap does the jail's; a new
  network namespace's is down) and, after its descriptors and signal dispositions, drops
  every capability, bounding set included: it made a user namespace, so it holds all of
  them in it until it does. An unwritable channel or scratch directory holds no socket
  or file of anyone's and is left as it is, unless a socket was promised there, which
  fails the start. The directories are removed, if empty, when the process is gone.
- **What each namespace closes** (decision-0001's table, each probed from inside a real
  jail with a control in a jail without the bundle, `tests/e2e/test_process_namespaces.py`):
  pid, `/proc` and signals (a sibling's pid is not there and `kill` finds no such process);
  mount (the channel and scratch directories are the process's own); network (the loopback
  is the process's own, so an abstract Unix socket is too); IPC (a System V message queue a
  sibling made is not found; POSIX message queues are the same namespace's, not probed, as a
  jail mounts no `mqueue`); user (no capability, and `mount(2)` is `EPERM`).
- **A signal to the process is what it would be to any process.** The kernel drops a signal
  a process outside a pid namespace sends its PID 1 unless the PID 1 handles it (`SIGKILL`
  and `SIGSTOP` excepted), so a `SIGTERM` or `SIGINT` to a program that installed no
  handler would do nothing, and `stop` would wait out its grace. The supervisor reads the
  process's `SigCgt` and `SigIgn` from `/proc/<pid>/status` before it signals and sends
  `SIGKILL` for a signal that would have ended an ordinary process by default and that
  the process neither handles nor ignores; a handled or ignored one is sent as it is
  (a handler runs, an ignored `SIGTERM` waits out the grace), and `SIGCHLD`, `SIGCONT`,
  `SIGSTOP`, `SIGTSTP`, `SIGTTIN`, `SIGTTOU`, `SIGURG` and `SIGWINCH` always. The host's
  own ladder, which signals a leader outside its namespace too, does the same for
  `SIGTERM` (`teardown.term_rung`: `SIGTERM`, but `SIGKILL` for a leader whose `NSpid`
  ends in `1` after another number and that neither handles nor ignores it). What a caller
  sees of it is a status of `-9` where an ordinary process would have had `-15` (or `-2` for
  an interrupt), and that the process's children, handlers or none, end with it at once: a
  stop ends the namespace. A PID 1 can't be ended by a signal it sends itself, either (a
  shell's `kill -KILL $$` returns and goes on), the kernel's rule for a namespace's init.
- **The supervisor is out of its reach, and the orphans are its own.** A process of a
  jail with namespaces can't see the supervisor (`/proc` shows only its own pid
  namespace), signal it or reach its socket. A process it orphans is adopted by
  the PID 1 of its own pid namespace, which is the program itself: it reaps nothing it
  does not `wait` for, as in any container without an init, and a zombie it leaves is
  gone to every check brig makes (decision-171) and to the kernel when the namespace ends.
- **Measured here (TASK-0079.07).** A nested user, mount, pid, network and IPC bundle as
  an unprivileged user inside a jail with the cover of decision-194 removed: `/proc` is a
  fresh one, the loopback comes up, the capability sets are empty. As uid 0 with
  `--cap-drop ALL`, a nested user namespace can write no `uid_map` at all (mapping the
  parent's uid 0 needs `CAP_SETFCAP` in the parent: `verify_root_map`), and a fresh `/proc`
  is refused whatever the map.

Implementing task: TASK-0079.07. (Ruled 2026-10-16, decision-195.)

## 9. The Jail (the Handle until decision-183)

The shape since decision-183 (§3); "the handle" in the rulings below, which
are kept as written, is this `Jail`, and its `kill` is `destroy`, its `exec`
a `start`:

```python
class Jail:
    @classmethod
    def create(cls, jail: CompiledJail, *, runtime: Runtime, cwd: str,
               jail_id: str, jail_dir: str, tether: int | None = None) -> Jail
    def to_dict(self) -> dict: ...                   # everything teardown/observe needs
    @classmethod
    def from_dict(cls, d, *, runtimes: Mapping[RuntimeKind, Runtime]) -> Jail

    def start(self, argv, *, cwd: str | None = None, io: IoPolicy = IoPolicy(),
              channel: Reservation | None = None) -> Process  # absent without a supervisor
    def channel(self, name: str) -> Reservation         # decision-184, §10
    def processes(self) -> tuple[Process, ...]          # start order
    def alive(self) -> bool
    def destroy(self, *, grace: float = 2.0) -> KillReport
                                                       # tree/group teardown of EVERYTHING
                                                       # the jail names: every process's
                                                       # group in start order, then
                                                       # helpers, containers; grace=0 ends
                                                       # it at once (decision-193)
    @property
    def instance_group(self) -> int | None             # decision-193: the process group that
                                                       # holds a supervised jail's PID 1
    def probe(self, battery) -> ProbeReport            # §12; absent when start is
    # fields: report, spec, signatures, channels, compile_events, jail_id, jail_dir

class Process:
    def interrupt(self) -> bool         # SIGINT to its group; absent without a supervisor
    def stop(self) -> KillReport        # the ladder, its group alone; same
    def wait(self, timeout: float | None = None) -> int   # same
    def alive(self) -> bool
    def exit_events(self) -> tuple[Event, ...]  # §11
    def wait_ready(self, timeout: float) -> None    # decision-184, §10
    def connect(self) -> socket                     # decision-185, §10: the verified dial
    # fields: id, pid, start_time, argv, stdout_path, stderr_path, fidelity,
    #         channel, bound_path, endpoint (decision-184)
```

`console` (§11) stays absent; §10's `dial` for a reserved channel is
`Process.connect` (decision-185). The fields an embedder reads
rather than calls: `compile_events`, every mechanism sensor's
`known_at_compile()` payload stamped at `create` (§11); `report`, the
`EnforcementReport` the stack compiled; and each process's identity pair
`pid`/`start_time` (with the jail's `helper_pids`/`helper_stamps` in its
dict), which is what makes a recycled pid read as gone rather than as this
jail — see "A pid is not an identity" below.

**An unimplemented capability is absent from the surface, never a raising stub.**
The block above is the finished shape. A milestone that cannot yet honour one of
these methods ships a `Handle` *without* it — not one that declares it and
raises. A method that raises lies to `hasattr` and to every embedder that
feature-detects; it is law 1's silent downgrade wearing an API's clothes.
(Private delegates filled inside the same milestone are not this case: the
surface never named them.)

**`interrupt` ships (2026-09-08, decision-151).** It was absent under exactly
that law from M2 (ambiguity A10) until an embedder needed it: its sandbox
executor had to answer "stop that one action" and, with no interrupt, its only
honest options were killing the whole jail — every other action in flight with
it — or silently doing nothing. It is **`SIGINT` to the workload's process
group**, `os.killpg`, never a single pid, for the same reason teardown never
signals one. Three clauses, each of which is a constraint on the
implementation and not a description of it:

- **It returns deliverability, not death.** `True` is the kernel accepting the
  signal for delivery; `False` is the group not being there
  (`ProcessLookupError`) or not being this process's to signal
  (`PermissionError`), returned rather than raised so a caller has nothing to
  translate. `SIGINT` is catchable, blockable and ignorable, and a hostile
  workload is entitled to all three — which is why `interrupt` is the first
  rung and `kill` is the ladder, and why only `kill`'s report carries a
  *verified* outcome. A method that returned `True` meaning "it stopped" would
  be law 1's grading dishonesty relocated into control.
- **The grade is already promised, and is not re-promised here.** How well
  control can be delivered for a given jail is the `control` axis of the
  `EnforcementReport` the handle already carries (§4; law 7's "its
  deliverability is itself graded in the report"). `interrupt` reads no grade
  and publishes none: a per-call grade would be a second, unsynchronized
  answer to a question the report answers.
- **Same pid-reuse seam as teardown**, accepted by decision-144 on the same
  terms: the pgid was read at spawn, and the blast radius is a signal.

(Implementing task: this phase.)

*Amended 2026-10-11 (implementing task: TASK-0077).* **A zombie is gone.** A
process that has exited and awaits only its parent's `wait` (state `Z`, on Linux
and darwin alike) runs nothing, but it stays in the process table, and
`os.kill(pid, 0)` still succeeds on it. Where PID 1 does not reap (a container
without an init, Docker without `--init`), a killed jail's orphans stay zombies
for good, so a verification that counted them would read a dead jail as
surviving, and `kill()` would report `FAILED` for a jail that ended. Both
observations therefore skip zombies: the group-membership scan that verifies the
ladder's last rung (`/bin/ps -Ao pid=,pgid=,stat=`, rows whose state starts with
`Z` left out), and `alive()` (`identity_holds`, which reads the leader's state
from `/proc/<pid>/stat` on Linux and `/bin/ps -o stat=` elsewhere). An
unreadable state is not evidence of death: it reads as not a zombie.
(Ruled 2026-10-11, decision-171.)

*Amended 2026-10-11 (implementing task: TASK-0079.19).* **An embedder can ask
whether a group still runs.** `Handle.alive()` answered for the leader only
(since decision-181: for every process's leader and the jail's helpers), and
`os.killpg(pgid, 0)` counts a zombie as running, so an embedder that sweeps dead
jails never saw one end where PID 1 does not reap. brig
exports `brig.run.group_alive(pgid) -> bool`: the same scan teardown's
verification rung uses (`/bin/ps -Ao pid=,pgid=,stat=`, one function deciding
membership, so the two cannot drift). A group with at least one member not in
state `Z` reads alive; a group with no rows, or only `Z` rows, reads gone; when
the process table cannot be read (`/bin/ps` missing or failing) it reads alive,
so a sweep keeps what it cannot prove dead. The scan is injectable
(`read_table=`) so that failure is testable. (Ruled 2026-10-11, decision-176.)

*Amended 2026-10-11 after review (decision-176, TASK-0079.19).* "Cannot be
read" includes a row that does not parse. Any non-blank row of the scan that is
not exactly an integer pid, an integer pgid and a non-empty state (a header, a
missing or an extra column) makes the table unreadable, because skipping it
could read a live group as gone. `group_alive` reads that as alive; teardown's
verification rung lets it reach the per-item boundary, so the item is `FAILED`
(the group's end cannot be confirmed), never `ENDED`. Blank lines are skipped.

**`exec` — a sibling process inside the same confinement** (the
`docker exec -it` experience, for every stack). Semantics:

- The exec'd process is subject to the **same Spec** as the workload — never
  a weaker one. A mechanism that cannot guarantee this refuses exec.
- Fidelity is mechanism-shaped and reported honestly: `oci_container` and
  `bwrap` (via namespace entry) place the process inside the *same boundary
  instance*; `seatbelt` can only start a sibling under an *identical
  profile* — equivalent enforcement, different instance — and the
  `ExecHandle` says which. The empty stack execs a plain process, graded
  accordingly. *Amended 2026-10-15 (decision-192, TASK-0079.06):* bwrap does
  it by a request to the supervisor that is the jail's PID 1, not by entering
  a namespace: every process of a bwrap jail is `SAME_INSTANCE`.
- `interactive=True` wires the caller's tty to a pty on the exec'd process.
  That pty is shared media for as long as it lives (it appears in
  `shared_media` accounting), and
  interactive exec is the embedder's policy decision to offer — brig
  provides the mechanism, per law 4's boundary: this is a channel, not
  observation.
- **An exec sibling is the handle's to reap, and its registration must be
  durable.** The binding clause is **durability outside the live object**:
  `exec` records the sibling somewhere the handle can read back *in a later
  process*, never only as a field on a live `Handle`, so a rehydrated handle
  tears down execs it never itself started. *Which* durable record is an
  implementation choice, not a spec one — M2's was the event stream, an `EXEC`
  record with no matching `EXEC_END`; **decision-152 (2026-09-08) deleted that
  stream and the registration became a file per live sibling** under
  `<jail_dir>/execs/`, written before `exec` returns and removed by the first
  `wait()` that observes an exit status. Both are strictly more capable than a
  `to_dict` key, because both also reap a sibling started *after* the handle
  was serialized; the file-per-member shape additionally makes the live set a
  directory listing rather than a replay of every record ever appended. `kill`
  then ends those groups on
  the same ladder, after the workload group, and reports each as its own
  `KillReport` item. An exec the handle created and does not reap is a process
  from the tree surviving `kill` — the failure class this section exists to
  close. (decision-042: §9's teardown enumeration is illustrative, not
  exhaustive. decision-049: the clause is durability, not a named field, and the
  event-stream mechanism is compliant with it.)
  *Amended 2026-10-12 (decision-181, TASK-0079.25):* the record is now a
  directory per process, `<jail_dir>/procs/<id>/` (the first process's too),
  written before `exec` returns and **never removed by `wait()`**: a record
  outlives its process's wait, so `kill` still ends what a waited sibling left
  in its group, and reports an empty one `ALREADY_GONE`. Nothing writes or
  reads `execs/` any more.
- Probes (§12) run *through* `exec`, which is what makes them exercise the
  real path — probe and exec are the same machinery, one canned and judged,
  one free-form.

Fidelity is a named value, not prose: `ExecFidelity` is `SAME_INSTANCE`,
`EQUIVALENT_PROFILE`, or `PLAIN`, and the `ExecHandle` carries it. **A stack
with no mechanisms grades `PLAIN`** — the empty stack's exec is a plain sibling
process and the fidelity says exactly that rather than leaving it unstated.

**Which input routes to which outcome, stated so the vocabulary above has a
trigger.** The routing is on the compiled stack's `wrap` expressed as an argv
*prefix* — the only form that can be reproduced on a sibling's own argv without
weakening it — and there are exactly three cases:

- **No prefix exists** (the wrap is not a pure argv prefix): `exec`
  **refuses**, and refuses **before any file is opened**, so a refused exec
  leaves no stdout/stderr artifacts in the jail dir. This is the concrete
  trigger for this section's own sentence, "A mechanism that cannot guarantee
  this refuses exec".
- **The prefix is empty** (the empty stack, or an identity wrap): the sibling
  is spawned bare and grades **`PLAIN`**, as the paragraph above requires.
- **The prefix is non-empty**: it is reproduced on the sibling's argv under the
  launcher's own env composition, and the fidelity is **`EQUIVALENT_PROFILE`** —
  identical enforcement, a different boundary instance, which is what a
  seatbelt stack can honestly offer.

`interactive=True` refuses earlier still, on the missing `PTY` launch feature;
the three cases above are what remains once that refusal has not fired. This
text describes behaviour `task-046` already shipped and the integration tier
already pins — **implementing task: none, no code change** (decision-096's
legitimate outcome). Written from the built shape rather than from the design,
on decision-069's discipline. (Ruled 2026-08-24, decision-120, discharging
`doc-016` §8.2 ask 6.)

**A pid is not an identity, and every decision here now compares two facts
(2026-09-08, decision-155).** This section used to carry the gap as prose:
sibling liveness was "matched by pid", `alive()` admitted it could read `True`
against "an unrelated process that now happens to hold that number", and
decision-144 accepted the same window for teardown on the grounds that the
blast radius was a signal and no atomic alternative existed at this layer.
decision-144's own second condition for ending that acceptance was **holding a
pid across a durable boundary** — which is exactly what a serialized `Handle`
in an embedder's log does, and what §9 exists to make possible. So the pid is
no longer the whole record.

**What is recorded.** At launch, beside every pid this library writes down —
the workload leader, each `JAIL_LIFETIME` helper, each exec sibling's
registration — brig reads *when that process started* and records it with the
number: `/proc/<pid>/stat`'s `starttime` on Linux, `ps -o lstart=` elsewhere.
The pair is an identity in a way the number alone is not, because the kernel
never rewinds a running process's start time. `Handle` carries `start_time`
and `helper_stamps` (`HANDLE_VERSION` 5), and `<jail_dir>/execs/` carries one
per sibling, so a handle rehydrated in a later process compares the same two
facts the launching one would have.

**What every decision site does with it.** `alive()` reads a recycled pid as
**gone**. `interrupt()` returns `False` — not delivered, because what this
handle names is gone — instead of sending a `SIGINT` into a group led by a
stranger. Teardown's ladder does not run at all for such an item: it reports
`ALREADY_GONE` with a detail naming the mismatch, and signals nothing.
Deliberately narrower than "not alive": a leader that has exited and been
reaped leaves a pid naming *nothing*, while its process group can still hold
live children — the single-pid failure class this section exists to close — so
only a pid whose current occupant is provably someone else stops the ladder.

**The residual, stated rather than left silent.** The `ps` reading has
one-second resolution, so two processes holding the same pid within the same
second are indistinguishable; no system this library targets recycles a pid
that fast, but the claim is *narrowed by orders of magnitude*, not eliminated.
And a launch that could not take the reading at all — the workload had already
exited, microseconds in — records the stamp as unknown and degrades to exactly
the pid-only behaviour that preceded this, which is no worse than before and
says so at every call site. (Teardown no longer degrades: decision-172, below.)
A pidfd (Linux) would close both; it is a future
mechanism decision, not an assumption this section makes. (decision-051,
superseded here; decision-144's acceptance ends by its own terms.)

*Amended 2026-10-11 (implementing task: TASK-0078).* **A record brig cannot
verify is not kill authority.** An exec registration is a file under
`<jail_dir>/execs/`, and a `jail_dir` writable from inside the jail is an
arrangement this specification allows (the channel directory paragraph of §6
calls a jail directory holding the workspace the ordinary one). A registration
with an unknown stamp names a pid and a pgid and nothing that shows either is
this jail's: `recycled()` has no stamp to compare, so it reads "not recycled",
and the ladder used to run against whatever group the record named. A forged
one could aim `SIGTERM` and `SIGKILL` at any group the trusted process may
signal. So teardown's ladder now asks the record before it asks the group: an
item whose stamp is unknown is **never signalled, and never reaped** (its pid
may be some other child of the trusted process, whose exit status is not
teardown's to take). It reports `ALREADY_GONE` when a fresh group scan finds no
live member, and otherwise `FAILED`, with a detail saying no start time was
recorded and nothing was signalled: something may still run that teardown would
not touch, and the report says so rather than reading as ended. This holds for
every item alike (the workload group, an exec sibling, a helper), so a workload
whose leader exited before its stamp could be read, leaving children in its
group, is now reported `FAILED` rather than ended by a signal brig could not
justify. `alive()` and `interrupt()` keep decision-155's degraded pid check.
What this does not close: a record whose stamp is present but whose pid names
nothing still lets the ladder signal its pgid (the reaped-leader case above
needs that), so a jail that can write its `jail_dir` can still forge one; that
is a question of where records live, not of how they are read. (Ruled
2026-10-11, decision-172.) (A write root at or above the `jail_dir` no longer
makes it writable: decision-173, §5. Nor does a channel endpoint placed
directly in it, on bwrap: that layout is refused, decision-174, §5.)

*Amended 2026-10-11 (implementing task: TASK-0079.14).* **Teardown is total: a
registration brig cannot read is an item, not a stop.** `kill_jail` used to read
the registration directory with a function that raised on a file it could not
parse, so one such file ended the call after the workload group and left every
exec sibling and every helper running. No jail can write its `jail_dir` any more
(decision-173, decision-174), so a registration is the launcher's own and the
unreadable one is what tampering on the host or a broken disk leaves; teardown
still must not stop on it. A registration file that is not valid UTF-8 JSON, is
not an object, lacks `pid`, `pgid` or `start_time`, or holds the wrong type for
one, becomes its own `exec_sibling` item: `FAILED`, its identity the file's
path, its detail naming the file and what was wrong with it, saying nothing it
names was signalled, and telling the reader to inspect it (and end any process
of the jail it names, by hand). Nothing a file like that names is ever
signalled. Every other sibling, the workload group and the helpers are torn down
as before, and the unreadable items follow the readable ones in the report. A
file that vanishes between the listing and the read was deregistered meanwhile
and is skipped. Registrations are written whole and renamed into place, so a
crash mid-write leaves a `.partial` file teardown never lists, not a truncated
registration; only tampering or a disk fault yields an unreadable one. The
residual decision-172 states (a stamp present, a pid naming nothing) is closed
by where records live now: such a registration is genuine, its leader reaped,
and teardown ends its group. (Ruled 2026-10-11, decision-175.)

*Amended 2026-10-11 after review (decision-175, TASK-0079.14).* The paragraph
above promised more than it did: "torn down as before" held for an unparseable
file but not for a well-formed one that lied. Now (1) a pid or pgid outside the
range a process id can hold (2 up to 2**31 - 1) makes the file unreadable, so
`0`, `1`, negative and huge ids never reach a signal call; (2) teardown never
signals the trusted process's own group or a pgid of 0 or 1, for any item
(workload, sibling, helper): such an item is `FAILED` with a detail saying
nothing was signalled; and (3) each item's ladder runs inside one boundary that
turns an unexpected `Exception` (a `ps` that failed, a pid the OS rejects) into
that item's `FAILED` outcome, its detail naming the exception and what to do, so
`kill_jail` raises nothing from an item and one item never stops the next.

The handle is the fix for two documented failure classes in prior art: kill
paths that lose a container's identity when a relay pid dies (identity lives
in the serialized handle, not in a live process's argv), and single-pid
SIGKILL that leaves the interesting child alive (teardown is group-shaped:
`killpg`, then named helpers, then mechanism-specific remains, reported
per-item in `KillReport`).

**The serialized handle does not carry the launching process's environment
(2026-09-08, decision-152).** It used to: `env` was the workload's actual
environment as spawned, which for the `subprocess` launcher is the launcher's
own `os.environ` overlaid with the jail's. That made `to_dict()` a copy of the
operator's environment, API tokens included, and it defeated the whole point of
a serializable handle — an embedder that wanted to persist one had to invent a
private, mode-restricted side file to keep it out of its own log, which is one
more artifact whose existence, location and lifetime nothing else in the system
knows about. The field is deleted. `jail_env` — the compiled jail's OWN
overlay, which is mechanism-declared policy rather than ambient state — stays,
and `exec` composes `{**os.environ, **jail_env}` fresh at exec time in every
fidelity case, which is what it already did whenever the wrap prefix was
non-empty. **A serialized handle is now plain enough to live in the embedder's
own log**, which is where handle persistence belongs: the log is already the
durable record of the embedder's work, and a handle in it is a handle a later process
can rehydrate and kill with nothing else. (Implementing task: this phase.)

**The exit status is readable again, and it is not a log (2026-09-08,
decision-156).** decision-152 deleted the per-jail event stream and §11 named
the one capability that genuinely went with it: an exit status readable by a
process that never parented the workload. `wait()` answered in the launching
process and raised `ExitStatusUnobservable` everywhere else — so a rehydrated
handle, the shape an embedder uses to clean up after a runtime that died
holding a jail, could tear that jail down but never say how it ended. That is
given back here, without the stream: **the launcher runs the workload under a
tiny wrapper that writes the status to `<jail_dir>/exit`, once, atomically**
(since decision-181 every process, siblings included, runs under one of its own,
writing `<jail_dir>/procs/<id>/exit`)
(written to a temporary name and renamed, so a reader sees a complete status
or no file). One line, one write, no appender, no tail, nothing to rotate —
the objections that killed the stream do not apply to a file whose entire
content is how one process ended.

Three constraints, each a limit on the implementation rather than a
description of it:

- **The status is exact, which is why the wrapper is a program and not a
  shell.** It is the workload's parent, so it distinguishes "exited 143" from
  "killed by `SIGTERM`" (`143` versus `-15`) the way `$?` cannot, and it then
  ends the same way its child did, so the number on disk and the number the
  launching process observes are the same number by construction rather than
  by agreement.
- **The wrapper prepends nothing and enforces nothing.** It is outside the
  jail's own `wrap` — trusted-side plumbing, the same shape as a
  `JAIL_LIFETIME` helper — so what runs inside the confinement is byte for
  byte what ran before, `Handle.argv` still reports the jail's compiled argv,
  and `exec` still reproduces `wrap_prefix` and nothing else. `Handle.pid`
  names the wrapper, with the jail's own process its child in the same group;
  teardown is group-shaped at every rung, so no kill path depends on which of
  the two the number names.
- **`SIGKILL` still writes nothing, and `ExitStatusUnobservable` still means
  what it says.** A signal no process can catch leaves no status behind, and
  the killer holds the `KillReport`, which is that ending's record. What the
  exception no longer means is "you are not the launching process". Its
  remaining cases are exactly: the group was `SIGKILL`ed, the jail directory
  has been swept, or no wrapper ever ran. In none of them does a status exist
  to be read. (Implementing task: this phase.)

**The ladder is fixed, and its last rung is verification**: `SIGTERM` to the
group, a grace period, `SIGKILL` to the group, then *verify* the survivors are
actually gone — and only then report, per item. The verification rung is not
optional. A `KillReport` that records something as ended because a signal was
*sent* is law 1's grading dishonesty relocated into teardown, and law 7 makes
deliverability itself a graded claim rather than an assumption. The grace period
is `destroy`'s keyword, `grace` (default 2.0 s); `grace=0` skips the first two
rungs and sends `SIGKILL` at once, for a caller that must not give a workload a
period in which to act (decision-193).

**The ladder runs per item, and there is only one ladder.** Every group the
handle names — the workload group first, then each exec sibling, then helpers,
then containers as those arrive — is torn down by the same four rungs and
earns its own item. A second, weaker path for some other kind of thing the
handle owns would be exactly the silent downgrade law 1 forbids, relocated
into teardown.

**`KillReport`** is `KillReport(items)` over
`KillItem(kind, identity, outcome, detail)`, with
`KillOutcome ∈ {ENDED, ALREADY_GONE, FAILED}` — `ENDED` reserved for the case
where the *verification* rung observed the group empty, never for a signal that
was merely deliverable. `kind` names what was torn down: `"workload_group"` and
`"exec_sibling"` and `"helper"` are the three kinds a jail can produce today;
`"container"` joins them as that mechanism arrives (`"pane"` went with the
`tmux` launcher, decision-154). `identity` is the thing's own name in whatever
namespace it lives in (a pgid, as text, for both group kinds). **The report IS
the record** (2026-09-08, decision-152): teardown used to append one `KILL`
event per item after the fact, and that copy was strictly poorer than the
report it was copied from, so it went with the stream. An embedder that wants
teardown in its log writes what `kill` returns. (Folded from the built shape by
decision-044, discharging decision-038's A11, with the second kind admitted by
decision-042 and the third by decision-132.)

**Helper lifetime is watched by pid, not by pipe-EOF.** §6 permits either and
requires the choice be made once and written down; decision-132 makes it pid.
The reason is serialization: a `JAIL_LIFETIME` helper's pid rides on the
`Handle` (`helper_pids`, from `HANDLE_VERSION` 3), so a handle rehydrated in a
process that never started the helper can still kill it — a capability an
inherited pipe fd cannot cross a process boundary to provide, and one §9's
"kill leaves nothing" needs, since a surviving egress proxy is a listening
socket nobody owns. `LAUNCH_SCOPED` helpers run to completion *before* the
workload is spawned, and a non-zero exit refuses the launch rather than
starting a workload behind a preparation step that failed. (Ruled 2026-08-29,
decision-132.)

### The Jail and its processes (2026-10-12, decision-181)

decision-0001's migration step 3a; §3 has the order `Handle` is retired in,
§8 the runtime's half. Once TASK-0079.28 lands, this is the section's shape:

```python
class Jail:
    @classmethod
    def create(cls, jail: CompiledJail, *, runtime: Runtime, cwd: str,
               jail_id: str, jail_dir: str, tether: int | None = None) -> Jail
    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d, *, runtimes: Mapping[RuntimeKind, Runtime]) -> Jail

    def start(self, argv, *, cwd: str | None = None,
              io: IoPolicy = IoPolicy()) -> Process  # absent without a supervisor
    def processes(self) -> tuple[Process, ...]          # start order
    def alive(self) -> bool
    def destroy(self) -> KillReport                    # every process, then helpers
    def wait_ready(self, channel: str, timeout: float) -> None
    def probe(self, battery) -> ProbeReport            # absent when start is
    # fields: report, spec, signatures, channels, compile_events, jail_id, jail_dir

class Process:
    def interrupt(self) -> bool         # SIGINT to its group; absent without a supervisor
    def stop(self) -> KillReport        # the ladder, its group alone; same
    def wait(self, timeout: float | None = None) -> int   # same
    def alive(self) -> bool
    def exit_events(self) -> tuple[Event, ...]
    # fields: id, pid, start_time, argv, stdout_path, stderr_path, fidelity
```

`Handle.kill` is `Jail.destroy`; `Handle.exec` is `Jail.start` (`interactive`
goes: it could only refuse, for want of `PTY`, and a parameter only one value
of which works is a raising stub, so it returns with a runtime that has
`PTY`); `stat` and `JailStat` go (`alive`, `processes()` and `report` answer
them); `dial` and `console` stay absent. `ExecFidelity` keeps its three
values on `Process.fidelity`; a process-scope control grade beside it is
TASK-0079.08's. A start's channel is decision-184's (§10, TASK-0079.05).

**Each process has a record and an exit record of its own.** A start makes
`<jail_dir>/procs/<id>/`, `<id>` a fresh token per start (never a pid, never
reused), before it spawns, and the process's stdio files go there. Once the
spawn returns, the host writes `record.json` beside them (id, start order,
pid, pgid, start stamp, argv, stdio paths), whole, to a temporary name
renamed into place, as registrations are written now. The process's own exit
wrapper writes `exit` there (decision-156, unchanged but for the path). This
replaces `<jail_dir>/execs/` and `<jail_dir>/exit`, and settles decision-162
for good: a status belongs to one process id and can't be read as another
process's. Between the directory and the record a process runs unrecorded for
the length of a spawn; in a tethered jail it is tethered from before its
workload starts, so an embedder that dies in that window takes it down.

- **A record outlives its process's `wait`.** Today the first `wait()` on a
  sibling deletes its registration, so a teardown after it skips the
  sibling's group, and anything the sibling left running in that group
  escapes `kill`. Now `wait` deletes nothing: `destroy` runs the ladder for
  every record, and one whose group is empty reports `ALREADY_GONE`. A report
  after a waited sibling gains that item; nothing else in it changes.
- **`create` over a used `jail_dir`.** Records left by an earlier jail are
  removed by `create` only once nothing they name runs, and it decides that
  per record as teardown does, the stamp before the group: a record whose
  leader holds its identity (decision-155) runs; one whose leader's pid now
  names another process (recycled, or a planted record naming a stranger) no
  longer holds that group, whatever `group_alive` says of its pgid; one whose
  leader is gone runs while its group has a live member (`group_alive`, the
  reaped-leader case). A recycled leader means an empty group: the kernel
  hands out a pid again only once no process group of that number has a
  member, and a leader's pid is its group's pgid. So a recycled pgid can't
  hold the directory forever, and a live jail's records are never removed. **On any doubt it refuses and
  removes nothing**: a record that can't be read, has an unknown stamp
  (decision-172), or names an id out of range, a process table that can't be
  read, or anything under `procs/` that is not a directory brig made (a link,
  a file). While anything runs or is in doubt, `create` refuses, naming the
  directory and what holds it, and saying to destroy that jail or choose
  another directory. The removal follows no links: it opens each entry
  beneath `procs/` without following a symlink (`O_NOFOLLOW`, directory file
  descriptors), because on a stack without an `fs_write` mechanism the jail
  could write that directory. Removing a gone jail's records gives up
  authority over nothing.
- **Teardown keeps every guard.** The ladder (§9 above) runs per record in
  start order, then per helper, with decision-155 (a recycled pid is gone,
  nothing signalled), decision-171 (a zombie is gone), decision-172 (an
  unknown stamp is never signalled or reaped) and decision-175 (a record that
  can't be read, or names an id out of range, is its own `FAILED` item, its
  identity the file's path; the trusted process's own group, 0 and 1 are
  never signalled; no item stops the next) unchanged.

**Records are kill authority, so no grant reaches them.** The jail never
writes a record: the host writes `record.json`, and the exit wrapper is a
host-side program outside the jail's `wrap`. Where they live is the other
half. bwrap and seatbelt seal the `jail_dir` against every write root
(decision-173) and grant inside it only `<jail_dir>/tmp` and a LISTEN
channel's own grant; bwrap refuses an endpoint directly in the `jail_dir`
(decision-174). That left a gap, planted on 2026-10-12 (TASK-0079.04's
notes): an endpoint at `<jail_dir>/execs/k.sock` compiles under
`strict_linux()` and binds `<jail_dir>/execs` read-write into the jail, the
directory teardown signals by. So **every mechanism that compiles a LISTEN
channel refuses an endpoint at or under brig's records** (`<jail_dir>/procs`;
`<jail_dir>/execs` too until decision-183 deleted it), testing the lexical
and the resolved parent as TASK-0079.17 does, with a `ValueError` naming the
endpoint and the records directory and saying to put the endpoint in a
subdirectory of its own (`<jail_dir>/chan/`) or outside the `jail_dir`.
seatbelt refuses it too: its grant is the socket's literal path, but a socket
created at a record's path is a record the host can't read. The scratch name
`tmp` never holds a record. Grades are unchanged (a refusal grades nothing).

**A stack with no `fs_write` mechanism seals nothing**, and the ruling does
not refuse it: the empty stack, `env_scrub` or `rlimits` alone grade
`fs_write` `unenforced`, and their workload runs with the embedder's own uid
and no namespace, so it can already signal every group a forged record could
name. A forged record gives it nothing it lacks; every guard above still
holds (an unknown stamp is never signalled, a recycled pid never, the
embedder's own group never).

**A jail is rehydrated with the embedder's runtimes.** `to_dict` carries what
`Handle.to_dict` carries but the first process's fields, plus `runtime` (the
`RuntimeKind` that made it), `tethered`, and `processes`, the records known
when it was called; `HANDLE_VERSION` is 6, and an older dict is refused, as
every bump before. `Jail.from_dict(d, runtimes=...)` takes the runtimes from
the embedder, never from the dict: a dict naming a kind the embedder did not
pass, or one whose runtime's own `kind` differs, is refused (law 2), naming
the kind and saying what to pass. The dict is the authority for the processes
it names; a record on disk for one of them that disagrees is not used.
`destroy` still runs the ladder for the identity the dict names, under the
same stamp guards (a recycled pid is gone and nothing is signalled,
decision-155; an unknown stamp is never signalled, decision-172), so the
process the dict names is ended, as teardown-total requires (decision-175);
only the disk copy becomes its own `FAILED` item, its identity the file's
path, signalling nothing it names. A
record on disk the dict does not name is a later start and is read like any
other. A rehydrated jail reads each process's exit record, so `wait` answers
for every process, siblings included.

**`start` is absent, not raising, when a jail cannot start.** That is when
its runtime has no supervisor (`Runtime.supervisor` returns `None`), and when
it was created tethered in another process: the tether's fd did not cross
`to_dict`, and a start there would run untethered. `hasattr(jail, "start")`
is false then, and `probe` goes with it. `Process.interrupt`, `stop` and
`wait` are absent on a process of a jail with no supervisor; `destroy` is
always there.

**Probes run as processes.** `jail.probe(battery)` is `battery.run(jail)`:
each probe is a `jail.start`, waited with its deadline and read from its own
stdio files, and its record stays for `destroy` like any process's. §12's
"through `exec`" reads "through `start`".

**The fake runtime has a kind of its own.** `FakeRuntime.kind` was `HOST`, so
once records are sent to runtimes by kind a fake's record would reach
`HostRuntime`. `RuntimeKind.FAKE` is added to `core`, with static grades
`unenforced` on both runtime axes and a detail saying it is a test double; no
mechanism names it, so no compiled jail has it. `Jail.create` accepts a
runtime whose kind is the compiled jail's, or `FAKE` standing in for any
(the report keeps the compiled kind's grades); the jail's record says `FAKE`,
so `from_dict` sends it only to the runtime passed under `FAKE`, and a fake
record rehydrated with only `HostRuntime` passed is refused. The kind is
TASK-0079.25's; the refusal, and its test, are TASK-0079.26's, since
`from_dict(runtimes=)` arrives there.

**Settled by TASK-0079.25 (2026-10-12, no new ruling).** Seven points the
review left to the implementation, and three edges it found:

1. **The sentinel.** `create` derives `wrap_prefix` from `wrap` applied to two
   tokens that each hold a NUL (`"\0brig-wrap-sentinel-argv0"`, `"…argv1"`).
   No argv `execve` takes can hold a NUL, so it never equals an argv a start is
   asked for; a wrap that rewrites either token (or appends, or drops) derives
   no prefix and every start refuses; in the creating process each start also
   checks `wrap` of its own argv.
2. **A start on a tether that has ended is refused** (`TetherClosed`), before
   anything is made: a process started then would be killed at once by its own
   watcher. A tether that ends after the check is the watcher's to act on. A tether
   has ended when **every** write end is closed, so one the embedder's close has not
   ended yet is still open while a child that another thread of the embedder forked
   has not exec'd (it holds a copy of every descriptor until then): measured under
   load, the hangup came 1.5 to 2.4 ms after the close, and a start made in that window
   is not refused (it goes ahead and its watcher, or the supervised jail's own, ends it
   when the copy goes: `SupervisorGone` for a start under way). The check reads the
   pipe's state with no wait and promises no more (TASK-0079.06, 2026-10-15; no
   change of behaviour).
3. **The jail's tether fd.** `create` duplicates the read end (not
   inheritable) and the creating process holds the duplicate in memory, so the
   embedder may close its own once `create` returns, as after `launch` before.
   Each start passes it to its own wrapper alone (`pass_fds`); the wrapper hands
   it to its watcher and closes its copy. The duplicate is closed when the
   last in-memory holder is collected, never by `destroy`.
4. **The id** is 16 lowercase hex characters (64 bits from `secrets`). Read
   back, only a name that is exactly that is an id, and a record's own `id`
   must equal its directory's name; anything else under `procs/` is an
   unreadable entry (teardown: a `FAILED` item; `create`: a doubt).
5. **A `record.json` that can't be written** after the spawn: the start ends
   the process's group through the ladder (every guard), removes its records
   directory once it is gone, and re-raises the error with a note saying so.
6. **What `create` removes** of an earlier jail: the whole `procs/` tree
   (records, exit records, stdio), all or nothing. The jail directory's
   top-level files (staged files, helper logs) are overwritten as before; the
   old layout's `exit` and `execs/` are read by nothing and left alone.
7. **bh-02's runner tests** assert no `KillReport` item beyond "every item
   ended or already gone", and the runner never starts a sibling, so a waited
   sibling's new `ALREADY_GONE` item changes none of them.

And: **a stdio name may not be a record's** (`IoPolicy` refuses a name that is
not one plain file name, is `record.json`, `exit` or their `.partial`, or
names both streams the same); **a start whose argv can't be spawned** ends its
wrapper's group (its watcher with it) and removes its records directory, so
nothing is left to hold the jail directory; and **a launch whose first start
fails** destroys what `create` started (its `JAIL_LIFETIME` helpers).

Implementing tasks: TASK-0079.25 for the records, `create` with no process,
the per-start wrapper and tether (§8), the refusal that keeps every grant off
the records, and the fake's own kind; TASK-0079.26 for `Jail` and
`Process`, `to_dict`/`from_dict` and `HANDLE_VERSION` 6 (the refusal of a fake
record with only `HostRuntime` passed among it), `start` absent, and
probes; TASK-0079.27 for bh-02's runner; TASK-0079.28 for retiring `Handle`
and this section's old shape. (Ruled 2026-10-12, decision-181.)

**Settled by TASK-0079.26 (2026-10-12, no new ruling).** What the ruling left
to the implementation of `Jail` and `Process` (`brig/run/jail.py`):

1. **Absent is an attribute that is not there.** `Jail.start` and
   `Jail.probe`, and `Process.interrupt`, `stop` and `wait`, are properties
   that raise `AttributeError` when the call is absent, so `hasattr` is false
   and `getattr(jail, "start", None)` is `None`, while a type checker still
   knows the call's signature where it is present. One class each, no
   subclass per case.
2. **The runtime answers for processes.** `Runtime` gains `processes(jail)`
   (the ones the record holds, then every other one the runtime finds, in
   start order; a disk copy of a held process is never used in its place) and
   `process_alive(jail, process)` (its leader holds its identity), which
   `Jail.processes()` and `Process.alive()` delegate to, as every other call
   does.
3. **What a jail holds in memory.** The processes its dict named, then every
   process it started itself, in start order: these are what it "knows", and
   `destroy` ends them by the identity it holds. A disk record **disagrees**
   when any field but `order` differs (`order` only sorts; a `Handle`, which
   carries no order, names its first process with 0).
4. **The dict.** `version` (6), `runtime`, `tethered`, `jail_id`, `jail_dir`,
   `cwd`, `jail_env`, `wrap_prefix`, `spec`, `report`, `signatures`,
   `channels`, `compile_events`, `helper_pids`, `helper_stamps` and
   `processes` (each a record's own fields, checked as a `record.json` is: an
   id brig makes, ids unique). `launcher_name` gives way to `runtime`: a jail
   has no launcher. `Handle`'s dict is unchanged in shape and is written as 6
   too, until TASK-0079.28 deletes it; nothing persists one across the bump
   (bh-02 never calls `Handle.from_dict`).
5. **`Jail.create` refuses a runtime of another kind** (`ValueError`, naming
   both kinds), unless it is `FAKE`, as the ruling says.
6. **A refused start changes nothing** (`ExecWrapNotAPrefix`, `TetherClosed`):
   the jail is the embedder's, to start again or destroy. The launcher, which
   creates and starts in one call and hands nobody a jail when the start is
   refused, destroys what `create` started, as TASK-0079.25 settled; a test
   now shows the helper ended.
7. **`Handle.probe` runs through `jail.start` too**: it builds the `Jail` its
   handle describes (its runtime, its first process known, its tether hold)
   and probes that, so every battery runs as processes until
   TASK-0079.28 deletes `Handle`.
8. **The dict alone can't say untethered** (review 1). `create` writes the
   jail's own record, `<jail_dir>/jail.json` (its id and whether it is
   tethered; sealed from the jail as the rest of the jail directory is,
   decision-173), and `Runtime.tethered` reads it. A rehydrated jail has
   `start` only when its dict and that record both say untethered: a record
   missing, unreadable, naming another jail or saying tethered means absent,
   so a hand-edited dict can't start a process untethered in a tethered jail.
   The residual: on a stack with no `fs_write` mechanism nothing seals the
   jail directory, so a workload that can also edit the dict could rewrite
   `jail.json` too, as it could every record there; that stack's `fs_write`
   grade already says so.
   A disagreeing disk copy's `FAILED` item takes the held process's kind.

Implementing task: TASK-0079.26.

**`wait` means gone, where it can (2026-10-12, decision-182).** The exit
wrapper writes its process's exit record just before it exits, so a `wait()`
that answered on the record let a `create` into the same `jail_dir` meet a
wrapper that still ran, and refuse (`JailDirInUse`, rightly by decision-181)
in about one run in ten. Ruled: in the process that started a process,
`wait()` answers only once its exit wrapper has exited and been reaped (that
process's own waiter record; the exit record is not read while the waiter owns
the reap), so the process's group has no running leader when it returns and
`create` into the same `jail_dir` right after never refuses on it. A
rehydrated handle's `wait()` (any process but the starter) cannot reap: it
guarantees only that the exit record exists, and the wrapper may still be
leaving for a moment. `create`'s refusal is not weakened for that window
(refuse while anything recorded runs, and on doubt); it now names each held
process's pid and group and says that a process already waited for elsewhere
is still leaving, to wait a moment and retry, or to destroy the jail.
Implementing task: TASK-0079.30. (Ruled 2026-10-12, decision-182.)

*Amended 2026-10-12 (decision-182, TASK-0079.30 review):* once the waiter has
reaped, an exit record that exists wins over the waiter's status, and the
waiter's is used only where there is none. The record is the workload's own
status ("recorded, not invented"); the waiter's is the wrapper's, which differs
when teardown kills the wrapper after it wrote. `wait()` returning means the
process's leader has left; a workload that left children in its group still
holds the jail directory, and `create` rightly refuses until they are gone.

**A supervised jail's processes and ending (2026-10-15, decision-192).**
decision-0001's migration step 4a, the embedder's half; §6 (decision-190) and §8
(decision-191) are the mechanism's and the runtime's. In a jail whose PID 1 is
brig's supervisor a `Process` is one of its processes, and the notes above
about a process's leader, its exit record and its group hold for a jail the host
starts. For a supervised one, ruled:

- **A process is recorded before it runs a byte, as the host sees it.** `start` is the
  two requests of §8. Between them the host turns the pidfd the supervisor sent into
  the process's pid in the host's pid namespace (`/proc/self/fdinfo`, the kernel's own
  translation between the two), reads when that process started, checks that it leads
  a process group of its own, and writes `record.json` (`pid`, `pgid` and `start_time`
  as every record has them; `argv` the workload's own, since the wrap is around the
  supervisor and not around it); a pid the host cannot name, or a start time it cannot
  read, refuses the start with the process still held at the gate, and the process is
  told not to run. So the record is written before the process exists to be anyone, and
  the window decision-181 named, a process running unrecorded for the length of a spawn,
  does not exist here. A failed exec removes the record's directory, as a failed spawn
  always did.
- **Identity checks are the host's own, unchanged.** `Process.pid` is the process itself,
  leading its own group, never the exit wrapper (there is none per process): `alive`, the
  verified dial (decision-185: the peer is the process's group, led by the process
  recorded, and in a pid namespace a co-tenant's group is refused), and a rehydrated
  jail's per-process teardown ask what they always asked. What the host does **to** a
  process is a request by its id (`interrupt` is a `signal` of `SIGINT`, `stop` a `stop`,
  `wait` a `wait`), because a number the jail could influence is not what the supervisor
  acts on. A `stop` is verified twice, by the supervisor inside and by the host's own
  scan of the process table, and `ENDED` is reported only when both agree. Its reach is
  the process's group, as before: a child that left it with `setsid()` is outside it, until
  each process has a pid namespace of its own (TASK-0079.07); `destroy` ends those.
  *Amended 2026-10-16 (decision-195, TASK-0079.07): where the host lets a process have
  namespaces of its own a `stop` ends its pid namespace, a `setsid()` child included.*
- **`fidelity` is `SAME_INSTANCE`.** *(Amended 2026-10-16, decision-196: when a process has
  namespaces of its own it is in the jail's confinement, not its pid, mount, network or IPC
  namespace.)* Every process of the jail is in the one mount, network
  and pid namespace the supervisor holds, observed from inside (`readlink /proc/self/ns/*`
  is one answer for all of them and another for any other jail), and what separates
  them is what each process's own group and the kernel's user-id rules do, nothing more.
  `ExecFidelity.SAME_INSTANCE`'s docstring said no mechanism could deliver it; this one
  does.
- **`destroy` runs the same ladder per process first, then the instance.** Each process's
  group is ended by the four rungs (a workload that handles `SIGTERM` still gets its
  grace), as it was; then the instance, `"supervisor"` in the `KillReport`'s closed
  vocabulary (§9's `KILL_ITEM_KINDS` gains it, beside `workload_group`, `exec_sibling`,
  `helper` and `container` to come), whose identity is the instance group's pgid:
  just before its ladder the link is closed, so the supervisor takes end-of-file and the
  jail ends at once (`SIGTERM` is dropped by a namespace's init, so the ladder alone would
  wait out its grace), and the ladder verifies and falls back to `SIGKILL`. A supervisor
  found running before and gone after is `ENDED`, never `ALREADY_GONE`: the verification
  rung observed it. A rehydrated jail, which has no link, is ended by the ladder alone,
  and waits out one grace period on the supervisor. That is the order of a plain
  `destroy()`; `destroy(grace=0)` reverses it (decision-193). `alive` is true while
  the instance group's leader holds its identity, a process in it or none.
- **The dict carries the instance** (`supervisor`, `null` or the pid and start stamp,
  `JAIL_VERSION` 9) **and a rehydrated jail has no supervisor**: its link is a socket, which
  can't cross `to_dict`, so `start` and `probe` are absent and `interrupt`, `stop` and
  `wait` are absent on its processes (§9's law: absent, never raising); it can be
  destroyed, and `alive` and the rest of what teardown needs answer from the dict.
- **A status is the supervisor's report, and lives in the process that asked.** A
  supervised process has no exit record on disk (its exit wrapper is the supervisor's, and
  there is none for it): `wait` is answered by the supervisor, and a status once learned
  is kept by the link and recorded as the exit events' source (`Process.exit_events`
  answers as for any process, a sensor's reading of the ending included), so it is answered
  after the jail is gone. A status the supervisor never reported before the jail ended is
  `ExitStatusUnobservable`, as a `SIGKILL`ed process's always was.
- **The environment is fixed when the jail is created.** decision-152's "composed fresh at
  each start" holds for a jail whose processes the host starts; a supervised jail's
  processes inherit the supervisor's, which is the creating process's environment through
  the composed wrap at `create`, scrubbed as the stack scrubs it (SCRUB and no allowed
  name: empty). `Jail.start` has no `env`, so nothing a caller could change per start
  is lost.

Implementing task: TASK-0079.06. (Ruled 2026-10-15, decision-192.)

**A teardown can end a jail at once, and a jail whose hold the host lifted is ended so
(2026-10-15, decision-193).** The closing review of TASK-0079.06 measured what
decision-192's order costs a caller who must not wait. bh-02's tripwire (the host
replaced or removed a path the jail holds with a mount, so the mount inside the jail is
gone) was armed with `destroy()`, which ladders each process first: `SIGTERM`, up to
2.0 s for a workload that ignores it, `SIGKILL`, and only then the instance. A workload
that ignored `SIGTERM` and wrote the absent secret every 10 ms planted it on the host in
3 of 3 runs, the jail ending after 2.01 to 2.06 s; the `killpg(SIGKILL)` it replaced
ended the jail in 0.01 s. A grace period is a window a hostile workload uses. Ruled:

- **`Jail.destroy(*, grace: float = 2.0)` and `Runtime.destroy(jail, *, grace)`.** §9's
  grace period was always a keyword; the surface now has it. `grace=0` skips the first
  two rungs: `SIGKILL` goes to the group at once and the verification rung follows (it
  still waits up to 2.0 s for the table to show the group empty: `SIGKILL` cannot be
  ignored, but the kernel needs a moment to remove what it killed). A negative `grace` is
  a `ValueError`. Nothing changes for a plain `destroy()`: a workload that handles
  `SIGTERM` still gets its grace. `Process.stop` is as it was.
- **At once, in a supervised jail, is the instance first.** The first signal is
  `SIGKILL` to the instance's group (its leader running, as for any group at `grace=0`),
  ahead of every process-table scan and every item: the supervisor, PID 1 of the jail's
  pid namespace, ends, and the kernel ends every process in the namespace with it, a
  `setsid()` child included, as fast as the `killpg` it replaces (the namespace's init is
  safe from a signal sent inside it; the host's is not). Then each item is verified in
  the report's usual order, the processes, then the instance, its link closed just
  before its item as it always was (a socket nobody reads by then), then the helpers. A
  process whose leader held its identity just before the signal and whose group is then
  found empty is `ENDED`, never `ALREADY_GONE`, which stays for what was gone before
  (the detail says it ended with the jail's pid namespace when its group was empty
  already by the time its own ladder looked).
- **At `grace=0` a group whose leader runs is signalled before anything else is read.**
  The pre-signal scan that reports `ALREADY_GONE` for an empty group is a `ps` run before
  the kill, which on a loaded machine is what the window is made of; the leader's
  identity is a `/proc` read. A group whose leader is not running is scanned first, as
  it always was, since a group of zombies is gone and a signal to it says it was there.
  `ENDED` is a group the verification observed empty after the signal reached it.
- **A missed deadline and a supervisor that never said it was ready end the instance at
  once too** (`grace=0`, decision-191): the host has already waited out the deadline.
- **`Jail.instance_group`: which process group holds the jail.** A supervised jail's PID 1
  and bwrap's own process are in one group, which lives exactly as long as the jail's pid
  and mount namespaces do: the first program ending, or a `setsid()` child outliving it,
  changes nothing. `None` for a jail with no supervisor, whose programs' own groups are
  all there is. It is the number `to_dict()["supervisor"]["pid"]` carries, and what an
  embedder that records "which jail holds this" for a later process to test with
  `group_alive` records (bh-02's runner, for the placeholders a jail holds): a program's
  own pid is not it, because a program may end while the jail goes on.

Implementing task: TASK-0079.06, reopened by its closing review. (Ruled 2026-10-15,
decision-193.)

**A process says whether it has namespaces, grades its control, and its socket
may be in a directory of its own (2026-10-16, decision-196).** decision-0001's
migration step 4b, the embedder's half; §6 (decision-194) and §8 (decision-195) are
the mechanism's and the runtime's. Ruled:

- **`Process.namespaces` and `Process.control`.** `namespaces` is whether the
  process was started as PID 1 of user, pid, mount, network and IPC namespaces of its
  own (decision-195). `control` is a `Graded` (§4) for what its `stop` delivers, the
  process scope decision-0001 puts on each `Process` and not in the report. In
  namespaces it is `cooperative`, its detail saying `stop` ends the process's pid
  namespace, a `setsid()` child included; without them, in a supervised jail,
  `cooperative`, its detail saying `stop` signals the process's group, which a child can
  leave with `setsid()` (only `destroy()` ends that), and **why the jail's processes have
  no namespaces** as the supervisor said it (a blocked nested user namespace, uid 0).
  A jail with no supervisor says its runtime gives a process none. `cooperative` is the
  ceiling for both until TASK-0079.08's battery plants survivors from the host and proves
  more (decision-0001, law 10); the two differ in `namespaces` and in the detail. The
  jail's `report` is the compile-time claim and is not changed: its `control` axis is the
  jail scope, `unenforced` as before.
- **The record carries it.** `ProcessRecord` and `record.json` gain `namespaces`
  (a bool, required: an older record reads unreadable, a doubt like any other), and the
  jail's dict carries the records, so `JAIL_VERSION` is 10. A rehydrated jail reads it from
  the records; the reason it was not held lives only in the process that created the jail.
- **A socket is in a directory of its own.** A process with a mount namespace sees the
  channel directory as one directory made for it, so the socket it binds at the reserved
  path `<chan>/<token>.sock` is at `<chan>/<token>/<token>.sock` on the host. For such a
  jail `Reservation.endpoint` differs from `bound_path` (`socket_endpoint`: the one
  directory in between, named for the token), `Runtime.endpoint` derives it from the
  record's `bound_path` and `namespaces`, and `reservation_refusal` expects it. The
  verified dial (decision-185) is unchanged: the kernel numbers a listener in a descendant
  pid namespace for the host that dials it, so its group and its leader's identity are the
  ones the record holds. Without namespaces nothing moves: the two paths are one.
- **The residual decision-184 named is closed where the namespaces are there.** A socket
  in the channel directory was reachable by every process of its jail; now a process sees
  only its own, and `connect` to a sibling's path finds no such file. It is a statement
  about brig's own channel directory; an embedder's own writable directory (bh-02's
  runner grants each owner's socket directory until TASK-0079.31) is a normal grant, and
  stays shared. `channel_exclusivity` stays `unenforced` (§7).
- **`fidelity` is still `SAME_INSTANCE`.** decision-192's "every process of the jail is in
  the one mount, network and pid namespace the supervisor holds" is amended: the processes
  share the jail's confinement (its mounts, its allowlist, its limits, its one network of
  nothing) and no longer its pid, mount, network or IPC namespace when they have their own.
- **A destroy does not wait out a grace a process can't use.** The ladder's first rung
  is `SIGKILL` for a leader that is a pid namespace's init and handles no `SIGTERM`
  (`term_rung`, decision-195), so a jail of such processes is not ended in two seconds per
  process. A process that handles `SIGTERM` still gets it and its grace.
- **Law 7's process scope** (§2) is this: the grade at the process scope is `Process.control`,
  `cooperative` at most until the battery.

Implementing task: TASK-0079.07. (Ruled 2026-10-16, decision-196.)

## 10. Communication with jails

Three inbound kinds, each with different liveness, trust, and delivery:

1. **Request channel** — synchronous, duplex, framed (length-prefix, CRC,
   resynchronizable). The `Spec` declares the channel by name; the jail
   LISTENs on a socket the runtime reserves for it in the jail's channel
   directory, and the trusted side dials it via `process.connect()`
   (decision-184, decision-185, decision-186). Each mechanism compiles the
   crossing (Seatbelt's grant on the channel directory, bwrap's bind of it,
   a container relay). Readiness
   is generic: a LISTEN channel is ready when its bind is observable.
   **Observable means a connect succeeds** — not that the endpoint path
   exists. A socket file outlives the process that bound it, so path existence
   reports ready for a jail that has already died. Readiness connects and
   closes; path-existence is never readiness.
2. **Control** — out-of-band interrupt/kill/lifetime signals, delivered by
   mechanism means (signal to group, exec into container, pipe-EOF). Works
   when 1 cannot. Graded (`control` axis).
3. **Shared media** — the implicit channels: writable mounts, pty stdin, a
   read-write attach. Never forbidden by fiat; always *enumerated* in the
   Spec's `shared_media` so `channel_exclusivity` grading covers exactly the
   real list. A read-write console attach is a channel request, policy-gated,
   not an observation feature.

**A channel directory per jail, and a socket reserved before each start
(2026-10-12, decision-184).** decision-0001's migration step 3b, its first
part. Until now a channel's socket was a path the `Spec` names, compiled at
launch, so a running jail could not take a new socket and two processes in one
jail could not each have their own. Ruled:

- **The runtime owns one channel directory per jail, `<jail_dir>/chan`.** Its
  name is brig's, beside `tmp`, `procs` and `jail.json`, never a `Spec` path:
  `core.runtime.channel_dir(jail_dir)`, which `CompileCtx.channel_dir` derives
  from the resolved `jail_dir`, so no context names it by hand. `HostRuntime.create`
  makes it (mode 0700) before any start and refuses an entry there that is not a
  directory it could have made (a link, a file), since a bind follows a link.
  When the `Spec` declares a channel, each mechanism that compiles `fs_write`
  grants it at create, once for the jail, **beside** today's per-endpoint
  grants, which stay (§5's channels keep their `endpoint` until
  TASK-0079.32): bwrap binds it read-write at stage 4, deduplicated with an
  endpoint directory that is the same, and binds it again after the seal
  (stage 5b) as it does a channel directory inside the jail directory;
  seatbelt emits `(allow file-write* (subpath CHAN))` after the seal and before
  the carve-outs, so a `write_denies` under it still wins. A `write_denies`
  entry at or above the channel directory is refused in both
  (`ChannelInsideWriteDeny`): the channel could not work there. A `Spec` with no
  channel gets no grant, and its compile is unchanged. seatbelt's half is
  checked by its rendered profile only (no darwin host runs brig's tiers here);
  the tests that pin it say so.
- **It squares with the jail directory's rulings by construction.**
  decision-173's seal still covers the rest of the jail directory: `chan/`
  joins `tmp/` as what stays writable inside it, and it is a subdirectory, so
  decision-174's refusal (no grant whose directory IS the jail directory) and
  decision-181's (no grant at or under `procs/`) are never reached by it. Their
  tests stand unchanged.
- **Reserve, then start (the owner's choice, 2026-10-12).**
  `jail.channel(name)` reserves a socket in the channel directory for a channel
  the `Spec` declares, and returns a `Reservation`: the channel's name, the
  path the process binds inside the jail (`bound_path`), and the host path the
  embedder dials (`endpoint`). An undeclared name is refused
  (`UnknownChannel`), saying to declare it in the `Spec`'s `channels`. The
  embedder puts `bound_path` in the argv it starts and passes the reservation:
  `jail.start(argv, channel=reservation)`. No environment variable carries it,
  so nothing an env mechanism strips can lose it, and it works on every jail
  type now. The reservation is the runtime's (`Runtime.reserve`):
  `HostRuntime` names it `<chan>/<16 lowercase hex>.sock`, fresh per call, and
  its in-jail and host paths are the same path. `Supervisor.start` takes
  `channel: Reservation | None` and refuses (`ReservationRefused`, a
  `ValueError`, before anything is made or spawned) a reservation that is not
  its own: one whose path is not directly in this jail's channel directory under
  a name it makes, whose endpoint is not the one it would hand out, or that a
  process the jail knows already binds. A process holds one socket, so the host
  stamps provenance by socket (law 6).
- **The process carries its channel.** `ProcessRecord` (and `record.json`) gain
  `channel` and `bound_path`, both `null` for a process started with none; an
  older record lacks them and reads unreadable, a doubt like any other.
  `Process` carries `channel`, `bound_path` and `endpoint`, and the jail's dict
  carries the records, so `JAIL_VERSION` is 7.
- **Readiness and the host path belong to the runtime.** `Runtime.endpoint(jail,
  process)` resolves a process's channel to the host path to dial (`None`
  without one), and `Runtime.ready(jail, process)` says whether it accepts a
  connection now: for `HostRuntime` a connect that succeeds, never the path's
  existence (§10.1). `Process.wait_ready(timeout)` polls it and raises
  `WaitReadyTimeout`. The fake runtime mirrors it: its endpoint is a relay path
  apart from the bound one, as a runtime that shares no socket with the host
  would hand out, and its readiness is a flag. `Jail.wait_ready(channel)` stays
  for a channel's declared endpoint until TASK-0079.32.
- **Residual, named.** A socket in the channel directory is reachable by every
  process of its jail until each has a mount namespace of its own
  (TASK-0079.07; closed where the host lets it, decision-196): a co-tenant's socket is shared media, not a channel to the
  host (decision-0001), and `channel_exclusivity` stays `unenforced` (§7). A
  link a process plants in the channel directory is dialled by the host as
  found, as a link in a per-endpoint directory always was. Grades are
  otherwise unchanged. *Amended by decision-185 (below, 2026-10-12): the host
  no longer dials a reserved socket as found.*

Implementing task: TASK-0079.05; bh-02's runner moves to it in TASK-0079.31,
and the `Spec` stops naming paths in TASK-0079.32. (Ruled 2026-10-12,
decision-184.) *Amended by decision-186 (below, 2026-10-13): the per-endpoint
grants and `Jail.wait_ready(channel)` are gone, and the channel directory is
every channel's one grant.*

**The host dials a reserved socket only through a check of what answers
(2026-10-12, decision-185).** decision-184 left a confused deputy named as a
residual: the channel directory is writable from the jail, so any process of it
(a co-tenant included, since a sibling's reserved name is in its argv) can put a
symbolic link at a reserved socket's path pointing at a host socket outside the
jail, and the host's readiness connect and the embedder's dial followed it,
reaching whatever the host's user can reach (a container daemon, an agent, a
session bus) and speaking the embedder's protocol there. A review planted one
and `Process.wait_ready` reported ready. Ruled, superseding that residual:

- **One verified dial, `Runtime.connect(jail, process)`, and readiness is it.**
  It returns a connected `AF_UNIX` stream socket to `process`'s channel, or
  raises: `EndpointRefused` (a `RuntimeError`; `endpoint` and `reason` are its
  fields) when what is there is not the process's own listener, and an
  `OSError` while nothing listens yet (`FileNotFoundError`, nothing bound;
  `ConnectionRefusedError`, bound with no listener). `Runtime.ready` is that
  same dial, closed at once: `False` on the `OSError`, and the refusal raised,
  never read as "not yet", so `Process.wait_ready` fails at once on a planted
  endpoint instead of waiting it out. `Process.connect()` is the embedder's
  face of it, and **the only documented way to dial a reserved channel**:
  `Process.endpoint` stays a field (for logs and errors), and dialling it raw
  skips the check. This is §10.1's `dial` for a reserved channel; bh-02's
  owners move to it in TASK-0079.31.
- **Before connecting, the path is a socket and not a link.** `HostRuntime`
  `lstat`s the endpoint and refuses a link, or anything else that is not a
  socket, without connecting. This alone is a race (the jail can swap a link
  in between the `lstat` and the `connect`), so it is the cheap half: it keeps
  the host from opening a connection to a planted target at all in the common
  case.
- **After connecting, the peer is a process of that process's group, the
  guarantee.** The kernel's record of who listens (`SO_PEERCRED` on Linux, the
  pid of the process that called `listen`, as the host's pid namespace numbers
  it) names the peer; brig reads its process group and requires it to be the
  started process's own (`ProcessRecord.pgid`), with the group's leader still
  holding its recorded identity, read after the peer's group, so the group's
  number cannot have passed to a stranger in between (decision-155; an
  `UNKNOWN` stamp is no identity and refuses, as decision-172 reads one).
  Otherwise the socket is closed and `EndpointRefused` raised, having sent
  nothing. The group, not the jail's processes or descent from the leader:
  brig's control is group-shaped (§9, law 7), every host start leads a group of
  its own (`start_new_session`), and bwrap emits no `--new-session` (§6), so a
  workload and everything it forks stay in it; with a pid namespace a
  co-tenant is another start's group and is refused, which closes
  decision-184's co-tenant residual for the host's dial (not for the
  co-tenants themselves, TASK-0079.07's; closed where the processes have mount
  namespaces, decision-196). Without one (the empty stack, all
  host starts in one session) a co-tenant could setpgid into a sibling's
  group and pass as it: never a host socket, but the residual stands there.
  Descent was
  rejected: an orphan reparents out of it on a host without a pid namespace,
  and the process table must be walked to see it. A listener that left its
  group (`setsid`) is refused, which is the safe direction. A nested pid
  namespace changes nothing: the kernel numbers the peer in the reader's
  namespace, and a peer it cannot number reads as pid 0 and is refused.
- **A listener that has left is refused, where the kernel can say so.** A pid
  names the process that listened, which may have exited and had its number
  reused (a daemon that forks after `listen`). Where Linux offers
  `SO_PEERPIDFD` (6.5 and later), brig takes the listener's pidfd and
  requires it alive both before and after reading the group, so the pid cannot
  name a newcomer; where it does not (an older kernel), the pid alone is read,
  and a jail that could take a dead listener's host pid inside its own group
  remains a residual, named here. darwin reads `LOCAL_PEERPID` and has no
  pidfd, so the same residual holds there; that path is written from the
  platform's headers and is unverified, since no darwin host runs brig's tiers
  here. A platform where brig reads no peer refuses every dial
  (`EndpointRefused`): no grade rises on it, and a channel there does not
  connect rather than connecting unchecked.
- **Unchanged.** Grades (no axis claims this; it is the host's own safety, not
  the workload's confinement), `HostSupervisor.start`'s refusal of a foreign
  reservation (decision-184), and `Jail.wait_ready(channel)` for a channel's
  declared endpoint, which still connects as found until TASK-0079.32 retires
  it. The fake runtime mirrors the seam: its `connect` hands back one end of a
  socket pair while `listening`, raises `ConnectionRefusedError` otherwise, and
  raises `EndpointRefused` with its `refusal` when one is set, through
  `ready` too.

Implementing task: TASK-0079.33. (Ruled 2026-10-12, decision-185.)
*Amended by decision-186 (below, 2026-10-13): `Jail.wait_ready(channel)` is
gone, and a peer the kernel can't report is a refusal, not "not yet".*

**The Spec names channels, not host paths (2026-10-13, decision-186).**
decision-0001's migration step 3b, its third part. decision-184 gave each jail
a channel directory and kept, beside it, the path each `Channel` declared
(`endpoint`): a grant per endpoint in every mechanism, three refusals about
where an endpoint may sit, and `Jail.wait_ready(channel)`, which dialled it as
found. A `Spec` is policy, and where a socket lives is the runtime's (a
container or a remote sandbox shares no host path with it). Ruled:

- **`Channel(name, kind)`.** A channel is a name the `Spec` declares and its
  kind (`LISTEN`, §5); it names no path. Every socket is one the runtime
  reserves in the jail's channel directory (`jail.channel(name)`, decision-184),
  and only a declared name can be reserved (`UnknownChannel`). `SPEC_VERSION`
  is 2 (a version-1 dict, whose channels carry `endpoint`, is refused as any
  other version is), and `JAIL_VERSION` is 8, since a jail's dict carries its
  channels.
- **The channel directory is every channel's one grant.** When the `Spec`
  declares a channel, each mechanism that compiles `fs_write` grants
  `<jail_dir>/chan` as decision-184 ruled (bwrap: bound read-write at stage 4,
  and again after the seal when there is one; seatbelt: its subpath after the
  seal and before the carve-outs), and nothing else for channels: bwrap's
  endpoint directory and seatbelt's socket literal are gone. seatbelt's
  unscoped `(allow network-bind)` still follows a declared channel and nothing
  else. A `Spec` with no channel compiles as before.
- **The three refusals about where an endpoint may sit, restated for the
  channel directory.** Each guarded a grant that a path chosen by the `Spec`
  could aim; the grant is now one brig names, so each holds by construction and
  its test asserts the positive, with a plant that aims the grant elsewhere:
  - *decision-174 (no channel grant is the jail directory):* the channel
    directory is a subdirectory brig derives from the jail directory
    (`channel_dir`), never the jail directory, so a channel never makes the
    jail directory writable; decision-173's seal is unchanged.
    `ChannelInsideJailDir` goes with the endpoints.
  - *decision-181 (no grant at or under the records):* `chan` and `procs` are
    siblings in the jail directory, so no channel grant reaches a record.
    `ChannelOnRecords` and `refuse_channel_on_records` go with the endpoints.
    A reservation is still refused unless its path is directly in the channel
    directory under a name the runtime makes (decision-184).
  - *The write-deny refusal (`ChannelInsideWriteDeny`):* a socket cannot be
    bound under a carve-out, so what is refused is a `write_denies` entry at or
    above the channel directory, in both mechanisms (decision-184's half). The
    half that refused an endpoint under a carve-out goes with the endpoints. A
    `write_denies` entry strictly inside the channel directory still wins over
    it (bwrap mounts it after, seatbelt emits it after).
- **`narrowed_to` meets channels by name.** Its refusal of one channel name
  bound to a different endpoint in each operand had nothing left to compare: a
  name in both operands declares the same channel, so the meet keeps the names
  both declare and `IncomparableSpecs` is raised for differing read models only
  (§5). The channels clause of `is_subset_of` is unchanged: a child's channel
  names are among its parent's.
- **The network battery binds a reserved socket.** Its positive control for a
  `Spec` that declares a channel binds a socket the jail reserved for it
  (`network_battery(spec, denied_address=..., channel=jail.channel(name))`),
  the one action every mechanism grants for a channel, and it is named
  `bind_a_reserved_channel_socket`. Construction refuses a `Spec` that
  declares a channel without a reservation, or with one for a channel it does
  not declare, as it refuses a `Spec` with no network action (decision-117).
- **`Jail.wait_ready(channel)` is gone**, with the readiness helper that
  connected to a declared endpoint as found (decision-185 named it the one dial
  left unchecked). Readiness is `Process.wait_ready`, and the dial
  `Process.connect`, both through the runtime's verified dial.
- **A peer the kernel can't report is a refusal.** `HostRuntime.ready` read any
  `OSError` from the dial as "nothing listens yet", and a failed read of the
  peer after a connect succeeded is one, so `Process.wait_ready` waited out its
  timeout on a socket that answered (found in TASK-0079.33's review). `dial`
  now closes the connection and raises `EndpointRefused` naming the error when
  the peer can't be read; only the path's `lstat` and the `connect` (nothing
  bound, nothing listening) read "not yet".
- **Unchanged.** Grades; decision-184's reservations and the records' fields;
  decision-185's verified dial; the residuals both name (a co-tenant's socket
  is shared media until each process has a mount namespace, TASK-0079.07; closed
  where the host lets them, decision-196).

Implementing task: TASK-0079.32. (Ruled 2026-10-13, decision-186.)

**Mailbox is deleted (2026-09-08, decision-153).** It was the second kind
here: an asynchronous, durable, ordered, many-writer-safe framed file with
deliverer-stamped provenance, consumed by the embedder's trusted driver and
never by the jailed process, with `NEXT_TURN` / `INTERRUPT` urgency composed
from the other kinds. Every sentence of that description is a sentence about
**the embedder's driver**, and reading it back is what settles the question:
the primitive's own contract said the jail never touches it. A queue that only
trusted code writes and only trusted code reads is not a way into a jail; it
is the embedder's own steering surface, and brig has no business shipping one.
Every embedder already has its own such surface. What brig keeps is the part that genuinely
crosses the boundary: the LISTEN channel above, on which steering arrives
re-encoded as work — which is what mailbox's own text said had to happen
anyway. `ChannelKind.MAILBOX` goes with it (§5); the framed-file primitive was
never built, so this deletes a plan and one enum member, not a mechanism.
(Implementing task: this phase.)

A fourth, trusted-side kind sits beside these: **co-tenant exec**
(`handle.exec`, §9) — a new process spawned *inside* the confinement by the
trusted side, interactive or not. It is not inbound data to the workload (the
workload need not even notice); it is the operator entering the jail. Its
laws: same-Spec inheritance, its pty enumerated as shared media while open,
every exec an event.

Mid-life injection (adding a file/artifact to a running jail) rides the
request channel as content — one path, uniform provenance, no per-mechanism
placement matrix.

Jail-to-jail: no primitive has two jailed endpoints. A parent steering a
child is the parent's outbound traffic becoming, in the embedder's trusted
process, an inbound `deliver`/`dial` to the child. brig ships spokes; only
the embedder's trusted code is a hub.

## 11. Observation

Three surfaces, all read-only (law 4):

- **Console** — the pty plane, for humans. `capture()` (current output),
  `stream()` (follow). Capabilities are declared per launcher.
  `attach_ro_command()` — an attach command returned as *data* for the
  embedder to print, never exec'd at the user — went with the `tmux` launcher
  (§8, decision-154); it named a command only that launcher could produce.
- **Events — returned as data, never written by brig (2026-09-08,
  decision-152).** Mechanisms are sensors that already make decisions the
  embedder wants — which names were scrubbed, which destinations are
  permitted, a limit tripping — and the point of this surface has always been
  that brig stops dropping them on the floor. What changed is where they go.
  A mechanism's `EventSource` returns payloads as data (§6); `run` stamps `ts`
  and `jail_id`, the two fields only it may supply; and the stamped `Event`s
  come back to the embedder on `Handle.compile_events` (what a sensor knew the
  instant it compiled) and from `Handle.exit_events()` (what a sensor makes of
  how the workload ended) -- since decision-183 `Jail.compile_events` and
  `Process.exit_events()`, per process. **brig writes no log.**

  The deleted design was one append-only JSONL stream per jail, tailed by
  observers, carrying five lifecycle kinds — `SPAWN`, `EXEC`, `EXEC_END`,
  `KILL`, `EXIT` — alongside the sensor records. Two things were wrong with
  it, and both only became visible with a real embedder. First, **every
  embedder that wants a durable record already has a log**, so brig was
  shipping a second, worse one beside it: unmerged, separately located,
  separately rotated, with its own atomicity claim to make and its own
  liveness question to answer. Second, **the lifecycle kinds were copies**.
  `KILL` restated a `KillReport` the caller was already holding. `SPAWN`
  restated argv, pid, pgid and cwd from the `Handle` returned in the same
  breath. `EXEC`/`EXEC_END` were a *registration* wearing an event's clothes —
  what teardown needed was the set of live siblings, which is now a file per
  member (§9). Only `EXIT` bought something real: an exit status readable by a
  process that never parented the workload.

  **That one capability came back, and not as a log (2026-09-08,
  decision-156).** For two milestones this paragraph read "that capability is
  genuinely gone" and §9 said `wait()` answers in the launching process and
  refuses everywhere else. It was the honest trade at the time and it was
  still a capability loss: a rehydrated handle's job is teardown, but an
  embedder cleaning up after a runtime that died holding a jail wants to
  record *how the jail ended*, and brig could only shrug. The launcher now
  runs the workload under a wrapper that writes the status to
  `<jail_dir>/exit` — one line, written once, renamed into place — and §9
  states what that does and does not cover. This is not the stream coming
  back: there is no appender, no tail, no second log beside the embedder's,
  and nothing accumulates. `ExitStatusUnobservable` remains, for the jail
  whose wrapper never wrote.

  **A third feed: what the egress proxy decided while the workload ran
  (2026-09-08, decision-157).** `connect_proxy`'s filter is a separate
  process that may not import brig at all (§13, decision-133), so its live
  allow/deny decisions cannot travel through `EventSource`, whose two methods
  are pure and answer at compile time and at exit. It writes them itself, as
  JSON lines under `<jail_dir>`, and both that mechanism's docstring and the
  proxy's said a `run`-layer reader would fold them in wherever the embedder's
  records go. **No such reader existed**, so every decision the filter made
  reached a file nobody opened — a whole mechanism's live output, declared and
  uncalled, which is the defect this library names everywhere else. `run` now
  ships that reader: it stamps `ts` and `jail_id` like every other record here
  and hands back stamped `Event`s. It is a **cursored** read — "what is new
  since I last looked" — because an embedder folds these into the record of
  the action that made the call, and resuming where the last read stopped is
  the caller's state to keep, not a frozen `Handle`'s. It is forgiving in
  exactly one direction: an absent file and a half-written trailing line are
  both "nothing new", while a whole line that is not the proxy's own record
  shape is loud, because something other than this jail's filter writing to
  that path is a fact an embedder must not fold in silently.

  `EventKind` is therefore three members, each a sensor's: `SPAWN` for what is
  known at compile time, `LIMIT_TRIP` for `rlimits` reading a `SIGXCPU`, and
  `EGRESS` for one decision the filter made on the wire. Law 8 is unchanged
  and now easier to hold: events are evidence, never the boundary, and nothing
  in brig's own control or teardown path reads one. (Implementing task: this
  phase.)
- **State** — `stat()`: alive, pids, rusage, current enforcement grades cheap
  enough for a status line to poll. Enforcement state is designed to be
  *displayed*, not archived: a client that cannot show "UNSANDBOXED" is
  wasting this. Plus workspace diff: `write_allows` roots are enumerable, so
  "what did it change" is a walk.

## 12. Probes

`handle.probe(battery)` runs canned violation attempts **inside the jail,
through the same stack, launcher, and channel the workload uses** — a policy
that holds for a side shell but not for the real path is not a policy.

Since decision-181 (§9, 2026-10-12) each probe is a process the jail starts
(`jail.start`), recorded like any other.

Verdicts are three-way, per probe:

- `PASS` — the attempt failed *with a denial signature* declared by the
  mechanism claiming that axis.
- `FAIL` — the attempt succeeded; the claim is false.
- `VACUOUS` — the attempt failed *without* a denial signature (wrong path,
  missing file, broken probe). A vacuous probe is a warning, never a pass.

**A verdict is decided against §6's classification subject**, not against raw
output: the probe engine builds the normalized denial string — the attempt's
stderr plus a canonical termination summary line carrying `signal:…` / `exit:…`
tokens — and matches the claiming mechanism's `denial_signatures` against *that*.
This is what lets a signal-shaped denial (`SIGXCPU`) and a text-shaped one
("Operation not permitted") be the same kind of claim. A mechanism declaring the
empty tuple has no way to reach `PASS` by signature at all, which is correct: its
axis is proved by the battery's positive controls, and every probe against it
that merely fails is `VACUOUS`. (Ruled 2026-08-23, decision-068.)

**A probe has one of THREE SHAPES, and the shape is data on the probe.** The
three-way verdict above is universal; what differs is what the probe *does* and
therefore what evidence can earn `PASS`. Everything written above this paragraph
describes the first shape and is unchanged by this fold.

- **`DENIAL`** — attempt a violation. `PASS` requires a declared signature to
  match §6's normalized classification subject; a failure *without* one is
  `VACUOUS`; a success is `FAIL`. This is the shape the paragraphs above define,
  verbatim and unamended.
- **`ABSENCE`** — perform a **permitted** observation and assert a
  policy-derived absence in its output. `PASS` requires the observation to exit
  **cleanly** *and* the asserted absence to hold; **a non-zero exit is
  `VACUOUS`, never `PASS`**, because an observation that did not run observed
  nothing. An `ABSENCE` `PASS` carries no matched signature, and that is its
  correct shape rather than a missing field.
- **`CONTROL`** — the positive control. `PASS` iff it succeeded.

**The empty `denial_signatures` tuple is therefore a ROUTING FACT, not a gap.**
A mechanism declaring it is not a mechanism missing something; it is a mechanism
whose axis is proved by an `ABSENCE` probe plus the battery's `CONTROL`, which
is exactly what the paragraph above already says when it states that such a
mechanism's "axis is proved by the battery's positive controls". `env_scrub` is
the first case: §6 records that scrubbing produces **absence, not denial**, so
an attempt-shaped probe was never the right instrument for it. The cpu probe
stays `DENIAL` and reaches `PASS` on `signal:SIGXCPU`.

This is what lets MILESTONES.md M4 EC1, this section's `PASS` clause, and
decision-067's empty tuple all hold at once — the `PASS` clause is written for
attempt-shaped probes, and a probe that does not attempt is not exempt from it
but outside it. (Ruled 2026-08-23, operator ruling round 14, decision-099, on
`doc-014` ambiguity A1. **Implementing tasks: `task-048`** declares the shape
table and the classification rule, **`task-050`** runs it through
`handle.exec`, **`task-053`** asserts it against `degraded()` — its env `PASS`
must carry `matched_signature is None`.)

Every battery includes **positive controls** (an action that must succeed —
write inside the workspace, dial the declared channel) so a broken probe
mechanism cannot impersonate a perfect jail. Probe outcomes are checked
against the report's grades: a probe that contradicts a grade fails the
battery loudly. Batteries ship for each axis; embedders add their own.

**A battery's own verdict is NOT `PASS` / `FAIL` / `VACUOUS`, and the difference
is the whole point.** A battery is a **consistency instrument**: the paragraph
above says exactly what it does — probe outcomes are checked against the
report's grades — and its verdict says whether that check agreed. So the
battery's three-way vocabulary is its own, and never `Verdict`'s:

- **`CONSISTENT`** — every probe outcome agrees with the report's grades. It
  does **not** mean enforcement was proven. Against a stack whose report
  honestly grades an axis `unenforced`, a probe that performs the violation and
  `FAIL`s is precisely what the report predicted, and the battery is
  `CONSISTENT` with it — the same asymmetry this section's `unenforced`
  parenthetical already states.
- **`CONTRADICTED`** — at least one probe outcome contradicts a grade. This is
  the "fails the battery loudly" case above, named.
- **`VACUOUS`** — a positive control failed, or a non-control probe asserted
  nothing. Nothing was learned; that is reported rather than rounded toward
  either of the others.

**`PASS` is retired at battery level deliberately, and this sentence is the
reason:** a reader cannot help hearing *enforcement proven* in the word `PASS`,
while a battery can agree perfectly with a report that claims nothing — so the
word would read stronger than what it asserts, which is this repo's recurring
defect installed into an API where every later reader inherits it.
**Per-probe verdicts keep `PASS` / `FAIL` / `VACUOUS` unchanged**: a probe
asserts a fact about *one attempt*, and `PASS` is honest at that altitude.

A `ProbeReport` therefore carries **per-axis observed outcomes** as data
alongside its battery verdict, so *what actually resisted* is a field to read
rather than an inference from a summary word.

**A probe has a deadline, and one that is still running at it is an outcome, never
an exception out of the battery.** The engine waits for each probe a bounded time
(15 s). A probe still running then is stopped through brig's own teardown for one
process (`Process.stop`: its group, verified, nothing of it left running) and
recorded as `unfinished`: a `DENIAL` or `ABSENCE` probe is `VACUOUS`, its detail
saying it did not finish in that many seconds, because a connect that never
completes is unreachability, not a refusal, and so no denial signature was seen
(an `ABSENCE` that did not run observed nothing, as its non-zero exit already
reads); a `CONTROL` probe is `FAIL` (the action did not succeed, which is what a
control that does not succeed already is), so its battery is `VACUOUS` by the
rule above. The battery therefore always returns a `ProbeReport`; a `TimeoutError`
out of `run_battery` was the defect (a Mac with a default route, where
`exec 3<>/dev/tcp/192.0.2.1/80` waits out a ~75 s connect timeout, crashed four
batteries instead of grading them). The deadline's length and the probes' argv
are unchanged. Implementing task: TASK-0079.35. (Ruled 2026-10-13, decision-187.) *Amended by decision-188 (below, 2026-10-14): an unfinished `CONTROL` is `VACUOUS`, not `FAIL`.*

**A probe that did not finish by its deadline is `VACUOUS`, whatever its shape, a
`CONTROL` included.** It amends decision-187's `CONTROL` clause, which recorded an
unfinished control as `FAIL`. A probe that was stopped observed nothing, so it
asserts no fact about the jail; `FAIL` asserts one (the action ran and did not
succeed), and under any report grade but `UNENFORCED` a `FAIL` adds a contradiction
to `ProbeReport.contradictions`. An unfinished probe therefore adds none. A control
that is not `PASS` already makes its battery `VACUOUS`, so the battery verdict is
unchanged; only the contradiction text goes. The deadline, its length, and the
rest of decision-187 are unchanged. Implementing task: TASK-0084.01. (Ruled
2026-10-14, decision-188.)

(Ruled 2026-08-24, operator ruling round 15, decision-104, on `doc-015` §5 —
direction (c): the vocabulary was the defect, not the algorithm and not the
criteria. **Implementing task: `task-053`**, whose rework round renames the
battery verdict in `brig/core/probes.py` and `brig/probe/runner.py`, adds the
per-axis observed outcomes, and re-greens the batteries' semantics tests against
the new name.)

## 13. Layering (pypeeker-enforced)

```
core  ←  mech  ←  stack  ←  run  ←  observe
                              ↑ ↖       ↑
                        runtime   probe ┘
```

| layer | contents | may import |
|---|---|---|
| `core` | Spec, axes, grades, Graded, Report, subset algebra, frames, `Event` and its serialization, threat lists, serialization | nothing (pure: no I/O, no clock, no randomness, no subprocess) |
| `mech` | Mechanism protocol, Step, all mechanisms, denial signatures | `core` |
| `stack` | Stack, compatibility matrix, presets, floors, aggregation | `core`, `mech` |
| `run` | the `Runtime` and `Supervisor` protocols and their records, `HostRuntime`, `Jail` and `Process`, teardown, readiness, dial, event stamping | `core`, `mech`, `stack` |
| `runtime` | runtimes that are not `run`'s own: `fake` today (decision-178); nothing in brig imports one, `run` included: an embedder picks a runtime by importing it | `core`, `mech`, `stack`, `run` |
| `observe` | Console, stat, workspace diff | `core`, `run` |
| `probe` | batteries, verdicts, report-vs-probe checks | `core`, `run`, `observe` |

Enforced by the custom `brig-layers` pypeeker rule (`pypeeker_rules/`) —
strict, keyed off file paths and literal import text — plus the builtin
`no-import-cycles` and `import-time-side-effects`. The builtin
`import-boundaries` is deliberately not used: under this flat layout it
fails open both ways (verified at M0 by planting violations — see
`pypeeker_rules/layers.py` for the trace). The gate's bite is proven by a
planted violation, not by a clean run (law 10).

Inside a layer, the same gate shapes module boundaries: the subset algebra and
serialization are methods on `Spec` in the module that defines it, because
splitting them into their own modules would make those modules import back into
the spec module and trip the builtin `no-import-cycles`.

## 14. Toolchain and testing

- Python ≥ 3.14, `uv` for everything, `ruff` (format + lint), `mypy --strict`,
  `pypeeker` strict as the architecture gate. `scripts/verify.sh` is the one
  definition of "the tree is good"; a commit hook runs its fast tier.
- Test tiers are defined in the repository's test rules (unit / integration / system)
  and enforced as pytest markers with `--strict-markers`. The one-line
  version: **unit** is pure (no subprocess, no network, no clock, `tmp_path`
  only); **integration** exercises one real mechanism or seam with real OS
  enforcement, observed from inside the jail; **system** drives full stacks
  through the public API with probe batteries, platform-gated. Tests leave
  the machine as they found it — a conftest gate fails the run on leaked
  processes or sockets.

## 15. Deferred and open

- **`oci_container` and `nix_closure`** land late by design (the relay and
  the closure builder are the two largest mechanisms); the model is validated
  on the cheap mechanisms first.
- **Windows** — out of scope entirely for now; stated, not implied.
- **A `suspend` control verb** — deferred until a consumer exists.
- **Staged-file delivery for sensitive `EnvPolicy.set` values** — writing them
  into `jail_dir` and having the compiled wrapper read them, instead of
  transiting them through host-visible argv (§5, law 9). Deferred until a
  consumer exists; named here so its absence is a decision rather than an
  oversight. (decision-093, P-13.)
- ~~**Event-stream liveness** — tail-a-file is the decision (no daemon);
  revisit only if a real consumer demonstrates the latency matters.~~
  **Closed 2026-09-08 by decision-152, by deleting the stream** rather than by
  answering the question: there is no file to tail, no daemon, and no latency
  to measure. Sensor records are returned to the embedder, which already has a
  log with its own liveness story (§11).
- **Cross-machine jails** (ssh launcher) — deferred; the Handle serialization
  format is designed not to preclude it.
- **A pty launcher** — deferred, and off §8's roster since decision-158
  (2026-09-08) rather than listed as if it existed. What it would buy is
  capturable, replayable output for any jail and a `PTY` launch feature, which
  is what `exec(interactive=True)` refuses for want of and what `console()`
  (§11) is absent for want of. Nothing else in the design waits on it: the
  launcher/enforcement split means it can be added without touching a
  mechanism.
- **A pidfd-shaped process identity** — decision-155 records a pid together
  with the moment that process started, which closes the reuse window to the
  resolution of the platform's own start-time reading (one second where that
  reading is `ps -o lstart=`). `pidfd_open` would close it exactly, and is
  Linux-only; deferred until brig has a Linux stack to want it for.
