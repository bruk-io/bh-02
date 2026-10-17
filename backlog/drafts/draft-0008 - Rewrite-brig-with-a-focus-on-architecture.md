---
id: DRAFT-0008
title: Rewrite brig with a focus on architecture
status: Draft
assignee:
  - '@bruk'
created_date: '2026-10-17 14:58'
updated_date: '2026-10-17 17:31'
labels:
  - brig
dependencies: []
references:
  - >-
    backlog/decisions/decision-0008 -
    Rebuild-brig-as-a-pure-domain-behind-ports-and-adapters-with-no-backwards-compatibility.md
type: intent
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem

brig works, and it jails bh-02's Python process today, but it grew stage by stage and it shows.
A jail type is spread over four packages, pure decisions sit inside the code that does I/O, grades
are stated before anything proves them, one role has two names (supervisor and "agent"), and the
supervisor program is written to an older Python than the rest. About half of what it ships, bh-02
never uses.

I want it rewritten with a focus on architecture, in my Python approach. It stays in bh-02 for now,
not a new repository, and the `libs/brig` folder should not contain the old brig code.
"io needs to be separate", and it "should not care about domain": three layers, domain, infra and
presentation, with standard test layers (unit, integration, e2e, defined by where the mocks start). We won't care about backwards compatibility; breaking is
mostly fine, and it's fine if bh-02 is in a broken state while we do this, on main. Keep egress. Keep oci, but pause on it for now.

Working in it should be really clean. While working, only the unit and integration tests the change
reaches run. E2e, the full suites, pypeeker, ruff and mypy run only when the work is done. `just` is the entry point for running these things. It needs a docs directory, MkDocs
with an auto-generated reference, and LikeC4 with the LikeC4 MCP enabled, following my best
practices. It should also create a Claude settings file at the start, to make sure my plugins are
set up. I would prefer all logs to be JSON-shaped and consistent.

## Affected users and systems

- **The owner (@bruk)**, who builds, reviews and accepts brig's work.
- **The agents working on brig in bh-02**: implementing workers and the reviewer that closes
  tasks. `just check`, `just done` and the LikeC4 MCP are their tools as much as the owner's.
- **bh-02**, brig's only embedder. Its runner plugin (`runner_cordis_plugin.jail`) is the only code
  that imports brig. Once the old brig is deleted, bh-02 is broken until its runner moves to the new
  brig's API.
- **The old brig**, deleted from `libs/brig` and reachable only in git history (as of d297a50,
  2026-10-17): the reference the rewrite reads with `git show` (its code, its 3,950-line SPEC and
  the measured facts in its rulings, decisions 1-203).
- **bh-02's `main` and its CI**: the rebuild lands on `main`. From the old brig's deletion until the
  runner moves, bh-02's own checks (`scripts/check`, the `linux-jail` workflow, the runner's tests)
  fail on `main` and on every pull request, as expected; brig's `just done` is the gate for brig's
  work. CI is Linux with bubblewrap and Docker. Seatbelt needs a Mac.

## Open questions

- [ ] Reservations (`.reserve(`): carry them over for bh-02's per-jail socket directory
  (bh-02 TASK-0079.31), or drop them?
- [ ] Egress: cooperative as today (the workload is pointed at the proxy and may ignore it), or
  enforced, by relaying the jail's only route out through the supervisor to the proxy?
- [ ] Seatbelt: build its slice before a Mac run proves it, or leave macOS unjailed (like every
  host until the new brig jails it) until a Mac run can prove it?
- [ ] The SPEC's numbering: continue from the old SPEC's decision-203, or start a fresh series with
  the old SPEC kept as history?
- [ ] The docs theme: bh-01's components, as bh-02's site uses, or Material for MkDocs?
- [x] The ruff hook that formats every file an agent edits: settled by staying in bh-02, whose
  `.claude/settings.json` already runs it on every edited file; ruff's checks still run only in
  `just done`.
- [ ] The log envelope: its fields (time, level, source, event, then the event's own fields?), and
  whether "all logs JSON-shaped and consistent" becomes a rule in the philosophy plugin, for every
  repository and not only brig.
- [x] Is "breaking is mostly fine" fully covered by criteria 16 and 17? Settled by the owner: bh-02
  may be broken while brig is rebuilt, so the ten laws (criterion 16) are all that must not break.

## References

- bh-02 decision-0008 (proposed): the layout and rules from before the brainstorm. Update it: the
  old brig is deleted rather than archived at `archive/brig-v1/`; the layers renamed domain, infra and presentation (infra independent of the
  domain); the cuts and keeps above. Its rule 14's four test layers become the three of the
  owner's test rule (unit, integration, e2e). Its order runs inside-out (the domain first, the API
  at step 5), against the test rule's "work outside-in": the new board's order starts from a test
  at the public API and works inward.
- bh-02 decision-0007 (accepted): Python 3.15 everywhere, the supervisor included.
- bh-02 TASK-0133 (supervisor, never agent) and TASK-0134 (decision-0007's implementation) are
  absorbed by criteria 1 and 5. TASK-0131 (earlier helpers left running) has nowhere to happen once
  the proxy is the only helper.
- The c4-architecture plugin, in knowhere (`likec4-diagrams`: scaffold.py's layout, c4lint, the
  hard rules).
- `@likec4/mcp` (1.60.0), `mkdocs-likec4` (1.2.2), `mkdocstrings-python` (2.0.9), `rust-just`
  (1.59.0): the versions current on 2026-10-17.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 brig lives in bh-02's `libs/brig`, rebuilt from empty: nothing of the old brig's code is in the folder, and it is reachable only in git history. brig imports only the standard library. Every file is Python 3.15, the supervisor program included.
- [ ] #2 Before any other work lands, bh-02's `.claude/settings.json` sets up the owner's plugins for every session in the repository, the owner's or an agent's, local or in the cloud: it registers the knowhere marketplace (`bruk-io/knowhere`), enables `philosophy@knowhere`, `authoring-kit@knowhere` and `c4-architecture@knowhere`, and approves the `likec4` server from `.mcp.json`.
- [ ] #3 The code is in three layers: `domain` does no I/O and imports nothing outside itself, `infra` imports nothing from brig and takes and returns plain data, and `presentation` is the only layer that knows both. A gate fails any change that breaks one of these rules.
- [ ] #4 Each jail type is a slice of its own, and no jail type imports another. bwrap and Seatbelt are built. oci has its place in the layout but is not built yet (paused).
- [ ] #5 Kept, and working: the filesystem policy, environment scrubbing, channels, the supervisor (named supervisor everywhere, never agent), the verified teardown and its report, grades, egress through the allowlisting proxy, and the interpreter checks.
- [ ] #6 Cut, with nothing left of them: resource limits and the trampoline, rebuilding a jail in another process, probes as public API (the batteries stay, as e2e tests), events and denial signatures, exec fidelity, the mechanism stack and its compatibility matrix, the fake runtime, and the general helper machinery (the proxy is the one helper, started and stopped as part of the jail).
- [ ] #7 The code follows the owner's Python approach (`philosophy:python-idioms`) and passes strict mypy.
- [ ] #8 Every test sits in one of three layers, defined by where the mocks start (the owner's `python-tests` rule, 0.4.6): `tests/unit/` tests one pure function, with nothing mocked; `tests/integration/` tests brig's own parts together from a real entry point, with the world faked at its edge and nowhere else (fakes only, asserted on through their state); `tests/e2e/` tests against the real world with nothing faked, either a whole journey through the public API (the batteries included) or one infra module against bubblewrap, sandbox-exec or Docker. No test in any layer patches: time, randomness and the host enter the code as data. The fakes of the world live with the integration tests, not in brig.
- [ ] #9 `just` is brig's only entry point (`libs/brig/justfile`; bh-02's `scripts/check` stays the workspace's): `just --list` shows every recipe with what it does, and each command line is written once, in the justfile.
- [ ] #10 `just check` runs only the unit and integration tests that the change reaches (the diff against `main`, plus uncommitted and untracked files), and nothing else.
- [ ] #11 `just done` runs ruff, mypy (`just typecheck`), every pypeeker gate (`check --strict`), every test in all three layers, the integration suite twice in one process to catch leaked state, the docs build and the architecture lint. It reports every step whole and every failure in one pass. An e2e test it cannot run on this host is listed by name, never counted as a pass. CI runs `just done`, and nothing else counts as green.
- [ ] #12 brig's docs live in bh-02's MkDocs site, under `docs/brig/`, and the site builds failing on any warning. Its API reference is generated from brig's public API at build time and never committed.
- [ ] #13 brig's architecture is a LikeC4 model in orthodox C4, laid out and linted by the c4-architecture plugin's rules (`likec4 validate` and c4lint clean). Its views are embedded in the docs, and the LikeC4 MCP server is enabled for every session in the repository, at a pinned version.
- [ ] #14 The SPEC is part of the docs: brig's ten laws carried over, then one section per layer.
- [ ] #15 Every line brig's own processes write (the supervisor program, the egress proxy and its decision lines) is one JSON object in one envelope, defined once and written by one encoder. The library itself writes no log: what it knows comes back to the embedder as data.
- [ ] #16 Must not break: Every one of brig's ten laws (the old SPEC, section 2) holds in the new brig. Each has a test that would fail if it stopped holding, law 10's with a planted violation and its positive control.
- [ ] #17 When the new brig can jail bh-02's Python process, bh-02's runner moves to the new API in one change, and bh-02 works again, jailed. Until then bh-02 may be broken.
<!-- AC:END -->
