# WORKFLOW.md — the rules brig is built under

brig was built in its own repository, by an orchestrator dispatching one task
at a time to implementing and verifying agents. **That machinery did not come
with it.** What is written here is the part that still binds anyone changing
brig: **the gate, the tiers, the evidence rules, and the spec-first law.**
MILESTONES.md is the record of what was planned and what shipped.

Decision numbers are kept on every rule that has one, because code and tests
cite them by number (`WORKFLOW.md decision-026 rule 1`, `rule 4's remedy`, the
restoration discipline). A rule renumbered here would strand those citations.

## The gate

brig is a member of a uv workspace, and green is the workspace's checks passing
with brig's own gate among them. From the workspace root:

```sh
uv run ruff format --check brig && uv run ruff check --no-fix brig
uv run mypy brig/src
uv run pytest libs/brig -q
scripts/arch-check --no-fix       # runs brig's gate from brig/, with its own rules
```

Read each with its real exit code, never through a pipe: a pipe's exit status
is the last stage's, and a green `tee` has hidden a red gate before.

Narrower runs while working:

```sh
uv run pytest libs/brig -m unit
uv run pytest libs/brig -m integration
uv run pytest libs/brig -m e2e
```

## The tiers

Three markers, and **every test carries exactly one** — enforced by brig's
`tests/conftest.py`, so a brig test with none fails collection.

| marker | what it may touch |
|---|---|
| `unit` | one module, no I/O, no subprocess, no sockets, no clock |
| `integration` | several in-repo components, real OS mechanisms, external deps mocked |
| `e2e` | real mechanisms end to end, through the public API only |

brig's own repository called the top tier `system` and kept it in
`tests/system/`. Here it is `e2e`, in `tests/e2e/` — same tests, same platform
gating, same meaning. Prose that still says "system tier" is stale wording,
not a third tier.

`tests/conftest.py` also adds two things: the
leak sweep (every workload the suite launches carries a per-run token, and a
`/bin/ps` sweep plus a spawn registry catch anything a test's teardown missed)
and a POSIX floor that skips the integration and e2e tiers **by name** where
the OS cannot host them. Darwin-only mechanisms carry their own `skipif` at
the module that uses them. A skip that reads as a pass is the failure this
posture exists to avoid.

## Spec first (binding)

**A behaviour change is a SPEC.md change first.** Each lands as a dated
decision paragraph in the section it belongs to, and SPEC.md is left
describing the shape that is *built* — not the shape that was planned. The
laws in §2 are the fixed part; everything else is amendable by a ruling that
says so out loud.

**Every fold names its implementing task, or states "no code change"**
(decision-096). A fold with neither is tracked by nothing: decision-080's fold
landed with no task, and two rounds later the shipped code still contradicted
SPEC.md §5 with two green unit tests asserting what the spec forbade — no gate
in the repository could see it, because the gate checks code against tests
and both had been changed to agree with each other rather than with the
specification. "No code change" is a legitimate and common outcome; silence is
not.

**Amending a governing document means re-reading what quotes it.** brig's own
repository ran `scripts/anchor_check.py` over its task corpus for this; the
corpus and the script are both gone, and what replaced them is a grep: SPEC.md,
MILESTONES.md and this file are quoted verbatim in docstrings and test
docstrings all over brig, so an amendment that moves a sentence
someone quotes leaves a citation pointing at text that no longer exists. Search
for the moved phrase before committing the move. (decision-046's distinction
still holds: a *dispatch input* quoting superseded text misleads the next
reader and is fixed; a *record* quoting it is history and is never retro-edited.)

## Git discipline (binding)

**Git is read-only while implementing** (decision-074). No `stash`, `checkout`,
`restore`, `clean`, `reset`, `add`, or `commit` — ever, in any form, including
inside a helper script or a mutation-check teardown. Reading is untouched
(`status`, `diff`, `log`, `show`, `ls-files`).

Those seven verbs are **whole-tree** operations. brig's M3 used `git stash`/`pop`
and `git checkout --` for mutation-check cleanup while three workers shared one
tree, and the race swept six tasks' freshly-modified tracked files back to
`HEAD` while their untracked deliverables survived — destroying the record of
real work (decision-073).

**Restoration is a scratch copy plus `sha256`, never git.** Copy the file out
before mutating it, copy it back after, and paste the matching digest as proof.
Better still: plant into a scratch copy of the tree and never touch the
original. This is the discipline several docstrings in the suite refer to when
they say a mutation check was run "as a one-time scratch-copy plant/revert".

## Evidence rules (binding)

A criterion must be capable of being **both true and false**. Before running
one, ask: *what would make this fail?* A criterion with no answer is not a
criterion.

**Never pin content with `git diff <file>` against a file that has no committed
baseline** (decision-018). Until a baseline commit exists for that path, `git
diff` is empty by construction and the check cannot fail. Pin content by
literal comparison against text quoted into the task instead. Once a path has
been committed, `git diff` against it is a real assertion again — subject to
rule 2.

Six rules from the same failure class:

1. **No bare command name a shell alias can redefine** (decision-026). Use an
   absolute path (`/bin/ps`, `/bin/ls`), a command with no common alias
   (`find`, `git`, `grep`), or `python -c`. M1 pinned the layer list with
   `ls -F brig | grep '/$'`; `ls` was an alias for `eza`, whose `-F` emits no
   trailing slash, so the pipeline printed nothing whether or not the criterion
   held. The failure class is "the check's meaning depends on the shell it runs
   in", and the fix is to remove that dependence, not to enumerate aliases.
   This is why every `/bin/ps` scan in this suite spells the absolute path.
2. **A `git diff` content pin ships its own plant-control** (decision-026). On
   a committed path the diff discriminates *only when the pathspec resolves* —
   run from the wrong directory, a repo-root-relative pathspec resolves to
   nothing and returns an empty diff **with a plant present**, indistinguishable
   from "identical". So plant a difference, observe that same invocation report
   it non-empty, and revert. Without the control it is rule decision-018's
   unfalsifiable assertion wearing a baseline. Several docstrings call a
   deliberate no-deletion change "this task's own zero-`git diff` pin"; that is
   this rule.
3. **A mutation pairing names a deterministic test** (decision-026). "Breaking
   X makes test Y fail" is discharged only by a `Y` that fails *every* run. A
   hypothesis or property test that reddens on some samplings is corroboration,
   never the named pairing: M1 found a planted clause caught in only 2 runs of
   4, which would have made the criterion pass or fail by luck.
4. **A claim whose subject a later change is chartered to replace is retired BY
   that change** (decision-041). Not by deletion alone, and never by editing a
   red tree until it is green. The replacement **asserts the positive** — that
   the thing which replaced the scaffolding is present and works — and carries
   its own control. M2 shipped three raising stubs so parallel work could run on
   disjoint files, pinned them with a test, then removed the stubs; the test
   became false and the tier went red with no rule for it. Note what this is
   *not*: it does not license removing a test that is true and inconvenient.
5. **A change may pin only what it alone owns** (decision-078, generalized by
   decision-079). "`pytest -m integration` reports exactly N passed" stops
   being a claim about *this* change the moment anything else lands. M3 had the
   same integer — 51 — pinned in three places while the tree stood at 62. What
   a change owns and still pins: its own new tests, named, and the suite's
   health (0 failures). Where a total is genuinely wanted, state a
   reconciliation — baseline + enumerated additions = observed total — and
   require the arithmetic to close exactly. The enumeration is over collected
   test ids, not over files: a new module can grow a parametrized count in a
   file nobody edited (decision-083).
6. **A `grep` content pin must discriminate a CALL SITE from a MENTION**
   (decision-083). A pattern that a docstring, a quoted spec sentence, or a
   comment can satisfy is not asserting what it says it asserts: it goes green
   on prose and red on a re-worded comment, in both cases without anything
   happening to the code. Pin the call site's syntax, scope the search to the
   paths the claim is about, and ship rule 2's plant-control.

## Deterministic gates, not judgment

Anything a machine can check is checked by a machine, and the list is short on
purpose: layering (`pypeeker check --strict`, over the tables in the root
`pyproject.toml`), types (`mypy --strict`), format and lint (`ruff`), tier
markers (the root `conftest.py`), leaked processes (brig's own
`tests/conftest.py`), coverage (`fail_under` in `pyproject.toml`). A rule that
only a reader enforces is a rule that decays; if a rule here matters and can be
mechanized, mechanize it and delete the prose.

## Rules that keep the work honest

- **Never grade up.** A mechanism claims what it can deliver on the platform it
  compiled for, and nothing more. This is law 1, and every other rule here is
  downstream of it.
- **A capability that is not implemented is absent from the surface**, never a
  raising stub (SPEC.md §9). A method that raises lies to `hasattr` and to
  every embedder that feature-detects.
- **A declared-and-uncalled shape is a defect, not a placeholder.** `Helper`
  went three milestones with nothing starting one; the egress proxy wrote its
  decisions to a file no reader opened for two. Both were found by asking "who
  reads this?" of a thing the code declared.
- **A control belongs in the same test as the claim.** "The jail denied it" is
  worth nothing without "and the same jail, in the same run, permitted the
  allowed case" — otherwise a broken jail and an unreachable target look
  identical.
- **An observation made with the code under test is not an observation.** The
  suite's leak checks, teardown proofs and liveness assertions go through
  `/bin/ps` and `os.kill`, never through the module they are judging.
