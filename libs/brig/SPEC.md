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
   hostile. Teardown is process-group/tree-shaped, and its deliverability is
   itself graded in the report.
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
Spec ──compile──▶ Stack(Mechanisms) ──▶ Step ──launch──▶ Launcher ──▶ Handle
                        │                                               │
                        └────────── EnforcementReport ◀── probe() ──────┘
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
- **Launcher** — starts the final argv: plain subprocess, or pty-tee
  subprocess. Declares capabilities; refuses stacks whose requirements it
  cannot honor.
- **Handle** — the running jail as the embedder holds it: serializable,
  rehydratable in a later process, owner of teardown, the anchor for
  observation and communication.

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
    channels=(Channel(name, kind, endpoint), ...),
    shared_media=(...,),          # derived + declared; see §10
    provisioning=Provisioning(files=((path, digest), ...),
                              closures=(...,), env=(...,)),
)
```

Notes:

- **`write_denies` is new relative to prior art in the parent project** and
  exists for the self-escalation threat: a jail that can write `.git/hooks`,
  `.envrc`, or an agent config file inside its granted workspace executes code
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
  that jails a coding agent in its own repository. Until this ruling that
  secret had no spelling in an allowlist `Spec` at all (the field was refused
  as inactive), so the only allowlist jail over such a workspace was one that
  could read it. A mechanism compiles each carve-out against the trees it
  actually mounts: outside every one it is inert (absent is already denied);
  inside one it is masked; and where a mask cannot be made (for `bwrap`, a
  path that does not exist yet, §6) the `fs_read` grade drops and names it.
  The algebra is unchanged in shape: read denies union in the meet and grow
  in the denies clause under both models, and the two models stay
  incomparable. (Ruled 2026-09-28, decision-164. First embedder: bh-02's
  jailed kernel on Linux, whose project root is a write root and whose
  `local.env` is the credential it must not read.)
- **Threat lists ship as data, not defaults.** brig provides curated,
  documented tuples the embedder folds in explicitly:
  - `CREDENTIAL_READ_DENIES_HOME_RELATIVE` — `.ssh`, `.aws`, `.gnupg`,
    `.netrc`, `.config/gh`, `.docker`, `.kube`, `.npmrc`, `.git-credentials`,
    `.config/gcloud`, `.claude`, `.claude.json`, …
  - `SELF_MODIFY_WORKSPACE_RELATIVE` — `.git/hooks`, `.git/config`,
    `.bashrc`, `.zshrc`, `.profile`, `.envrc`, `.vscode`, `.idea`, agent
    config files (`AGENTS.md`, `CLAUDE.md`, `.claude`), …
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
  or when one channel name is bound to a different kind or endpoint in each
  operand. Every one of those per-axis formulas already *is* the greatest lower
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
  path/name/endpoint, and on the *inactive* read-model field being populated
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
- Serialization: `to_dict`/`from_dict`, versioned, round-trip stable.
- **The version is `SPEC_VERSION = 1`, and an unknown key at any level is a
  refusal.** There is no migration framework and no tolerated extra field: a
  dict brig cannot account for is rejected, not partially understood.
  `from_dict` re-runs construction validation, so serialization cannot smuggle
  in a Spec that could not have been constructed directly.

## 6. Mechanisms

```python
class Mechanism(Protocol):
    name: str
    axes: frozenset[Axis]                 # what it claims
    def compile(self, spec: Spec, ctx: CompileCtx) -> Step: ...

@dataclass(frozen=True)
class Step:
    wrap: ArgvTransformer                 # argv -> argv
    env: Mapping[str, str]
    staged: tuple[StagedFile, ...]        # profiles, scripts — written pre-launch
    helpers: tuple[Helper, ...]           # e.g. egress proxy; declared lifetime
    requires: frozenset[LaunchFeature]    # e.g. NEW_PROCESS_GROUP
    grades: Mapping[Axis, Graded]         # grade + detail per claimed axis
    denial_signatures: tuple[Pattern, ...]  # what this mechanism's denials look like
    events: EventSource | None            # optional sensor feed (§11)
```

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
  mapping cannot cover it — yet the staged profile and usually the LISTEN
  endpoint live under it, which would put the same bug in the one path the
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
the mechanism does — compiling the SBPL rules that let the jail bind its
declared LISTEN endpoint — and **not** an axis it claims. Its declared `axes`
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
Linux for the first time, in a container: `tools/linux-check.sh` in the keel
workspace.)

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
  (1) `--unshare-all`; (2) the jail's own furniture, `--proc /proc` and
  `--dev /dev`, first among the mounts so every spec-derived mount stacks on
  top of it; (3) `read_allows` as `--ro-bind`; (4) the declared LISTEN
  channel's endpoint DIRECTORY as `--bind`; (5) `write_allows` as `--bind`;
  (6) `write_denies` as submounts *after* the write roots — which is what
  makes deny-over-allow true here; (7) the `read_denies` carve-outs that exist
  inside a mounted tree, last of all (decision-164, below); (8) `--`, then the
  workload's argv.
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
- **The channel directory is mounted BEFORE the write roots (2026-09-08,
  decision-163), and until it was, a `write_denies` carve-out inside a jail
  directory was compiled and then silently unmade.** The endpoint's directory
  is the one mount whose path policy does not choose — an embedder puts the
  socket in the jail directory, and a jail directory that also HOLDS the
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
  container: `tools/linux-check.sh` in the keel workspace, and
  `tests/e2e/test_strict_linux_journey.py` is where it showed.)
- **Source resolved, destination as the Spec wrote it.** Every mount names its
  source by the realpath'd form (so a symlinked path mounts the tree it
  actually points at) and its destination by the `Spec`'s own path (so the
  workload's view matches the policy that was written — a jail where `/bin/sh`
  is missing because `/bin` was normalised into `/usr/bin` is a jail that
  cannot start).
- **The LISTEN channel costs a writable DIRECTORY, where seatbelt's costs a
  path.** §10.1 makes each mechanism compile the crossing; seatbelt can name
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
  rung accounts for. And no `--tmpfs /tmp`: §5 puts temp space inside
  `write_allows`, and handing the jail writable space nothing granted would
  make the `fs_write` claim false by exactly one directory.

(Implementing task: this phase.)

Deliberately absent: a cooperative filesystem guard (see §4), and `ulimit -u`
/ `RLIMIT_NPROC` anywhere (per-user on darwin and commonly on linux; capping
it strangles the operator's desktop and masquerades as a policy denial — a
finding both parent projects hit independently).

## 7. Stacks

`Stack(mechanisms).compile(spec, floors) -> CompiledJail`

**`CompiledJail`** is a frozen dataclass carrying `spec`, `report`, `wrap`,
`env`, `staged`, `helpers`, `requires`, `mechanism_names`, `matrix_version`.
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
grades `unenforced` (§6's roster note). (Ruled 2026-08-24, decision-118 for the
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
`unenforced`.

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

## 8. Launchers

```python
class Launcher(Protocol):
    name: str
    capabilities: frozenset[LaunchFeature]   # NEW_PROCESS_GROUP, PTY, DETACH, ...
    def launch(self, jail: CompiledJail, *, argv, cwd, io: IoPolicy) -> Handle: ...
```

- `subprocess` — pipes or files for stdio, detached, new process group.

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
the empty stack, everywhere.

A launcher refuses a `CompiledJail` whose `requires` exceed its
`capabilities`. Refusal names the missing feature.

**`IoPolicy`** starts at the honest minimum and widens only when a launcher can
deliver more: stdout and stderr to files under the jail directory (the
filenames are configurable, the content mode is not), stdin from `/dev/null`
(fixed). Pipes and ring buffers arrive with a pty launcher, if one is ever
written — until such a launcher exists, a wider `IoPolicy` would be a
capability claim with nothing behind it, which law 2 forbids. (Folded from the built shape by decision-044,
discharging decision-038's A8.)

## 9. The Handle

```python
class Handle:
    def to_dict(self) -> dict: ...            # everything teardown/observe needs
    @classmethod
    def from_dict(cls, d) -> Handle: ...      # rehydrate in a later process

    def wait_ready(self, channel: str, timeout: float) -> None
    def alive(self) -> bool
    def stat(self) -> JailStat                # pids, rusage, current grades
    def interrupt(self) -> bool               # mechanism-delivered
    def kill(self) -> KillReport              # tree/group teardown of EVERYTHING
                                              # the handle names: workload group,
                                              # exec siblings (this section's
                                              # `exec`, below), then
                                              # helpers, containers
    def dial(self, channel: str) -> Connection
    def exec(self, argv, *, interactive=False) -> ExecHandle   # see below
    def console(self) -> Console | None       # §11
    def exit_events(self) -> tuple[Event, ...]  # §11
    def probe(self, battery) -> ProbeReport   # §12
```

plus the fields an embedder reads rather than calls: `compile_events`, every
mechanism sensor's `known_at_compile()` payload stamped at launch (§11);
`report`, the `EnforcementReport` the stack compiled; and the identity pair
`pid`/`start_time` (with `helper_pids`/`helper_stamps` beside it), which is
what makes a recycled pid read as gone rather than as this jail — see "A pid
is not an identity" below.

**An unimplemented capability is absent from the surface, never a raising stub.**
The block above is the finished shape. A milestone that cannot yet honour one of
these methods ships a `Handle` *without* it — not one that declares it and
raises. A method that raises lies to `hasattr` and to every embedder that
feature-detects; it is law 1's silent downgrade wearing an API's clothes.
(Private delegates filled inside the same milestone are not this case: the
surface never named them.)

**`interrupt` ships (2026-09-08, decision-151).** It was absent under exactly
that law from M2 (ambiguity A10) until an embedder needed it: keel's sandbox
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

**`exec` — a sibling process inside the same confinement** (the
`docker exec -it` experience, for every stack). Semantics:

- The exec'd process is subject to the **same Spec** as the workload — never
  a weaker one. A mechanism that cannot guarantee this refuses exec.
- Fidelity is mechanism-shaped and reported honestly: `oci_container` and
  `bwrap` (via namespace entry) place the process inside the *same boundary
  instance*; `seatbelt` can only start a sibling under an *identical
  profile* — equivalent enforcement, different instance — and the
  `ExecHandle` says which. The empty stack execs a plain process, graded
  accordingly.
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
says so at every call site. A pidfd (Linux) would close both; it is a future
mechanism decision, not an assumption this section makes. (decision-051,
superseded here; decision-144's acceptance ends by its own terms.)

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
durable record of the session, and a handle in it is a handle a later process
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
deliverability itself a graded claim rather than an assumption.

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

## 10. Communication with jails

Three inbound kinds, each with different liveness, trust, and delivery:

1. **Request channel** — synchronous, duplex, framed (length-prefix, CRC,
   resynchronizable). The jail LISTENs on a declared endpoint; the trusted
   side dials via `handle.dial()`. Each mechanism compiles the crossing
   (Seatbelt bind rules, bwrap socket-dir bind, container relay). Readiness
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

**Mailbox is deleted (2026-09-08, decision-153).** It was the second kind
here: an asynchronous, durable, ordered, many-writer-safe framed file with
deliverer-stamped provenance, consumed by the embedder's trusted driver and
never by the jailed process, with `NEXT_TURN` / `INTERRUPT` urgency composed
from the other kinds. Every sentence of that description is a sentence about
**the embedder's driver**, and reading it back is what settles the question:
the primitive's own contract said the jail never touches it. A queue that only
trusted code writes and only trusted code reads is not a way into a jail; it
is the embedder's own steering surface, and brig has no business shipping one.
keel's Session Interface is that surface for this embedder, and any other
embedder already has its own. What brig keeps is the part that genuinely
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
  how the workload ended). **brig writes no log.**

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

(Ruled 2026-08-24, operator ruling round 15, decision-104, on `doc-015` §5 —
direction (c): the vocabulary was the defect, not the algorithm and not the
criteria. **Implementing task: `task-053`**, whose rework round renames the
battery verdict in `brig/core/probes.py` and `brig/probe/runner.py`, adds the
per-axis observed outcomes, and re-greens the batteries' semantics tests against
the new name.)

## 13. Layering (pypeeker-enforced)

```
core  ←  mech  ←  stack  ←  run  ←  observe
                              ↖       ↑
                                probe ┘
```

| layer | contents | may import |
|---|---|---|
| `core` | Spec, axes, grades, Graded, Report, subset algebra, frames, `Event` and its serialization, threat lists, serialization | nothing (pure: no I/O, no clock, no randomness, no subprocess) |
| `mech` | Mechanism protocol, Step, all mechanisms, denial signatures | `core` |
| `stack` | Stack, compatibility matrix, presets, floors, aggregation | `core`, `mech` |
| `run` | Launchers, Handle, teardown, readiness, dial, event stamping | `core`, `mech`, `stack` |
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
  definition of "the tree is good"; the Claude commit hook runs its fast tier.
- Test tiers are defined in `.claude/rules/` (unit / integration / system)
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
