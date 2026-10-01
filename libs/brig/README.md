# brig

Composable, honestly-graded sandboxes for running untrusted processes.

A `Spec` describes the jail (filesystem, network, limits, env, channels).
`Mechanism`s — Seatbelt, bubblewrap, cgroup scopes, an egress proxy, rlimits,
env scrubbing, containers, Nix closures — each compile a slice of it and
compose into a `Stack`. The `subprocess` `Launcher` starts the result and
hands back a serializable `Handle` for teardown, exec-into-jail, observation,
and probes. Every axis of enforcement is graded — `enforced`, `best_effort`,
`cooperative`, `unenforced` — against what the stack can actually deliver, and
`probe()` proves the grades by attempting violations from inside.

brig keeps no log and no state of its own. A mechanism's sensors return
their records as data, `run` stamps them, and they come back on the
`Handle` — `compile_events` for what a mechanism knew when it compiled,
`exit_events()` for what it makes of how the workload ended — plus
`run.read_egress_decisions`, the cursored reader for what the egress filter,
which is a separate process, decided on the wire. The embedder decides where
they all go. The one thing brig does write is `<jail_dir>/exit`: the
workload's exit status, once, so a `Handle` rehydrated in another process can
still say how the jail ended.

Read `SPEC.md` (the contract and its laws) and `MILESTONES.md` (the build
order, and what actually shipped against it). Where the two disagree, SPEC.md
is the one describing the library.

## Standing alone

brig imports the standard library and itself, and nothing else. It knows nothing about what
embeds it; an adapter to anything else belongs in the embedder. Two rules in brig's own gate
hold that: `brig-standalone` (stdlib and brig only) and `brig-layers` (the DAG in `SPEC.md`
section 13), both in `pypeeker_rules/brig.py`, configured under `[tool.pypeeker]` in this
directory's `pyproject.toml`.

The tiers are `unit`, `integration` and `e2e`, and every brig test carries exactly one.
`tests/conftest.py` holds brig's tests to that, keeps the leak sweep, and adds a POSIX floor:
the integration and e2e tiers skip by name where the OS cannot host them.

## What Phase 3 changed, and what it deleted

Having a first real embedder made
four parts of the plan answerable that were not answerable in the
abstract. Each is a `SPEC.md` change first and code second, with a dated
decision paragraph in the section it belongs to.

- **`Handle.interrupt` ships** (decision-151). `SIGINT` to the workload's
  process group, returning whether the signal was *delivered* — never
  whether anything stopped, which is what `kill`'s verified report is for.
  It was absent from the surface for three milestones under §9's own law
  against raising stubs; an embedder cancelling one action
  is the consumer that made it worth building, because without it, cancelling one action
  meant killing the jail.
- **The per-jail event stream is deleted** (decision-152). No
  `events.jsonl`, no `EventLog`, no `SPAWN`/`EXEC`/`EXEC_END`/`KILL`/`EXIT`
  lifecycle records. Every embedder that wants a durable record already has
  a log, so brig was keeping a second, worse one; and four of the five
  lifecycle kinds were copies of something the caller already held. What
  replaced each reader: exec-sibling registration is a file per live
  sibling under `<jail_dir>/execs/`, teardown's record is the `KillReport`
  it returns, and the exit status lives in the launching process
  (`Handle.wait()` refuses honestly anywhere else — superseded four rulings
  later by decision-156, below). `Handle.env` — the
  launching process's whole environment — went too, which is what makes a
  serialized handle safe for an embedder's log to carry.
- **`ChannelKind.MAILBOX` is deleted** (decision-153) with §10's whole
  mailbox primitive. Its own contract said the jail never touches it, which
  makes it the embedder's steering surface rather than a way into a jail.
  `LISTEN` stays and is now the only kind.
- **The `tmux` launcher is off the roster** (decision-154). It was never
  built; its value was observation, which the embedder owns.
  `attach_ro_command()` and the `"pane"` kill-item kind went with it.

`MILESTONES.md` is the record of the plan as it stood, so it still carries the
tmux launcher (M8) and the mailbox primitive (M13) — marked, where they
appear, as deleted rather than pending. `SPEC.md` is the contract, and it is
where the deletions are ruled; where the two documents disagree, `SPEC.md` is
the one describing the library.

## What Phase 4 changed

Four more rulings, each a `SPEC.md` change first and code second, and each one
a gap this library had been *naming* rather than closing.

- **A pid is not an identity** (decision-155). Every pid brig writes down — the
  workload leader, each `JAIL_LIFETIME` helper, each exec sibling — is now
  recorded together with the moment that process started, and every liveness
  and kill decision compares both. A recycled pid reads as **gone**:
  `alive()` says so, `interrupt()` returns `False` rather than signalling a
  stranger, and teardown reports `ALREADY_GONE` without running a rung.
  decision-144 had accepted that window on the grounds that no atomic
  alternative existed at this layer; its own second condition for ending the
  acceptance was holding a pid across a durable boundary, which a serialized
  handle in an embedder's log does.
- **The exit status crosses a process boundary again** (decision-156).
  decision-152 deleted the event stream and admitted it cost exactly one
  capability: a status readable by a process that never parented the workload.
  The launcher now runs the workload under a tiny wrapper that writes the
  status to `<jail_dir>/exit`, once, atomically. Not a log — one line, one
  write, nothing to tail or rotate. `ExitStatusUnobservable` remains for the
  jail whose wrapper never wrote, which is the `SIGKILL`ed group.
- **The egress proxy's decisions have a reader** (decision-157). The filter is
  a separate process that may not import brig, so it writes its allow/deny
  records itself — and for two milestones nothing read them. `run` now folds
  them back as stamped `Event`s, cursored so an embedder can attribute them to
  the action that made the call.
- **The launcher roster is one launcher** (decision-158). `subprocess_pty` sat
  on `SPEC.md` §8's roster and was never written, which is the same dishonesty
  as a raising stub one level up. It is in §15 as deferred work now, where an
  unbuilt thing belongs.

## Linux, as of 2026-09-08

`bwrap` is real, and `strict_linux()` — `[bwrap, rlimits, env_scrub]` — is
the preset that composes it. It is the Linux sibling of `scratch_darwin()`:
`fs_read`, `fs_write` and `network` all `enforced`, `env` `enforced` from
`env_scrub`, `limits` `best_effort` because `rlimits` reaches cpu and
nothing else. It is deliberately **not** `SPEC.md` §7's `strict()`, which
also names `systemd_scope` and `pasta`; neither exists, and a stack shipped
under that name would be claiming them.

Three things about it are worth knowing before you compose it, and all three
are refusals rather than surprises:

- **It is the ALLOWLIST half of the two read models.** A `DENY_LIST` Spec is
  refused by name. A mount cannot mask a path that does not exist yet, so a
  denylist emulated on mounts would silently compile to nothing in exactly
  the credential directories a denylist is written for.
- **`read_allows` has to cover the system tree the workload needs**,
  including `/bin/sh` and `/usr/bin/env` if `env_scrub` is in the stack —
  it composes *inside* the jail, which is the whole point of the ordering.
- **The declared LISTEN channel's endpoint DIRECTORY is bind-mounted
  writable**, because a socket cannot be bind-mounted before it exists. That
  is one writable path no `write_allows` entry named, and the `fs_write`
  grade's own detail says so.

**Where it is verified.** The compile is pure, so its golden argv, its six
refusals and the mount order are unit tests that run anywhere. The
enforcement is not: `tests/integration/test_bwrap_fs.py`,
`tests/integration/test_bwrap_network.py` and
`tests/e2e/test_strict_linux_journey.py` drive a real `bwrap` and skip —
visibly, naming the binary and the package — where there is none. brig's
development machine is darwin, so those three files need a Linux host: CI's
ubuntu job, or that job's steps run in an ubuntu container.

**They were first executed 2026-09-08**, by that container, and the run was
not a formality — it found three defects in this library that nothing on
darwin could reach: `RLIMIT_CPU`'s soft limit equalled its hard limit, so
Linux killed with `SIGKILL` and every `SIGXCPU` claim `rlimits` makes
silently never fired (decision-161); a second launch into one jail directory
read the FIRST launch's exit record (decision-162); and `bwrap` mounted the
channel's directory AFTER the write roots, so a jail directory holding the
workspace stacked read-write over the `write_denies` carve-outs inside it and
the jail could write what it was denied (decision-163). All three are fixed,
and the tiers are green on Linux. No GitHub Actions run has been observed
yet — a container is not the runner image.

**Read carve-outs, 2026-09-28 (decision-164).** An allowlist `Spec` may now
carry `read_denies`: the secrets inside an allowed tree (a `local.env` at the
top of a writable workspace). `bwrap` masks the ones that exist — a file reads
EACCES, a directory is an empty mode-0000 read-only tmpfs — and leaves the
absent ones alone with `fs_read` graded `best_effort`, naming them, because a
mask's mount point would be created on the host. The same run measured what
that means for `write_denies`: an absent carve-out's empty directory is made
on the HOST, parents included, and outlives the jail; the embedder removes it
after teardown, never during (a mount point removed on the host is detached
inside the jail). `scripts/linux-jail-check` at the workspace root is this
workspace's container run of the bwrap tiers.

**A jail can end with its embedder, 2026-09-30 (decision-167).** A launch is
detached, so a jail outlived an embedder that died without calling `kill`, and
a program its workload left in the background kept running with its grants.
`launch(..., tether=fd)` takes the read end of a pipe the embedder keeps the
write end of: when that closes (the embedder closed it, or died, `SIGKILL`
included), a watcher in the jail's process group sends the group `SIGKILL`.
Under `bwrap` that ends the whole pid namespace; under seatbelt a process that
left the group (`setsid()`) is out of its reach, as it is of `kill`'s.
`tests/integration/test_tether.py` kills a launching process to show it.

## Development

Requires Python >= 3.15 and [uv](https://docs.astral.sh/uv/). brig is a member of a uv
workspace; from the workspace root:

```bash
uv sync --all-packages
uv run pytest libs/brig -q                  # every tier
uv run pytest libs/brig -m unit -q          # one tier
uv run mypy brig/src
scripts/arch-check                     # includes brig's own gate, run from this directory
```
