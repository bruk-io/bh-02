---
id: decision-0001
title: Separate a jail's runtime from its confinement in brig
date: '2026-10-10 21:42'
status: proposed
---
## Context

brig's model is six nouns (SPEC.md section 3): `Spec -> Stack(Mechanisms) -> Step -> launch -> Launcher -> Handle`. Its plug-in points are protocols an embedder can implement: `Mechanism` (`name`, `axes`, `compile(spec, ctx) -> Step`) and `Battery` (core/probes.py). A mechanism of the embedder's own composes only where every pair is in the compatibility matrix, a module-level table keyed by name (stack/__init__.py:653), and the stack special-cases some mechanisms by name. A `Step`'s main lever is `wrap: argv -> argv`: every technology is a command prefix (`bwrap ... --`, `sandbox-exec -p ...`) around processes the launcher itself starts.

Everything after compile has one implementation, hardwired to host process groups (checked against the code):

| Control | Today | A container needs |
|---|---|---|
| interrupt | `os.killpg(pgid, SIGINT)` (run/handle.py:472) | `docker kill --signal INT`, which reaches only its PID 1 |
| kill, verified | a signal ladder on the group, verified by a `/bin/ps` scan (run/teardown.py) | `docker rm -f`, verified by `docker inspect` |
| liveness | the leader's pid and start time (handle.py:428) | the container's state |
| exit status | a `python -c` wrapper writes `<jail_dir>/exit` (run/_exit_status.py) | `docker wait`, `docker inspect` |
| exec | runs the wrap prefix again with a new argv (run/exec_.py:199): a second container | `docker exec CONTAINER argv` |
| tether | a watcher in the group does `killpg(0)` | a host watcher runs `docker rm -f` |
| identity in a saved handle (`HANDLE_VERSION`) | pgids, pid and start time | a container id |

SPEC.md section 10 says control is "delivered by mechanism means (signal to group, exec into container, pipe-EOF)", and section 15 plans `oci_container` (brig's own M10), but a `Step` has no field for control, there is one launcher (run/launcher.py:359) and no Launcher protocol in code. So three things don't fit:

1. **A jail with a life of its own**: a container behind a daemon, a microVM, a remote sandbox, an ssh host. Its processes are not the launcher's descendants.
2. **A jail that holds many processes in one instance.** `Handle.exec` exists, but it is `EQUIVALENT_PROFILE` at best: on bwrap it starts a second bwrap, every namespace and mount again. `SAME_INSTANCE` is in the SPEC and unbuilt (exec_.py:149). An exec takes no working directory and has no channel (output to files, input `/dev/null`).
3. **bh-02's needs**: one jail per session that its Python process, its extensions process and each sub-agent's REPL run in (bh-02's milestone M6, not brig's M6), instead of a jail per program.

Other systems put the plug-in point at the lifecycle: Kubernetes' CRI (`RunPodSandbox`, `CreateContainer`, `ExecSync`, `StopPodSandbox`, with runc, gVisor or Kata behind it), E2B (`Sandbox.create()`, `commands.run()`, an agent inside the VM), Modal (`Sandbox.create`, `exec`, `terminate`). Command wrappers (bubblewrap, nsjail, Codex CLI, Claude Code's sandbox-runtime) launch a fresh sandbox per command. brig's mechanism layer is the richest of the wrappers (composition, per-axis grades, probes); it lacks the lifecycle seam.

**Found while designing this (each its own task, ahead of this decision: TASK-0075 to TASK-0078):**
- brig's own host-side Python programs import from the workload's working directory. The exit wrapper runs `python -c` with `cwd` set to the workload's (launcher.py:236), and no brig interpreter runs with `-I`. Reproduced 2026-10-10 with the empty stack: a `subprocess.py` planted in the workspace ran inside the wrapper, outside any jail. The rlimits trampoline and the egress proxy (`python -m`) have the same shape (not reproduced). TASK-0075, high priority.
- `connect_proxy` lets an inherited `NO_PROXY` bypass the egress filter (connect_proxy.py:125 leaves it unset rather than empty; 11 egress tests pass only with it unset). TASK-0076.
- Teardown counts zombies as survivors where PID 1 doesn't reap (5 kill, teardown and probe tests fail in such a container). TASK-0077.
- Teardown acts on a record it can't verify: `recycled()` treats an empty start stamp as "not recycled" (run/_identity.py:159), so a registration under `execs/` with an empty stamp makes the ladder signal whatever group it names. TASK-0078.

## Decision

### Each concern has one home

| Concern | The question it answers | Home | Shape |
|---|---|---|---|
| Policy | What may the jail touch, reach, consume, and how does it talk? | `core` | `Spec`, pure data; channels by name, never by host path |
| Confinement | How is each axis enforced, and how well? | `mech` | `Mechanism.compile -> Step`, plus an optional `runtime` |
| Composition | Do these fit together, and how strong is the whole? | `stack` | `Stack.compile -> CompiledJail`, which names its runtime kind and grades every axis, `control` included |
| Lifecycle and control | How does the jail start, run more, stop, end? | `run` (protocol), `runtime/host`, `runtime/oci` | `Runtime` |
| Transport | How does trusted code reach a process inside? | the runtime | a channel directory per jail, a socket per process |
| Persistence | How does a later process find and end it? | `run` | `Jail` and `Process` records; identity opaque to `run`, verified by its runtime |
| Evidence | What happened? | `run`, `observe` | `Event`, sensors (unchanged) |
| Verification | Is the report true? | `probe` | batteries, plus a control battery driven from the host |

`Runtime` replaces the `Launcher` noun, and `Jail` and `Process` replace `Handle`. brig keeps six nouns: Spec, Mechanism, Step, Stack, Runtime, Jail (with its processes). `LaunchFeature` becomes the runtime's capabilities.

### Mechanisms name their runtime; the matrix keeps the order

A mechanism may name the one `RuntimeKind` it needs (`Mechanism.runtime`; bwrap and Seatbelt: `HOST`; a container: `OCI`). The compatibility matrix stays the authority for which mechanisms compose and in what order, so `rlimits` stays outside bwrap and Seatbelt as SPEC.md section 7 records. Two mechanisms naming different runtimes are refused (law 2), and the matrix already refuses a pair it doesn't list, so an inner mechanism under a runtime it doesn't support needs no rule of its own.

On `HOST`, `create` runs the whole composed wrap around brig's supervisor instead of around the workload. The scrubbed environment and `RLIMIT_CPU` are inherited by every process the supervisor starts; the gap is the supervisor's own CPU time, which the report names. Golden argv tests change only in the innermost argv.

### Grades stay in the stack, at two scopes

`RuntimeKind`, `Capability` and `Scope` (`JAIL`, `PROCESS`) are pure data in `core`. A runtime's grades are static per kind, so `Stack.compile` can read them and floors can be checked, `require(control=...)` included. The report's `control` axis is the jail scope: whether the jail and everything in it can be ended without cooperation. The process scope travels on each `Process` with its fidelity (`SAME_INSTANCE`, `EQUIVALENT_PROFILE`, `PLAIN`), not in the report. `channel_exclusivity` depends on the runtime too (a relay, exec stdio), and is graded the same way. No control grade above `cooperative` ships without a battery driven from the host that plants survivors (a `setsid()` child, a process ignoring `SIGTERM`, a stopped supervisor) and a positive control (law 10).

### The Runtime protocol: an instance and an agent

```python
class Runtime(Protocol):                # the instance: non-cooperative
    kind: RuntimeKind
    capabilities: frozenset[Capability]
    def create(self, jail: CompiledJail, *, cwd: str, tether: int | None) -> JailRecord
    def alive(self, jail: JailRecord) -> bool
    def destroy(self, jail: JailRecord) -> KillReport      # verified
    def agent(self, jail: JailRecord) -> Agent | None      # None: this jail can only be destroyed

class Agent(Protocol):                  # inside the instance: shared by every runtime
    def start(self, argv: Sequence[str], *, cwd: str, channel: str | None,
              io: IoPolicy) -> ProcessRecord
    def signal(self, process: ProcessRecord, sig: Signal) -> bool
    def wait(self, process: ProcessRecord, timeout: float) -> int | None
    def stop(self, process: ProcessRecord) -> KillReport
```

The instance part is the runtime's own (namespaces and a tether on `HOST`, the daemon on `OCI`, a VM or a lease elsewhere). The agent is one protocol every runtime shares: brig's supervisor on `HOST`, the same supervisor under `OCI` where the image has `python3` (with `docker exec` as a lower-fidelity fallback, since Docker can't signal an exec), a vsock agent for a microVM. Readiness and resolving an endpoint to a host path belong to the runtime, since a container on Docker Desktop or a remote sandbox shares no host socket. Pause, stats and file copy stay out until a runtime needs them.

### The supervisor (HOST, bwrap)

- It is PID 1 of the jail's pid namespace (`--as-pid-1`), so the kernel drops `SIGKILL` and `SIGSTOP` sent to it from inside, while a `SIGKILL` from the host still lands. It reaps orphans, which also ends the zombie problem inside the jail.
- It starts each process as PID 1 of a nested pid namespace (`os.unshare(CLONE_NEWUSER | CLONE_NEWPID)`), so stopping a process ends its namespace, a `setsid()` escape included, and siblings can't see each other's `/proc`. Some hosts restrict nested user namespaces: measure, and grade the process scope by what holds.
- It runs `python -I` with an empty environment, from a working directory the jail can't write, with its source delivered read-only (`--ro-bind-data`, since bwrap's allowlist hides `jail_dir` and stages nothing) and every import done before any jail process exists. A Spec whose allowlist lacks the interpreter is refused.
- Its control channel is a socketpair inherited from the runtime and passed to nothing it starts. It carries `SCM_RIGHTS`, so stdio the host opened is passed in and `IoPolicy` needs no writable directory the Spec didn't name. Requests from several callers are multiplexed by id.
- EOF on that channel means the host is gone: the supervisor ends everything (the tether, from the inside). Every request has a host-side timeout that escalates to `destroy`.
- On Seatbelt there is no namespace and no supervisor: each start applies the profile again (`EQUIVALENT_PROFILE`), process control is group-shaped, and the `setsid()` escape is the named gap (bh-02's TASK-0035).

### Jail and Process

- `Jail`: the instance as the embedder holds it. Its report, its records, `start(argv, *, cwd, channel)`, `destroy()`, `processes()` (with labels), `stop(processes)`, `probe(battery)`, `to_dict()`.
- `Process`: one process in it. `interrupt()`, `stop()`, `wait()`, `alive()`, its exit events, its fidelity and process-scope control grade, the in-jail path its channel binds and the host path the embedder dials (a relay where the instance can't share one). `dial` stays optional; bh-02 dials with asyncio itself.
- Today's launch is `create` then `start`; today's exec sibling is a second `start`.
- Channels: the runtime owns one channel directory per jail, mounted at `create` and passed to compile in `CompileCtx`; each `start` makes a socket there. `start(channel=...)` names a channel the Spec declares. One socket per process, so the host stamps provenance by socket (law 6).
- Helpers with `JAIL_LIFETIME` live from `create` to `destroy` and are reached by the tether. Today the tether doesn't reach them and the exit waiter never ends them (run/_waiters.py), so a session's egress proxy would outlive a crashed embedder.

### Records and rehydration

- Records are data about kill targets, so the jail must never write them. A Spec whose write grants reach `jail_dir` is refused, or the records live where no grant reaches; the embedder's own `to_dict` is the authority.
- Nothing acts on an identity it can't verify: pid and start time, never an empty stamp; for OCI a `brig.jail` label and the daemon's id, with `DOCKER_HOST` taken from the runtime object, never from a record.
- `Jail.from_dict(d, runtimes={RuntimeKind.HOST: host})` takes the runtimes from the embedder; a record naming a kind it didn't pass is refused (law 2). A socketpair can't cross `to_dict`, so a rehydrated bwrap jail has no agent: it can be destroyed, and its `start` is absent, not raising (SPEC.md section 9).
- Each process's exit record lives beside its record, which also settles decision-162's one exit record per directory.

### Co-tenants are shared media

Processes in one instance share a uid and the filesystem; without nested namespaces they also share a pid namespace and `/proc`, and can read each other's environment and reopen each other's descriptors (Yama limits attach, not reading). That is counted as shared media under law 9 and named in the report's `channel_exclusivity` detail.

### Law 7

"Teardown reaches everything the jail contains (group, tree, namespace, container), never a single process, and is verified; its deliverability is graded per scope."

### Layering

```
core  <-  mech  <-  stack  <-  run  <-  runtime/host
                                ^   <-  runtime/oci
                     observe, probe
```

Each runtime is a row of its own in `brig-layers`, so `host` and `oci` can't import each other, proved by a planted violation. `run` holds the protocols, `Jail`, `Process`, records and event stamping, and never imports a runtime; the embedder picks runtimes by importing them. Until step 3, `HostRuntime` lives in `run`.

### OCI, walked through

`create` is `docker create --init --user <embedder uid>` (else project files end up owned by root) with the Spec compiled to container flags: mounts, `--network`, `--ulimit`, an env file (never `-e K=V`, which is argv: law 9). `env_scrub` and `rlimits` aren't composed inside; the `oci` mechanism compiles them itself, since the trampoline can't run in an image without brig. The channel directory is bind-mounted on Linux and relayed where a socket can't cross (Docker Desktop). The tether is a host watcher that runs `docker rm -f`. Egress filtering is a sidecar proxy on an `--internal` network; `connect_proxy` stays `HOST`-only.

### What stays

`Spec` and its algebra, axes and grades, floors, the compatibility matrix, the mechanisms' compile logic, denial signatures, sensors and events, probes and batteries, and every law but law 7's wording. Egress decisions become jail-scoped, so attributing one to a single action needs the process's socket or its own proxy.

### bh-02's use

- `runner:confined` creates one `Jail` per session, tethered to bh-02. The runner contract becomes `start(argv, cwd) -> started`, with `started.endpoint` the host path to dial. Read allows derived from argv, and `git_author`, move to create.
- A stuck Python process is stopped and started again in the same jail. Today `/restart python` ends the whole jail, background programs included; that holds only if each process is its own nested namespace, and "bh-02's use" must say so if it isn't.
- `/release` stops each program through its owner, then destroys the jail once nothing remains; otherwise it says which program still runs (the runner README's rule that each owner stops its own).
- The mount tripwire ends the jail with a kill that doesn't depend on the runtime, tells every owner `ended()`, and the next start creates a new jail.
- A session-long jail widens the window for absent `read_denies` paths (decision-164) and keeps decision-168's mount points for the whole session.
- Sub-agents' REPLs are processes in the session jail. Without nested namespaces a sub-agent can reach the kernel's channel and read its environment; the M6 milestone also needs labelled processes, stopping a set of them, concurrent starts, and a narrowed child jail that ends with its parent's.
- `runner:unconfined` could become brig's empty stack instead of bh-02's own subprocess code.

### Migration, Spec first (WORKFLOW.md)

0. Ahead of this decision: the four bugs above, the import-path escape first, and a measure of what a jail start costs on Linux and macOS.
1. **Name the seam.** `Runtime`, `Agent` and a `HostRuntime` in `run` that holds today's launcher, teardown, exec and tether; `Handle` delegates. bwrap can't hold an empty instance yet, so `HostRuntime` offers launch-shaped `create` plus first `start` only. Tests that import `run`'s private modules (about 30), `test_probe_forgery`'s `dataclasses.replace` on `Handle`, the rehydration tests and the ps-based leak sweep move with it. A fake runtime gives the protocol a second implementation from the start.
2. **Runtimes in composition**: `Mechanism.runtime`, the runtime kind in `CompiledJail`, static runtime grades. SPEC.md sections 6 and 7 change first; `MATRIX_VERSION` bumps if a row changes.
3. **Jail and Process**: per-process records and exit, one channel directory per jail, probes as processes, `HANDLE_VERSION` bumped. SPEC.md sections 3, 8 and 9 change first. bh-02's runner moves to one jail per session (TASK-0074).
4. **The supervisor**, with the control battery; SPEC.md section 4 and law 7 change first.
5. **`OCI` runtime** (brig's M10), reusing the supervisor as its agent; its integration tier skips visibly without docker.
6. Later: remote runtimes (an agent over vsock or a lease instead of a tether), and cgroup limits per runtime.

## Consequences

- A new jail technology is a mechanism, plus a runtime if it has a life of its own. Docker is an addition, not a rewrite.
- Every backend can hold many processes, at the best fidelity it can give, and says which, per scope.
- bh-02 gets one jail per session and sub-agents in it.
- brig's most central code moves (the handle, launcher, teardown, exec); `HANDLE_VERSION` changes; SPEC.md sections 3, 4, 6, 7, 8 and 9 and law 7 change.
- The supervisor is new code inside the jail, hardened as above, with its gaps graded rather than assumed.

## Reviews

Two read-only reviews, 2026-10-10: one against brig's laws, SPEC and code; one against separation of concerns, other sandboxes and bh-02's runner. Taken from them: the roles of mechanism dropped in favour of `Mechanism.runtime` and the existing matrix (the roles reversed a recorded ordering); grades kept in the stack at two scopes; records treated as kill authority; the supervisor as PID 1 with nested namespaces and `-I`; channels owned by the runtime; the runtime split into instance and agent; helpers tethered; co-tenants as shared media; law 7's wording; a Spec-first migration whose step 1 admits what it changes; and the import-path escape, now a task ahead of everything.

## Open questions

- [ ] Whether nested user namespaces are allowed on the hosts bh-02 runs on; if not, the process scope grades `cooperative` and "bh-02's use" names what a restart no longer ends.
- [ ] Where records live so no Spec grant reaches them, given the channel directory is mounted writable.
- [ ] Whether the control battery can plant a stopped supervisor without the test itself needing privileges.
