# Milestones

**What this document is.** The build order brig was planned and built to,
milestone by milestone, with each milestone's scope and exit criteria as they
were written. Docstrings and tests all over `packages/brig` quote these
criteria by number ("MILESTONES.md M2 exit criterion 1", "M4 EC2"), so the
numbering and the wording are load-bearing and are preserved.

**Where it disagrees with SPEC.md, SPEC.md is right.** This is a record of the
plan; SPEC.md is the contract for the shape that is *built*. Four things
planned here were later deleted rather than built, each by a dated ruling in
SPEC.md, and each is marked below where it appears: the per-jail event stream
(decision-152), the `tmux` launcher (decision-154), the `subprocess_pty`
launcher (decision-158), and the mailbox primitive (decision-153).

**The commands are historical.** The milestones were written against brig's
own repository and a later host workspace, and their commands (`verify.sh`,
`packages/brig` paths) name tooling that is not here. The three test markers
are `unit`, `integration` and `e2e` (the third was once spelled `system`).
Criteria quoted verbatim in code keep their original wording. WORKFLOW.md has
the commands that run today.

Process notes, binding on whoever decomposes these:

- **Lite agile.** Each milestone ships something usable and verifiable on its
  own. Milestones are taken in order; a milestone is not started until the
  previous one's exit criteria pass. Within a milestone, tickets should be
  small enough for a single implementing agent to finish and verify in one
  sitting.
- **Decomposition contract.** An Opus-tier agent breaks a milestone into
  tickets. Every ticket must name: the files it touches, the layer(s) it lives
  in (SPEC.md §13), the test tier(s) it adds to, and the exact command that
  proves it done. Implementation goes to Haiku/Sonnet-tier agents; a ticket
  that needs judgment calls about jail semantics goes back up, not sideways.
- **Verification-first.** Exit criteria are commands with expected outcomes.
  Where a criterion guards a gate or a safety property, it includes a
  **mutation check**: plant the violation, watch the gate fail, remove it
  (SPEC.md law 10). A clean run alone never closes a milestone.
- **Honesty carry-over.** Every milestone that adds enforcement adds the
  matching report grades, denial signatures, and probe(s) in the same
  milestone — never "grading later."
- Platform-gated work (linux-only, docker-only) must skip cleanly elsewhere,
  and the skip must be visible in output, not silent.

---

## M0 — Gates that bite

**Goal.** A repo where every later milestone's work is automatically held to
the rules: uv project, ruff, mypy --strict, pypeeker layer gate, test markers,
commit hook.

**Value.** Every subsequent agent-written change is checked by machinery, not
by reviewer stamina.

**Scope.**
- `pyproject.toml` finalized: uv, ruff, mypy strict, pytest strict markers
  (`unit` / `integration` / `system`; the third is spelled `e2e` in this
  workspace), pypeeker with the custom `brig-layers`
  rule (strict; the builtin `import-boundaries` fails open under this flat
  layout — verified by planting, see `pypeeker_rules/layers.py`) +
  `no-import-cycles` + `import-time-side-effects` with the §13 layer table.
- The one definition of green, as a script. (In brig's own repository this was
  `scripts/verify.sh`, with `fast` and `full` tiers; here it is the
  workspace's `./tools/verify.sh`, which has no tiers and runs every gate over
  every package.)
- A pre-commit gate that blocks a `git commit` while that script fails. (In
  brig's own repository, a `.claude/` hook; here, `tools/install-hooks.sh`.)
- Package skeleton: `brig/core` only (other layers appear when their
  milestone lands); one placeholder unit test so every gate has something to
  chew.
- `tests/conftest.py`: enforce that every test carries exactly one tier
  marker; leaked-process teardown check (grows with later milestones).

**Exit criteria.**
1. `./tools/verify.sh` passes end to end on a clean tree.
2. Mutation checks, each demonstrated then reverted:
   - a planted cross-layer import (e.g. `from brig.run import x` inside
     `brig/core/`) fails `pypeeker check --strict`;
   - a planted type error fails mypy; a planted format error fails ruff;
   - a `git commit` attempted with a failing tree is blocked by the hook.
3. A test with no tier marker fails collection.

---

## M1 — The core model

**Goal.** `brig/core` complete per SPEC.md §4–§5: Spec (fs policy with
`write_denies` and both read models, network, limits, env, channels,
shared media, provisioning), axes, four grades, `Graded`, `EnforcementReport`
with floors, subset algebra, threat lists as data, serialization.

**Value.** The contract exists as typed, tested, serializable data. An
embedder can already write and validate policy against it; everything later
is delivery.

**Scope.** Pure code only — no subprocess, no I/O. Property tests
(hypothesis) for the algebra; example-based tests for the threat lists and
serialization.

**Exit criteria.**
1. `uv run --locked pytest packages/brig -m unit` covers: subset algebra laws (reflexive;
   antisymmetric up to normalization; `narrowed_to(x)` always
   `is_subset_of(x)`; every axis participates — a test per axis proves that
   axis alone can break subset-ness), report floor refusal, `to_dict`/
   `from_dict` round-trips (property-tested).
2. Mutation check: removing any single axis from `is_subset_of`'s
   conjunction makes a named test fail (run once, documented in the PR).
3. Threat lists exist as documented tuples with the SPEC.md §5 contents;
   a unit test pins that `SELF_MODIFY_WORKSPACE_RELATIVE` includes
   `.git/hooks` and that `CREDENTIAL_READ_DENIES_HOME_RELATIVE` includes
   `.ssh` (canary entries, so accidental truncation is loud).
4. `./tools/verify.sh` green; no new layer beyond `core`.

---

## M2 — Run something: empty stack, subprocess launcher, Handle

**Goal.** `brig/stack` (empty stack + validation shell) and `brig/run`
(subprocess launcher, Handle with serialization, group teardown, readiness,
`exec` non-interactive). First end-to-end: `Stack([]).compile(spec)` →
`launch` → a live, killable, rehydratable Handle whose report says
`unenforced` everywhere.

**Value.** The library runs real processes with honest (all-unenforced)
reports. The parent project's `none` provider is now expressible in brig —
the first adoption target exists.

**Scope.**
- Stack compile pipeline (claims/coverage/floors run even when empty; the
  compatibility matrix exists with zero pairs).
- `subprocess` launcher: detached, new process group, stdio to files.
- Handle: `to_dict`/`from_dict`, `alive`, `stat` (pids + report), `kill` as
  group teardown with per-item `KillReport`, `wait_ready` for LISTEN
  channels, `exec` (plain sibling process, cwd + env of the jail).
- ~~Event stream file: lifecycle events only — `SPAWN`, `EXEC`, `EXEC_END`,
  `KILL`, four kinds and no others (decision-036: SPEC.md §9 requires an exec
  event to say *when it ended*, which one record written at exec-start cannot
  carry, so `EXEC` and `EXEC_END` are two records). The JSONL shape lands here
  so every later mechanism appends to something real.~~ **DELETED 2026-09-08
  by decision-152**, once a real embedder existed: every embedder that wants a
  durable record already has a log, so brig was keeping a second, worse one,
  and four of the five lifecycle kinds were copies of something the caller
  already held. What replaced each reader is named in SPEC.md §11. The one
  capability it genuinely bought — an exit status readable by a process that
  never parented the workload — came back at decision-156 as a single
  `<jail_dir>/exit` file written once by the launcher's exit wrapper.

**Exit criteria (integration tier).**
1. Launch `python -c` workload; handle round-trips through
   `to_dict`/`from_dict` in a *separate process* and `kill()` from the
   rehydrated handle ends it.
2. Group-kill mutation check: a workload that spawns a child (`bash -c
   'sleep 100 & wait'`-shaped); after `kill()`, **no process from the tree
   survives** — and a deliberately single-pid kill (test-local) is shown to
   leak the child, proving the tree check detects what group-kill fixes.
3. `wait_ready` on a Unix-socket LISTEN channel: returns when a real bind
   appears, times out cleanly when it never does.
4. `handle.exec(["pwd"])` runs in the jail's cwd; the exec appears in the
   event stream. (The second half is now a registration file per live sibling
   under `<jail_dir>/execs/` — decision-152 deleted the stream, and SPEC.md §9's
   binding clause was always *durability outside the live object* rather than a
   named medium.)
5. Floors work end to end: `require(fs_read=ENFORCED)` against the empty
   stack refuses at compile with the axis named.
6. The suite's leak-check catches, at session teardown: (a) any process whose
   own argv still carries the run-id token; (b) any process in a process group
   the poller ever observed carrying that token; and (c) any process whose
   parent is the pytest session process — which is every workload and every
   exec sibling this suite launches directly, zombies included. It does **not**
   catch: a token-less **grandchild** of a leaked exec sibling (arm (c) keys on
   `ppid == harness_pid`, one generation only, and arms (a)/(b) never saw the
   sibling's caller-supplied argv); a leak reaped between tests but live
   mid-session (arm (c) is final-sweep-only, deliberately, so a synchronous
   helper `/bin/ps` in another test cannot false-positive it); or an untagged
   descendant inside the harness's own pgid (the accepted, documented cost of
   never recording `harness_pgid`). Mutation-checked: disabling the
   exec-sibling reap makes the sweep itself red, naming the arm.
   (Reworded by operator ruling 2026-08-23 round 6, decision-050, from
   "Conftest leak-check now covers spawned process groups" — a claim broader
   than the sweep, and one no change could falsify.)

---

## M3 — The degraded jail: env_scrub, rlimits, denial signatures

**Goal.** `brig/mech` layer with the two no-jail-tech mechanisms and the full
mechanism contract: Step, argv trampoline, denial signatures, grades,
aggregation into the stack report.

**Value.** brig now *enforces* things — on any POSIX host with nothing
installed: env is `enforced`, cpu_seconds is `enforced`, everything else
honestly `unenforced`. The `degraded()` preset ships.

**Scope.**
- `env_scrub`: allow-names model; child env verified.
- `rlimits`: exec-trampoline (`python -m brig.mech.trampoline --cpu N --
  argv...`) — no `preexec_fn`, so any launcher can carry it.
- Mechanism protocol + Step finalized; single-claim validation live;
  ordering matrix gains its first real pair (rlimits outermost of the two,
  rationale recorded).
- Denial signatures on both mechanisms (`env_scrub`'s is deliberately the
  **empty tuple** — scrubbing produces absence, not denial, and a generic
  pattern there would manufacture false `PASS`es at M4; ruled 2026-08-23,
  decision-067); limit-trip and scrub events.

**Exit criteria (integration tier).**
1. `env_scrub`: workload prints its env; scrubbed names absent, allowed
   names present. Mutation check: with the mechanism removed from the stack,
   the same probe sees the secret — proving the test can fail.
2. `rlimits`: a spin loop under `cpu_seconds=1` dies with SIGXCPU within
   tolerance; the trip is recorded (in the event stream as planned; since
   decision-152, as a stamped `Event` returned from `Handle.exit_events()`);
   the report grades the
   `limits` axis `best_effort`, naming `memory`, `tasks`, `wall` and
   `output` as uncovered — the cpu field is enforced; per-field grades are
   M7. (Reworded at the M3 closeout from "grades limits-cpu `enforced` with
   the uncovered limit fields named in detail", which contradicted
   decision-061's ruling that the `limits` **axis** grades `best_effort`;
   proposal P-3, accepted by decision-083 *at the closeout*, ordered behind
   task-040's pin by decision-085.)
3. The trampoline composes: the same behavior under the subprocess launcher
   with an extra no-op wrapper stacked outside it (composition smoke test).
4. Report aggregation: `degraded()` preset's report is exactly the golden
   grades (snapshot-tested as data, reviewed by hand once).

---

## M4 — Probe engine

**Goal.** `brig/probe` layer: batteries, three-way verdicts
(PASS/FAIL/VACUOUS), positive controls, probe-vs-report contradiction
checking. Probes run through `handle.exec`.

**Value.** From here on, every enforcement claim in every milestone is
provable on demand — `brig probe` is the library's `/pyact-policy`, for any
stack. This is the feature that makes the reports trustworthy rather than
aspirational.

**Scope.** Core batteries for env, limits, fs-write, fs-read, network (the
fs/network batteries will mostly return VACUOUS-or-FAIL against the stacks
that exist so far — that is correct and is the point); verdict classification
via mechanism denial signatures; `ProbeReport` with per-probe evidence.

**Exit criteria.**
1. Against `degraded()`: env and cpu probes PASS, fs/network probes report
   honestly (FAIL where genuinely unenforced — a FAIL against an
   `unenforced` grade is *consistent*, not a contradiction).
2. Positive controls: a battery run where the workspace-write control fails
   marks the whole battery VACUOUS, not passed — demonstrated by pointing
   the battery at a non-writable workspace.
3. Mutation check: weaken a stack (drop `env_scrub`) without changing its
   claimed report (test-local forgery) — the probe battery *catches the
   contradiction* and fails loudly. This is the probe engine's reason to
   exist; it gets its own test.
4. Verdict classification: a probe that fails for a non-policy reason (e.g.
   command not found) lands VACUOUS, never PASS — unit-tested against the
   signature matcher.

---

## M5-lite — The darwin seatbelt vertical slice

**Amended 2026-08-24 (operator ruling round 16, `decision-110` and
`decision-111`), on the human operator's vertical-slice directive.** M5 as
written was two kernels in one milestone — Seatbelt on darwin and bubblewrap on
linux — on a host that is darwin and has neither. It is **SPLIT**: this entry is
the darwin slice, and **`bwrap` moves to the post-M9 backlog** with its rationale
stated there (an unverifiable-on-this-host mechanism cannot land under law 1).
The superseded M5 text survives in `doc-016` §9 and in `decision-110` as record
drift, and is never retro-edited (`decision-046`).

**Goal.** Kernel-enforced confinement on darwin: the `seatbelt` mechanism
(SBPL — default-deny write + allows, default-allow read + denies, `write_denies`
carve-outs, LISTEN socket-bind rules, deny-all network), the `scratch_darwin()`
preset, fs/network probe batteries that can finally reach `PASS` against a real
kernel, and the **adoption kit** an embedder reads before writing an adapter.

**Value.** brig delivers a real jail on the platform it is developed on. The
parent project's `srt` darwin behaviour becomes reproducible as a brig stack,
and the adoption kit makes M9 a wiring exercise rather than a design one.

**Scope** (`decision-111`, five parts).
- **The mechanism.** A **pure** `spec → SBPL text` render carrying the parent
  project's *probed* dialect facts as **tested** facts, not copied comments:
  `(import "system.sb")` first (`(deny default)` alone `SIGABRT`s `/bin/echo`);
  **realpath before rule-writing** (Seatbelt matches after symlink resolution, so
  a `/tmp` rule silently matches nothing); **unscoped `network-bind`** with the
  **`file-write*` literal** rule confining the socket path (a filtered
  `network-bind` denies the bind outright on this dialect); deny-default write
  with allows; default-allow read with denies; `write_denies` carve-outs
  compiled deny-over-allow; LISTEN channel compilation; deny-all network graded
  `enforced`. Denial signatures ship with the mechanism, per the honesty
  carry-over rule.
- **The battery target-resolution fix** (`doc-016` §7 deviation 4): probe targets
  resolve against the **HOST's** view at **battery construction**, never through
  the jail's env — with the **PASS-mode control that exposed the defect** as the
  named regression.
- **The `scratch_darwin()` preset**: `seatbelt` + `env_scrub` + `rlimits`,
  golden-graded, with its probe battery `CONSISTENT`.
- **The adoption kit**, as deliverables with acceptance criteria:
  `examples/harness_adapter.py` and `docs/ADOPTION.md`.
- **The reverse-contract gate** is recorded now (`decision-112`); **activation is
  the human operator's** and no task or closeout here may claim it.

**Exit criteria (integration + system, darwin-gated; skips must be visible).**
1. **From inside the jail**, each observation made by a jailed process reporting
   what happened, never by asserting on argv: write inside the workspace
   succeeds; write outside fails **with the mechanism's declared denial
   signature matched**; read of a `read_denies` path fails while a sibling
   readable path succeeds — the control; and **write to a `write_denies`
   carve-out inside the workspace fails** (`.git/hooks` canary) **while a
   sibling path inside the same workspace succeeds** — the control that
   separates "carve-out enforced" from "workspace not writable at all".
2. **Socket-bind channel**: with a LISTEN channel declared, the jail binds
   **exactly** the declared endpoint and a bind at any other path is denied;
   with **no** channel declared, a bind attempt is denied — the control that
   keeps `network: enforced` from covering an unscoped bind permission.
3. **`fs_write`, `fs_read` and `network` probe batteries report `CONSISTENT`
   against `scratch_darwin()` with their DENIAL probes at `PASS`** — the first
   passing fs battery in the project — **and the M4 forgery check still catches
   a weakened stack** (`tests/e2e/test_probe_forgery.py`, with its two
   controls, rewritten onto the stack this milestone weakens).
4. **Reports**: `fs_read`, `fs_write`, `network` and `env` grade `enforced` and
   `limits` grades `best_effort` on `scratch_darwin()`, as a hand-reviewed
   golden that turns red on any grade drifting **up**; the **read model is
   declared** in the report `detail` as a **denylist**, matching the parent
   project's own confessed posture rather than overstating it.
5. **Probe targets are host-resolved, and it is proved by a pairing**: the same
   fs DENIAL probe against an `EnvMode.PASS`, no-seatbelt spec reaches the real
   path and lands `FAIL`, and under `scratch_darwin()` lands `PASS` on a matched
   seatbelt signature. Neither side alone discharges this. No probe target may
   depend on a machine-specific file existing.
6. **The adoption kit runs**: `examples/harness_adapter.py` maps a plain-data
   grants record to a `Spec` (store/log denies and the credential list
   included), maps `prepare`/`spawn`/`interrupt`/`kill` to
   `compile`/`launch`/`Handle` with `handle.to_dict` persisted in the session
   dir, and translates `EnforcementReport` **passing `cooperative` through as a
   string** rather than rounding it in either direction — **exercised against a
   real `scratch_darwin()` jail in an integration test**, and pinned as importing
   nothing from any embedding project.

---

## M6 — Egress: connect_proxy as a standalone mechanism

**Goal.** The domain-filtering CONNECT proxy as its own mechanism with
declared helper lifetime, composed two ways: enforced-transport mode (paired
with seatbelt's loopback-only rule) and env-routed mode (`cooperative`, for
the degraded preset).

**Value.** Per-domain egress on darwin at `best_effort` with the SNI gap
named; honest `cooperative` egress everywhere else. Denied egress becomes
visible to the embedder — the "what did it try to reach" question gets an
answer. (Planned as event-stream records; the filter is a separate process
that may not import brig, so it writes its own JSON lines and, since
decision-157, `brig.run.read_egress_decisions` folds them back as stamped
`Event`s. Until that reader existed the answer was written and never read.)

**Scope.** Proxy process (plain-HTTP and CONNECT paths, separately tested);
helper lifetime `JAIL_LIFETIME` via the library's helper machinery (pid-watch
or pipe, chosen once, documented); allow/deny decision events; denial
signature ("403"); ordering rationale vs. seatbelt recorded in the matrix;
probe battery for network.

**Exit criteria (integration).**
1. Granted domain reachable, ungranted denied, **both** for plain HTTP and
   for CONNECT tunnels (two tests — the easy path must not stand in for the
   real one).
2. Every deny is recorded with the hostname, and a reader in `run` returns it
   to the embedder (decision-157; the planned medium was the event stream).
3. Seatbelt-paired mode: a raw dial bypassing the proxy is denied by the
   jail (control proving the pairing, not the proxy alone, carries the
   grade); report `best_effort` with SNI gap in detail. Env-routed mode:
   report `cooperative`; a probe that ignores the env vars demonstrates the
   bypass (that demonstration *is* the grade's justification).
4. Helper lifetime: kill the jail, proxy exits without polling or manual
   reaping; conftest leak-check covers it.

---

## M7 — Limits done right on linux: systemd_scope

**Goal.** cgroup-backed memory / tasks / cpu-quota enforcement via
`systemd-run --user --scope --collect`, ordered outermost so helper
processes are bound too.

**Value.** Closes the axes rlimits honestly cannot (memory, task count,
per-tree not per-user) — the parent project's confessed `best-effort` limits
become mostly `enforced` on linux.

**Scope.** Mechanism + matrix rows (outermost; rationale: bounds other
mechanisms' helpers); grades split per limit field; OOM (exit 137) and
TasksMax denial signatures; limits probe battery extended. Skip-gated to
linux with systemd user session.

**Exit criteria (integration, linux-gated).**
1. Memory hog under `memory_bytes` is OOM-killed (137); fork bomb under
   `max_tasks` is contained while the *operator's* process count is
   unaffected (the control that rules out the RLIMIT_NPROC failure mode).
2. Ordering proof: a mechanism helper (the M6 proxy) runs inside the scope —
   observed via cgroup membership, not asserted.
3. `--collect` verified: repeated runs leave no accumulated scopes.

---

## M8 — Observation: pty-tee, tmux launcher, stat for status lines

**NOT BUILT, and no longer planned in this shape.** The `tmux` launcher came
off SPEC.md §8's roster at decision-154 (2026-09-08): its whole value was
observation, which the embedder owns — brig hands back records and a handle,
and what a human watches is the embedder's surface. `attach_ro_command()` and
the `"pane"` kill-item kind went with it. The `subprocess_pty` launcher stayed
on that roster for one more ruling and came off at decision-158, for the
plainer reason that it was never written either and a roster is not a plan; it
is now in SPEC.md §15 as deferred work, where an unbuilt thing belongs.
`stat()` shipped at M2 in its `alive`/`pids`/`report` form. What follows is
the plan as it stood.

**Goal.** `brig/observe` layer: `subprocess_pty` launcher (teed, capturable,
replayable), `tmux` launcher on a dedicated socket (read-only attach command
as data), `console()` / `capture()` / `stream()`, `stat()` cheap enough to
poll, workspace diff.

**Value.** Any jail is watchable; tmux finally composes with real jails
(the argv/trampoline design from M3/M5 is what makes this possible — this
milestone proves that claim); embedders can render "UNSANDBOXED"-grade
status from `stat()`.

**Scope.** tmux launcher (dedicated `-L` socket, argv-words-not-string so
pane pid is the real process); capability declarations + refusal when a
stack's `requires` exceed a launcher; read-write attach exists only as a
channel request (policy-gated), `attach_ro_command()` returned as data;
interactive `handle.exec` lands here (it needs the pty machinery).

**Exit criteria (integration).**
1. Same stack, three launchers: **the enforcement report is byte-identical**
   across subprocess / pty-tee / tmux (observation ⊥ enforcement, tested,
   not asserted).
2. `capture()` returns known workload output under pty-tee and tmux; the
   tmux attach command is returned as data and points at the dedicated
   socket, never the default server.
3. A `scratch_darwin()` jail under the tmux launcher still passes its M5-lite
   probe battery — the milestone's headline claim, as a test. (Was "a
   `strict()` fs jail … its M5 probe battery"; re-anchored 2026-08-24 by
   `decision-110`, which split M5 and made `scratch_darwin()` the preset that
   has a passing fs battery.)
4. Interactive exec: scripted pty session (`exec(["sh"], interactive=True)`,
   drive a command, see output); open/close both recorded.
5. Conftest leak-check covers tmux panes/sockets.

---

## M9 — Adoption spike: the parent harness runs on brig

**Goal.** Behind the parent project's existing provider seam, implement
`none` and `srt`-equivalent providers as thin adapters over brig stacks;
parent integration suite passes unchanged.

**Value.** Proof the library is actually independent *and* sufficient — the
extraction thesis validated against the only real consumer. Findings feed
back as spec changes before the API is called stable.

**Scope.** Adapter code lives in the parent repo, not in brig. brig changes
allowed only as fixes to real gaps the adoption surfaces (each becomes a
spec edit + ticket, not a drive-by). Devcontainer stays on the old path
(oci_container is post-M9).

**Exit criteria.**
1. The embedder's own gate (unit + integration) green with the adapter
   providers substituted. **How this actually landed:** the adoption target
   became keel rather than the parent harness this milestone was written for,
   the adapter is `keel_executors.sandbox.SandboxExecutor` written against
   keel's real ports, and the gate it runs under is this workspace's
   `./tools/verify.sh`. See ADOPTION.md.
2. The parent's own jail-observed tests (read-deny, socket invariant,
   scratch profile) pass under brig-backed `srt`.
3. A written delta report: every place the brig report disagrees with the
   old provider's report, explained — differences must be *more* honest, or
   they are bugs.

---

## Post-M9 backlog (unscheduled, in likely order)

- **`bwrap` (linux filesystem jail)** — ro-bind / tmpfs-shadow / bind mounts,
  `--unshare-net` when no domains, `--die-with-parent`, `write_denies` compiled
  as mount-shadow, allowlist read model, and the `strict()` linux preset. Moved
  out of M5 by `decision-110` (2026-08-24). **Rationale, stated rather than
  implied: an unverifiable-on-this-host mechanism cannot land under law 1.** The
  development host is darwin with no Linux and no `bwrap`, so its enforcement
  claim could only ship asserted rather than observed from inside the jail —
  and the parent project's own README already declares Linux untested.
  **Schedulable when** a host exists on which the mechanism's enforcement can be
  observed from inside the jail; until then the pure-argv-render half is not
  worth landing alone, because a render nothing adjudicates is exactly the
  claim-without-a-reader shape this project keeps finding.

- **M10 `oci_container`**: the relay, container-local channel endpoints,
  `docker exec` co-tenancy, iptables/ipset egress, kill-through-handle for
  dead-relay recovery (the serialized-handle fix, proven by killing the
  relay first and tearing down from rehydration).
- **M11 `nix_closure`**: provisioning axis; jail.nix-style bwrap pairing;
  closure pinning aligned with Spec provisioning digests.
- **M12 `pasta`/`slirp4netns`**: filtered egress inside an unshared netns —
  upgrades linux granted-domains from `unenforced`.
- ~~**M13 mailbox primitive**: framed file, deliverer-stamped provenance,
  urgency composition (NEXT_TURN / INTERRUPT).~~ **DELETED 2026-09-08 by
  decision-153**, with SPEC.md §10's whole mailbox primitive. Its own contract
  said the jail never touches it, which makes it the embedder's steering
  surface rather than a way into a jail. `ChannelKind.MAILBOX` went with it;
  `LISTEN` is now the only kind.
- **M14 packaging & release**: PyPI, versioned Spec/report schemas, docs.
