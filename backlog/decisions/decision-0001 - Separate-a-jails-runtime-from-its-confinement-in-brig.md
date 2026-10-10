---
id: decision-0001
title: Separate a jail's runtime from its confinement in brig
date: '2026-10-10 21:42'
status: proposed
---
## Context

brig's model is six nouns (SPEC.md section 3): `Spec -> Stack(Mechanisms) -> Step -> launch -> Launcher -> Handle`. It has one plug-in point, `Mechanism` (a pure, runtime-checkable Protocol: `name`, `axes`, `compile(spec, ctx) -> Step`), and `Stack` takes any object that matches it, so an embedder can bring a mechanism of its own. A `Step`'s main lever is `wrap: argv -> argv`: every technology is a command prefix (`bwrap ... --`, `sandbox-exec -p ...`) around processes the launcher itself starts.

Everything after compile has one implementation, hardwired to host process groups:

| Control | Today | A container needs |
|---|---|---|
| interrupt | `os.killpg(pgid, SIGINT)` | `docker kill --signal INT` |
| kill, verified | signal ladder on the group, `ps` scan of its members | `docker rm -f`, `docker inspect` |
| liveness | the leader's pid and start time | the container's state |
| exit status | a wrapper writes `<jail_dir>/exit` | `docker wait`, `docker inspect` |
| exec | re-run the wrap prefix with a new argv (a second container) | `docker exec CONTAINER argv` |
| tether | a watcher in the group kills it | a watcher runs `docker rm -f` |
| identity in a saved handle | pgids, pid and start time | a container id |

SPEC.md section 10 already says control is "delivered by mechanism means (signal to group, exec into container, pipe-EOF)", and section 15 plans `oci_container` (M10), but a `Step` has no field for control and there is one launcher. So three things don't fit:

1. **A jail with a life of its own**: a container behind a daemon, a microVM, a remote sandbox, an ssh host. Its processes are not the launcher's descendants.
2. **A jail that holds many processes in one instance.** `Handle.exec` exists, but its fidelity is `EQUIVALENT_PROFILE` at best: on bwrap it starts a second bwrap (new namespaces, every mount again). `SAME_INSTANCE` is in the SPEC and unbuilt (out of scope since task-046). An exec takes no working directory and has no channel (output to files, input `/dev/null`).
3. **bh-02's needs**: one jail per session that its Python process, its extensions process and each sub-agent's REPL run in (M6), instead of a jail per program.

Other systems put the plug-in point at the lifecycle: Kubernetes' CRI (`RunPodSandbox`, `CreateContainer`, `ExecSync`, `StopPodSandbox`, with runc, gVisor or Kata behind it), E2B (`Sandbox.create()`, `commands.run()`), Modal (`Sandbox.create`, `exec`, `terminate`). Command wrappers (bubblewrap, nsjail, Codex CLI, Claude Code's sandbox-runtime) launch a fresh sandbox per command. brig's mechanism layer is the richest of the wrappers (composition, per-axis grades, probes); it lacks the lifecycle seam.

Found while looking (separate tasks, not this decision): `connect_proxy` lets an inherited `NO_PROXY` bypass the egress filter; teardown counts a zombie its group still lists as a survivor where PID 1 doesn't reap.

## Decision

### Each concern has one home

| Concern | The question it answers | Home | Shape |
|---|---|---|---|
| Policy | What may the jail touch, reach, consume, and how does it talk? | `core` | `Spec`, pure data (unchanged) |
| Confinement | How is each axis enforced, and how well? | `mech` | `Mechanism.compile -> Step` (unchanged, plus a role) |
| Composition | Do these fit together, and how strong is the whole? | `stack` | `Stack.compile -> CompiledJail`, which now also names its runtime |
| Lifecycle and control | How does the jail start, run more, stop, end? | `run` (protocol), `runtime/*` (implementations) | `Runtime` (new) |
| Transport | How does trusted code reach a process inside? | the runtime | a channel endpoint per process |
| Persistence | How does a later process find and end it? | `run` | `Jail` and `Process` records |
| Evidence | What happened? | `run`, `observe` | `Event`, sensors (unchanged) |
| Verification | Is the report true? | `probe` | batteries, run as processes in the jail |

### Two roles of mechanism

- A **boundary** mechanism defines the instance: bwrap's namespaces and mounts, Seatbelt's profile, a container. At most one per stack, and it names the runtime it needs.
- An **inner** mechanism shapes each process inside a boundary: `env_scrub`, `rlimits`, `connect_proxy`'s routing. Any number, each naming the runtimes it works under.

`Step` keeps `wrap`, now the per-process wrap (inner mechanisms, applied at every start), and gains `boundary`: what the runtime applies once when it creates the instance. A runtime that can't hold an instance (Seatbelt has no namespace) applies the boundary again at each start, and grades that start's fidelity `EQUIVALENT_PROFILE`.

### The Runtime protocol

The lifecycle and control of one kind of jail. It does I/O, so it lives in `run`, not `mech`:

```python
class Runtime(Protocol):
    kind: RuntimeKind                        # HOST, OCI, ...
    capabilities: frozenset[Capability]      # SAME_INSTANCE, PROCESS_SIGNAL, PTY, ...

    def create(self, jail: CompiledJail, *, cwd: str, tether: int | None) -> JailRecord
    def start(self, jail: JailRecord, argv: Sequence[str], *, cwd: str,
              channel: str | None, io: IoPolicy) -> ProcessRecord
    def signal(self, jail: JailRecord, process: ProcessRecord, sig: Signal) -> bool
    def alive(self, jail: JailRecord, process: ProcessRecord | None) -> bool
    def exit_status(self, jail: JailRecord, process: ProcessRecord) -> int | None
    def stop(self, jail: JailRecord, process: ProcessRecord) -> KillReport
    def destroy(self, jail: JailRecord) -> KillReport
    def control_grades(self, jail: CompiledJail) -> Mapping[Scope, Graded]
```

`create` starts the instance with no workload in it. `destroy` ends the instance and everything in it without any process's cooperation (law 7), and verifies it. Records are plain data, serializable, carrying the runtime's own identity for each thing (pid and start time, a container id).

### Jail and Process replace Handle

- `Jail`: the running instance as the embedder holds it. Its report, its records, `start(argv, *, cwd, channel)`, `destroy()`, `dial(process, channel)`, `probe(battery)`, `to_dict()`.
- `Process`: one process in it. `interrupt()`, `stop()`, `wait()`, `alive()`, its exit events, its fidelity (`SAME_INSTANCE`, `EQUIVALENT_PROFILE`, `PLAIN`).
- Today's launch is `create` then `start`; today's `exec` sibling is a second `start`.
- Rehydration takes the runtimes from the embedder: `Jail.from_dict(d, runtimes={RuntimeKind.HOST: host})`. A record naming a kind the embedder didn't pass is refused. Data never chooses code (law 5).
- Durable records under the jail directory: `jail.json` (runtime kind, instance identity, report, channel endpoints), and `processes/<id>.json` with its own exit record (which also settles decision-162's one-exit-record-per-directory).

### Composition rules (`Stack.compile`)

1. Exactly one runtime per compiled jail: the boundary's, or `HOST` when there is none (the empty stack).
2. At most one boundary mechanism; two are refused (law 2).
3. Every inner mechanism must name the chosen runtime as one it works under, or the stack is refused.
4. The `control` axis is graded by the runtime, at two scopes: the jail (must be non-cooperative to reach `enforced`) and a single process.

### How each backend maps

| Stack | Runtime | One instance, many processes | Process control | Jail control |
|---|---|---|---|---|
| empty | `HOST` | plain processes (`PLAIN`) | process group | process groups |
| `seatbelt` + inner | `HOST` | profile again per start (`EQUIVALENT_PROFILE`) | process group | process groups; a `setsid()` escape is the named gap (TASK-0035) |
| `bwrap` + inner | `HOST` | a supervisor inside the namespace (`SAME_INSTANCE`) | through the supervisor: `best_effort`, gap: a process in the jail can kill the supervisor | the outer group and tether end the namespace: `enforced` |
| `oci` + inner | `OCI` | `docker exec` (`SAME_INSTANCE`) | `docker exec` signalling, graded by what the image allows | `docker rm -f`, verified by `inspect`: `enforced` |
| later: ssh, remote sandboxes | their own | their exec | theirs | theirs |

The bwrap supervisor is brig's own program, standard library only, delivered as a staged file and run as the instance's first command. It takes requests only on a pipe inherited from the runtime, which nothing it starts inherits (`close_fds`), and it makes itself non-dumpable so a process in the jail can't open that pipe through `/proc` or `ptrace` it. It can still be signalled, hence the per-process grade.

### Layering

```
core  <-  mech  <-  stack  <-  run  <-  runtime/host, runtime/oci
                                ^
                     observe, probe
```

`run` holds the `Runtime` protocol, `Jail`, `Process`, records, readiness and dial, and event stamping. Today's launcher, teardown ladder, exit wrapper, exec, tether, pgid and identity code moves to `runtime/host`. `observe` and `probe` depend on `run` only. The embedder picks runtimes by importing them; `run` never imports one.

### What stays

`Spec` and its algebra, axes and grades, floors, `Mechanism` and the mechanisms' compile logic, denial signatures, sensors and events, probes and batteries, and every law. Law 7's sentence "Teardown is process-group/tree-shaped" becomes "Teardown is runtime-shaped and verified".

### bh-02's use

`runner:confined` creates one `Jail` per session, tethered to bh-02. `Runner.start(argv, cwd, endpoint)` becomes `jail.start(...)`. A stuck Python process is stopped and started again in the same jail. `/release` stops each program through its owner, then destroys the jail. A host mount undone destroys it, as a jail ends today. `started.reads()` and `writes()` come from the jail's spec. Sub-agents' REPLs are processes in it (M6). `runner:unconfined` could become brig's empty stack instead of bh-02's own subprocess code.

### Migration, each step green

0. Apart from this decision: fix `NO_PROXY`, make liveness ignore zombies, and measure what a jail start costs on Linux and macOS.
1. **Name the seam, no change in behaviour.** Add `Runtime` and a `HostRuntime` that holds today's launcher, teardown, exec and tether; `Handle` delegates to it. Every tier passes unchanged. Add a fake runtime for unit tests, so the protocol has a second implementation from the start.
2. **Mechanism roles.** Mark boundary and inner, resolve the runtime in `Stack.compile`, and split `wrap` from `boundary`. Golden argv tests for a single launch stay as they are.
3. **Jail and Process.** `create` plus `start`; per-process records, exit and stop; probes run as processes. Rewrite SPEC.md sections 3, 8 and 9 with a decision paragraph. Move bh-02's runner to one jail per session (TASK-0074).
4. **bwrap's supervisor**, for `SAME_INSTANCE` and per-scope control grades.
5. **`OCI` runtime** (brig's M10): create, exec, destroy, inspect, `--init`, a bind-mounted or relayed channel; its integration tier skips visibly without docker. It proves the seam with a real second user.
6. Later: remote runtimes, and cgroup limits per runtime (systemd scope on the host, the container's own under OCI).

## Consequences

- A new jail technology is a boundary mechanism, plus a runtime if it has a life of its own. Docker is an addition, not a rewrite.
- Every backend can hold many processes, at the best fidelity it can give, and says which.
- bh-02 gets one jail per session and sub-agents in it.
- brig's most central code moves (the handle, launcher, teardown, exec), and the saved handle's format changes (`SPEC_VERSION`).
- SPEC.md sections 3, 8 and 9 and law 7's wording change.
- The bwrap supervisor is new code inside the jail, with a named gap of its own.

## Open questions

- [ ] Names: `Runtime`, `Controller` or `Driver`; `Jail` and `Process`, or keep `Handle` for the jail.
- [ ] bwrap: a supervisor, or entering the namespaces from the host (`setns`) for each start; the second needs no code inside the jail, but entering an unprivileged user namespace and re-applying its filters is unproven.
- [ ] Channels: one socket per process, or one per jail carrying every process's messages.
- [ ] Inner mechanisms under OCI: apply `env_scrub` and `rlimits` inside `docker exec`, or compile them to container flags.
- [ ] Where a jail-lifetime helper (the egress proxy) runs under OCI: on the host, or as a sidecar.
- [ ] Whether a per-process stop through a supervisor is acceptable under law 7, given the jail-wide kill stays non-cooperative.
