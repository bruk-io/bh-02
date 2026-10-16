---
id: TASK-0128
title: >-
  Prove in a real jail that no directory on the way to bh-02's interpreter can
  be renamed
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-16 23:20'
updated_date: '2026-10-16 23:40'
labels:
  - runner
  - security
  - size-1
dependencies: []
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found reviewing TASK-0127: rename(2) refuses only a dentry that is itself a mount point, so an ancestor of a held path can be renamed and its mounts move with it. With the project at the home directory, an input that could mv ~/.local/share/uv aside could build its own python3.15 at the old name, and the next uv run on the host would run it.

Measured 2026-10-16 by the orchestrator, in a real bwrap jail with `_a_uv_python_in`'s layout: it is refused today. TASK-0126's interpreter deny and TASK-0127's link-directory denies are write denies, so brig's decision-168 pins bind every existing directory between the project and them over itself: `uv`, `uv/python`, `venv` and `venv/bin` refuse a rename (Device or resource busy), the rest are inside a read-only deny (Read-only file system). With `brig.mech.bwrap`'s `pins` replaced by one that returns nothing, renaming `uv` and `venv` succeeds on the host. So the pins are the one thing holding it, and no runner test says so: a change to the pins, or to which denies the runner hands brig (`uncovered`, `mountable`), could reopen it silently. This adds that test; no code change is expected.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 In a real bwrap jail with uv's layout under the project, an input's rename of each directory between the project and the interpreter file or a link on the way to it is refused, and nothing is moved on the host
- [x] #2 The test is seen failing with brig.mech.bwrap's pins replaced by one that returns nothing (renaming uv and venv then succeeds), and passing without the plant
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Order of work: (1) run the sibling real-jail test to confirm bubblewrap works here (not skipped). (2) Add one new test beside test_a_linux_jail_refuses_an_input_that_changes_a_link_..., not an extension of it: its assertion is one line per directory with an errno set (the link test counts 3*len(chain)), and its docstring is about the pins (decision-168), a different mechanism. Module-level program _LISTEN_THEN_RENAME_THE_DIRECTORIES with a comment above, argv = listen endpoint, the directories deepest first (ties by path, so the order is deterministic), said file. Dirs are derived from the layout the way the probe does (parents of the interpreter file and each link on the way, strictly under the resolved project). Assertions: each refusal is EBUSY or EROFS (strerror of both, so a vacuous ENOENT fails), nothing done, host: every directory still a dir at its name, no *.moved, file still there. finally: started.stop(). (3) Plant: temporarily add monkeypatch.setattr(sys.modules[brig.mech.bwrap], pins, lambda *a: ()) in the new test, run it, expect failure with uv and venv done; record errnos; revert the plant and confirm git diff has no plant. (4) Run the new test without plant, then uv run pytest -k linux_jail under tini -s --. (5) scripts/check bh-02/plugins/runner-cordis-plugin once at the end. Risks: the test is real-jail only and skips without /usr/bin/bwrap, so the run must show passed, not skipped; a plant left in the file; committing the backlog auto-commits (squash to 1d64d15 at the end).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implementation notes (worker, machine shared with one other worker: no timings recorded)

Changed: bh-02/plugins/runner-cordis-plugin/tests/test_runner_confined.py only (no code change outside the test).
- `import errno`.
- `_LISTEN_THEN_RENAME_THE_DIRECTORIES`: module-level program with a comment above it; tries os.rename(d, d + ".moved") for each argv directory and writes "<path>: done" or the strerror.
- `test_a_linux_jail_refuses_a_rename_of_a_directory_on_the_way_to_the_interpreter_bh_02_runs_on`, beside the link test. A new test, not an extension: the link test counts 3 * len(chain) and its docstring is about links; the pins (decision-168) are a different mechanism. Directories = parents of the interpreter file and of each link on the way, strictly under the resolved project, deepest first (ties by path). Host checks: each directory still a dir at its name, no *.moved, file present.

Unplanted, real bwrap (/usr/bin/bwrap), errno per directory (deepest first):
- uv/python/cpython-3.15.0-linux/bin: Read-only file system
- uv/python/cpython-3.15.0-linux: Read-only file system
- uv/python: Device or resource busy
- venv/bin: Device or resource busy
- uv: Device or resource busy
- venv: Device or resource busy

Plant (not committed): monkeypatch.setattr(sys.modules["brig.mech.bwrap"], "pins", lambda *a: ()) in the new test. Seen FAILING: uv: done, venv: done (same errnos for the other four); on the host afterwards uv.moved and venv.moved existed, uv and venv did not. The final-name run also failed (exit 1) with 'done' among the values. The file was restored from a backup and cmp-checked: no plant, no print in the diff.

Commands and results:
- sibling baseline `...::test_a_linux_jail_refuses_an_input_that_changes_a_link_...`: 1 passed (real jail, not skipped).
- new test unplanted: 1 passed; then 10 repeats in a row: 10 passed (exit 0 each).
- `tini -s -- uv run pytest bh-02/plugins/runner-cordis-plugin -k linux_jail -q -rs`: 13 passed, 75 deselected, exit 0 (the new test is among the 13).
- `scripts/check bh-02/plugins/runner-cordis-plugin`, first run: exit 1, lint only: line-too-long, the def name was 114 > 110. Fixed by renaming the test; `uv run ruff check` on the file passed.
- A race found on one run of the new test: `said.exists()` is true when the child has created the file, before it writes, so the parent once read {} (the sibling tests use the same idiom). The new test now waits until the file has one line per directory; 10/10 passed after. Sibling tests left unchanged.
- `scripts/check bh-02/plugins/runner-cordis-plugin`, final run: exit 0. format ok; lint ok; types ok (7 files); tests 87 passed, 1 skipped (test_runner_confined.py:1522, "seatbelt is darwin's"); gates ok for (root), libs/brig, libs/cordis, libs/cordis-helpers, libs/host-paths; docs ok; tokens skipped (no bh-01 dist here).

Not run: root scripts/check (not asked; not ticked); scripts/arch-check (nothing changed outside the member); scripts/linux-jail-check (Docker; the jail tests ran on this host's bwrap).

Not changed, for the owner: plugins/runner-cordis-plugin/README.md, the "The tests:" paragraph about the link denies, does not name this new test.

Check `scripts/check` exited 0

(22 earlier lines omitted)
```text
........................................................................ [ 19%]
........................................................................ [ 22%]
........................................................................ [ 24%]
........................................................................ [ 26%]
........................................................................ [ 28%]
........................................................................ [ 30%]
........................................................................ [ 33%]
........................................................................ [ 35%]
........................................................................ [ 37%]
........................................................................ [ 39%]
........................................................................ [ 41%]
........................................................................ [ 44%]
........................................................................ [ 46%]
..................................................................s..sss [ 48%]
sss...........s......................................................... [ 50%]
........................................................................ [ 52%]
........................................................................ [ 55%]
.ssssssssss...s..............s.......................................... [ 57%]
.......s................................................................ [ 59%]
........................................................................ [ 61%]
...............sss...................................................... [ 63%]
........................................................................ [ 66%]
........................................................................ [ 68%]
........................................................................ [ 70%]
........................................................................ [ 72%]
........................................................................ [ 74%]
........................................................................ [ 77%]
........................................................................ [ 79%]
........................................................................ [ 81%]
........................................................................ [ 83%]
........................................................................ [ 86%]
........................................................................ [ 88%]
........................................................................ [ 90%]
........................................................................ [ 92%]
........................................................................ [ 94%]
........................................................................ [ 97%]
........................................................................ [ 99%]
.........................                                                [100%]
3236 passed, 31 skipped in 289.83s (0:04:49)
   ok
== gates
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.
== (root)
   ok
== libs/brig
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/bh-02/.claude/worktrees/wt-0128/site
INFO    -  Documentation built in 6.66 seconds
   ok
== tokens
   skipped: no /home/user/bh-02/.claude/worktrees/bh-01/dist (bh-01, built, beside this repository)
```
<!-- SECTION:NOTES:END -->
